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


def test_resolve_symbol_prefers_secid_override():
    """指数兜底必须认 secid：000001 是上证指数（1.000001），不能按股票口径猜成 sz000001。"""
    from price_sync import resolve_symbol, symbol_from_secid

    assert symbol_from_secid("1.000001") == "sh000001"
    assert symbol_from_secid("0.399001") == "sz399001"
    assert symbol_from_secid("") == "" and symbol_from_secid("1.00001") == ""

    assert resolve_symbol("000001", {"000001": "1.000001"}) == "sh000001"   # 上证指数
    assert resolve_symbol("000510", {"000510": "1.000510"}) == "sh000510"   # 中证A500
    assert resolve_symbol("000300", {"000300": "1.000300"}) == "sh000300"   # 沪深300
    assert resolve_symbol("399006", {"399006": "0.399006"}) == "sz399006"   # 创业板指
    # 没有覆盖时仍按原口径（股票/ETF 走 tencent_symbol）
    assert resolve_symbol("000001") == "sz000001"
    assert resolve_symbol("601288") == "sh601288"


def test_fallback_uses_the_index_secid_not_the_bare_code(monkeypatch):
    """东财挂了走兜底时，指数要请求 sh000001 / sh000510 ——
    修前传的是裸代码，兜底按"非 6/5 开头=深市"猜前缀，于是
    上证指数被取成 sz000001 平安银行、中证A500 被取成 sz000510 新金路、
    沪深300 取 sz000300 直接落空（界面上就是"—"）。"""
    import price_sync as ps

    ps.clear_quote_cache()
    payload = ";".join([
        _quote_line("sh000001", "上证指数", "000001", "3830.45", "3823.62"),
        _quote_line("sh000510", "中证A500", "000510", "5360.18", "5348.50"),
        _quote_line("sh000300", "沪深300", "000300", "4345.21", "4340.76"),
    ]).encode("gbk")
    urls = []

    def fake_get(url, **kwargs):
        urls.append(url)
        if "eastmoney.com" in url:
            raise ConnectionError("Remote end closed connection without response")
        return FakeResp(payload)

    monkeypatch.setattr(ps.requests, "get", fake_get)
    quotes = ps.fetch_eastmoney_quotes(
        ["000001", "000510", "000300"],
        secid_map={"000001": "1.000001", "000510": "1.000510", "000300": "1.000300"},
    )

    gtimg = [u for u in urls if "gtimg" in u][0]
    assert "sh000001" in gtimg and "sh000510" in gtimg and "sh000300" in gtimg
    # 关键：不许再拿同号的深市个股顶包
    assert "sz000001" not in gtimg and "sz000510" not in gtimg and "sz000300" not in gtimg
    assert quotes["000001"]["name"] == "上证指数" and quotes["000001"]["price"] == 3830.45
    assert quotes["000510"]["name"] == "中证A500"
    assert quotes["000300"]["name"] == "沪深300" and quotes["000300"]["price"] == 4345.21


def test_key_indices_screen_shows_the_real_index(app_module, monkeypatch):
    """端到端（决策页「关键指数」那一屏）：东财挂了也不许把上证指数显示成平安银行。"""
    import price_sync as ps
    from market import build_market_summary

    ps.clear_quote_cache()
    payload = ";".join([
        _quote_line("sh000001", "上证指数", "000001", "3830.45", "3823.62"),
        _quote_line("sh000510", "中证A500", "000510", "5360.18", "5348.50"),
        _quote_line("sh000300", "沪深300", "000300", "4345.21", "4340.76"),
    ]).encode("gbk")

    def fake_get(url, **kwargs):
        if "eastmoney.com" in url:
            raise ConnectionError("Remote end closed connection without response")
        return FakeResp(payload)

    monkeypatch.setattr(ps.requests, "get", fake_get)
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        rows = {row["code"]: row for row in build_market_summary(conn)["indices"]}

    assert rows["000001"]["name"] == "上证指数"      # 修前是"平安银行"
    assert rows["000001"]["price"] == 3830.45       # 修前是平安银行的 11.35
    assert rows["000510"]["name"] == "中证A500"     # 修前是"新金路"
    assert rows["000300"]["available"] is True      # 修前取不到，"—"
    assert rows["000300"]["price"] == 4345.21
