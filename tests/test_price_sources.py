"""新浪行情第三源，以及 fetch_eastmoney_quotes 内部的三层兜底链。

背景（生产实测 2026-09-24）：东方财富 push2 与 push2delay 的 /api/qt/* **从这台
服务器的出口**访问不了（两者都直接 RemoteDisconnected；同一时刻在别的网络上是通的，
所以不是接口下线，是这条线路走不通）。后果是 `fetch_eastmoney_quotes` 内部原有的
"腾讯兜底"成了唯一实际生效的路径 —— 腾讯一抽风，日终快照与盘中预警会同时失明。

因此把新浪 hq.sinajs.cn（实测 93ms 可用）接成**第三层**，放在 fetch_eastmoney_quotes
内部而不是新增入口：这样持仓同步、预警、指数、自选所有已有调用点自动获得冗余。

新浪是 GBK 文本：var hq_str_sz000651="名称,今开,昨收,现价,最高,最低,...";
字段 0=名称 1=今开 2=昨收 3=现价。与腾讯不同，新浪不返回涨跌幅，需要自己按昨收算。
"""


import pytest

from test_price_tencent_fallback import FakeResp


def _sina_line(symbol: str, name: str, prev_close: str, price: str) -> str:
    # 0 名称 1 今开 2 昨收 3 现价 4 最高 5 最低
    parts = [name, price, prev_close, price, price, prev_close]
    return f'var hq_str_{symbol}="{",".join(parts)}";'


def _eastmoney_down(monkeypatch, ps):
    """让东财那一层直接连接失败（生产实况），但不影响腾讯/新浪的 mock。"""

    def fake_get(url, **kwargs):
        if "eastmoney.com" in url:
            raise ConnectionError("Remote end closed connection without response")
        raise AssertionError(f"不该请求这个地址: {url}")

    monkeypatch.setattr(ps.requests, "get", fake_get)


def test_fetch_sina_quotes_parses_gbk_payload(monkeypatch):
    import price_sync as ps

    payload = ";".join(
        [
            _sina_line("sh601288", "农业银行", "6.88", "6.83"),
            _sina_line("sz000651", "格力电器", "38.18", "38.36"),
        ]
    ).encode("gbk")
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs.get("headers") or {}))
        return FakeResp(payload)

    monkeypatch.setattr(ps.requests, "get", fake_get)
    quotes = ps.fetch_sina_quotes(["601288", "000651"])

    assert calls and "hq.sinajs.cn/list=" in calls[0][0]
    # 新浪必须带 Referer，否则会被拒
    assert "finance.sina.com.cn" in calls[0][1].get("Referer", "")

    assert quotes["601288"]["price"] == 6.83
    assert quotes["601288"]["name"] == "农业银行"
    assert quotes["601288"]["prev_close"] == 6.88
    assert quotes["601288"]["source"] == "新浪行情"
    # 新浪不给涨跌幅，自己按昨收算，口径与腾讯一致
    assert quotes["601288"]["change_pct"] == pytest.approx(
        round((6.83 / 6.88 - 1) * 100, 2)
    )
    assert quotes["000651"]["price"] == 38.36


def test_fetch_sina_skips_suspended_and_missing_prev_close(monkeypatch):
    import price_sync as ps

    payload = ";".join(
        [
            _sina_line("sh601288", "农业银行", "6.88", "0.00"),  # 停牌/无报价
            _sina_line("sz000651", "格力电器", "0.00", "38.36"),  # 昨收缺失
        ]
    ).encode("gbk")
    monkeypatch.setattr(ps.requests, "get", lambda url, **k: FakeResp(payload))

    quotes = ps.fetch_sina_quotes(["601288", "000651"])

    assert "601288" not in quotes, "停牌标的应被跳过"
    assert quotes["000651"]["price"] == 38.36
    assert quotes["000651"]["prev_close"] is None
    assert quotes["000651"]["change_pct"] is None


def test_fetch_sina_returns_empty_when_request_fails(monkeypatch):
    """兜底路径自己出问题不能反过来把抓价搞崩。"""
    import price_sync as ps

    def boom(url, **kwargs):
        raise ConnectionError("Remote end closed connection without response")

    monkeypatch.setattr(ps.requests, "get", boom)
    assert ps.fetch_sina_quotes(["601288"]) == {}


