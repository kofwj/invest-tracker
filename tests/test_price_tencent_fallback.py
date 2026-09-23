"""腾讯行情兜底：东财实时报价接口不可用时的降级路径。

背景（生产实测）：东方财富 push2/push2delay 的 /api/qt/* 会整段不可用——TLS 握手成功、
证书正常，但请求发出后远端直接断开（RemoteDisconnected）；东财其他域名与它的 K 线接口
(push2his) 正常，本机换网络同样失败，所以不是服务器 IP 被封。后果是一整批场内标的
"未取到有效价格" → 当天快照沿用旧价 → 当日收益显示约 0 并污染后续所有指标。
qt.gtimg.cn 一直可用（K 线走的就是腾讯），所以用它兜底。
"""


import pytest


class FakeResp:
    """足够像 requests.Response：raw + encoding，text 按 encoding 解码。"""

    def __init__(self, raw: bytes, status: int = 200, json_body=None):
        self._raw = raw
        self.status_code = status
        self.encoding = "utf-8"
        self._json = json_body

    @property
    def text(self):
        return self._raw.decode(self.encoding, errors="replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


def _quote_line(symbol: str, name: str, code: str, price: str, prev: str) -> str:
    # 腾讯格式：v_sh601288="1~名称~代码~现价~昨收~今开~…"（88 字段，这里补够 6 个即可）
    parts = ["1", name, code, price, prev, price]
    return f'v_{symbol}="{"~".join(parts)}";'


def test_tencent_symbol_mapping():
    from price_sync import tencent_symbol

    assert tencent_symbol("600519") == "sh600519"   # 沪市个股
    assert tencent_symbol("601288") == "sh601288"
    assert tencent_symbol("000651") == "sz000651"   # 深市个股
    assert tencent_symbol("159352") == "sz159352"   # 深市 ETF
    assert tencent_symbol("513530") == "sh513530"   # 沪市 ETF
    assert tencent_symbol("508056") == "sh508056"   # 沪市 REIT
    assert tencent_symbol("430047") == "bj430047"   # 北交所
    assert tencent_symbol("f002864") == ""          # 场外基金不走行情
    assert tencent_symbol("") == ""
    assert tencent_symbol("abc") == ""


def test_fetch_tencent_quotes_parses_gbk_payload(monkeypatch):
    import price_sync as ps

    ps.clear_quote_cache()
    payload = ";".join([
        _quote_line("sh601288", "农业银行", "601288", "6.83", "6.88"),
        _quote_line("sz000651", "格力电器", "000651", "38.36", "38.18"),
    ]).encode("gbk")
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResp(payload)

    monkeypatch.setattr(ps.requests, "get", fake_get)
    quotes = ps.fetch_tencent_quotes(["601288", "000651"])

    assert calls and calls[0].startswith("https://qt.gtimg.cn/q=")
    assert quotes["601288"]["price"] == 6.83
    assert quotes["601288"]["name"] == "农业银行"
    assert quotes["601288"]["prev_close"] == 6.88
    assert quotes["601288"]["source"] == "腾讯行情"
    # 涨跌幅由现价/昨收推导
    assert quotes["601288"]["change_pct"] == pytest.approx(round((6.83 / 6.88 - 1) * 100, 2))
    assert quotes["000651"]["price"] == 38.36


def test_tencent_skips_suspended_and_blank_prices(monkeypatch):
    import price_sync as ps

    ps.clear_quote_cache()
    payload = ";".join([
        _quote_line("sh601288", "农业银行", "601288", "0.00", "6.88"),   # 停牌
        _quote_line("sz000651", "格力电器", "000651", "", "38.18"),      # 无价
    ]).encode("gbk")
    monkeypatch.setattr(ps.requests, "get", lambda url, **k: FakeResp(payload))

    assert ps.fetch_tencent_quotes(["601288", "000651"]) == {}


def test_eastmoney_failure_falls_back_to_tencent(monkeypatch):
    """东财连接被远端断开（生产实况）→ 仍然拿到价格，来源标成腾讯。"""
    import price_sync as ps

    ps.clear_quote_cache()
    payload = _quote_line("sh601288", "农业银行", "601288", "6.83", "6.88").encode("gbk")

    def fake_get(url, **kwargs):
        if "eastmoney.com" in url:
            raise ConnectionError("Remote end closed connection without response")
        return FakeResp(payload)

    monkeypatch.setattr(ps.requests, "get", fake_get)
    quotes = ps.fetch_eastmoney_quotes(["601288"])

    assert quotes["601288"]["price"] == 6.83
    assert quotes["601288"]["source"] == "腾讯行情"


def test_eastmoney_ok_does_not_call_tencent(monkeypatch):
    """东财正常时不应该多打一次腾讯。"""
    import json as _json

    import price_sync as ps

    ps.clear_quote_cache()
    urls = []

    def fake_get(url, **kwargs):
        urls.append(url)
        if "eastmoney.com" in url:
            body = {"data": {"diff": [{"f12": "601288", "f14": "农业银行", "f2": 6.83, "f3": 0.5, "f18": 6.88}]}}
            return FakeResp(_json.dumps(body).encode("utf-8"), json_body=body)
        return FakeResp(_quote_line("sh601288", "农业银行", "601288", "9.99", "6.88").encode("gbk"))

    monkeypatch.setattr(ps.requests, "get", fake_get)
    quotes = ps.fetch_eastmoney_quotes(["601288"])

    assert quotes["601288"]["price"] == 6.83
    assert quotes["601288"]["source"] == "东方财富行情"
    assert all("gtimg" not in u for u in urls), "东财正常时不应请求腾讯"


def test_sync_prices_impl_updates_via_tencent_when_eastmoney_down(app_module, monkeypatch):
    """端到端：东财挂了也要能把价格更新进去（否则当日收益恒为 0）。"""
    import price_sync as ps
    from database import db_session
    from routers_holdings import _sync_prices_impl

    ps.clear_quote_cache()
    with db_session() as conn:
        conn.execute("DELETE FROM holdings")
        conn.execute(
            "INSERT INTO holdings (code,name,category,quantity,avg_cost,diluted_cost,total_dividend,last_price) "
            "VALUES ('601288','农业银行','A股权益',1000,6.0,6.0,0,6.88)"
        )
        conn.commit()

    payload = _quote_line("sh601288", "农业银行", "601288", "6.83", "6.88").encode("gbk")

    def fake_get(url, **kwargs):
        if "eastmoney.com" in url:
            raise ConnectionError("Remote end closed connection without response")
        return FakeResp(payload)

    monkeypatch.setattr(ps.requests, "get", fake_get)
    monkeypatch.setattr("kline_cache.sync_klines_for_holdings", lambda conn, *a, **k: {})

    result = _sync_prices_impl(backup=False)

    assert result["status"] == "success"
    assert result["failed"] == []
    assert result["updated"] == 1
    run = [d for d in result["details"] if d["code"] == "601288"][0]
    assert run["new_price"] == 6.83
    assert run["source"] == "腾讯行情"

    with db_session() as conn:
        row = conn.execute("SELECT last_price FROM holdings WHERE code='601288'").fetchone()
    assert float(row["last_price"]) == 6.83