def test_fetch_sina_ignores_non_market_codes():
    import price_sync as ps

    # 场外基金（f 前缀）与非法代码都不该产生请求
    assert ps.fetch_sina_quotes(["f002864", "", "abc"]) == {}


def test_sina_fills_gap_left_by_tencent(monkeypatch):
    """东财连不上、腾讯只给了一部分 → 剩下的用新浪补齐。"""
    import price_sync as ps

    ps.clear_quote_cache()
    _eastmoney_down(monkeypatch, ps)
    monkeypatch.setattr(
        ps,
        "fetch_tencent_quotes",
        lambda codes: {"601288": {"price": 6.83, "source": "腾讯行情"}},
    )
    monkeypatch.setattr(
        ps,
        "fetch_sina_quotes",
        lambda codes: {"000651": {"price": 38.36, "source": "新浪行情"}},
    )

    quotes = ps.fetch_eastmoney_quotes(["601288", "000651"])

    assert quotes["601288"]["source"] == "腾讯行情"
    assert quotes["000651"]["source"] == "新浪行情"


def test_sina_not_called_when_tencent_covers_everything(monkeypatch):
    """腾讯给全了就不该再打新浪 —— 盘中 3 分钟一轮，白请求会累积成限流风险。"""
    import price_sync as ps

    ps.clear_quote_cache()
    _eastmoney_down(monkeypatch, ps)
    monkeypatch.setattr(
        ps,
        "fetch_tencent_quotes",
        lambda codes: {"601288": {"price": 6.83, "source": "腾讯行情"}},
    )
    sina_calls = []
    monkeypatch.setattr(
        ps, "fetch_sina_quotes", lambda codes: sina_calls.append(list(codes)) or {}
    )

    quotes = ps.fetch_eastmoney_quotes(["601288"])

    assert quotes["601288"]["price"] == 6.83
    assert sina_calls == []


def test_sina_fills_gap_left_by_eastmoney_and_tencent(monkeypatch):
    """东财与腾讯都取不到时，新浪是最后一层。"""
    import price_sync as ps

    ps.clear_quote_cache()
    _eastmoney_down(monkeypatch, ps)
    monkeypatch.setattr(ps, "fetch_tencent_quotes", lambda codes: {})
    monkeypatch.setattr(
        ps,
        "fetch_sina_quotes",
        lambda codes: {"601288": {"price": 6.83, "source": "新浪行情"}},
    )

    quotes = ps.fetch_eastmoney_quotes(["601288"])

    assert quotes["601288"]["price"] == 6.83
    assert quotes["601288"]["source"] == "新浪行情"


def test_chain_returns_empty_when_all_sources_fail(monkeypatch):
    """三层全失败返回空 dict，且不抛异常（上层语义是"取不到价 → 保留旧价"）。"""
    import price_sync as ps

    ps.clear_quote_cache()
    _eastmoney_down(monkeypatch, ps)

    def boom(codes):
        raise ConnectionError("down")

    monkeypatch.setattr(ps, "fetch_tencent_quotes", boom)
    monkeypatch.setattr(ps, "fetch_sina_quotes", boom)

    assert ps.fetch_eastmoney_quotes(["601288", "000651"]) == {}


def test_sina_layer_failure_does_not_break_chain(monkeypatch):
    """新浪自己抛异常也不能把已经拿到的腾讯价弄丢。"""
    import price_sync as ps

    ps.clear_quote_cache()
    _eastmoney_down(monkeypatch, ps)
    monkeypatch.setattr(
        ps,
        "fetch_tencent_quotes",
        lambda codes: {"601288": {"price": 6.83, "source": "腾讯行情"}},
    )

def test_chain_handles_empty_input():
    """空输入直接返回空，不该打任何请求。"""
    from price_sync import fetch_eastmoney_quotes, fetch_sina_quotes, fetch_stock_quotes

    assert fetch_eastmoney_quotes([]) == {}
    assert fetch_sina_quotes([]) == {}
    assert fetch_stock_quotes([]) == {}
