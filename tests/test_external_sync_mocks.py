"""Mock 测试：外部依赖（东财行情 / 天天基金净值 / 新浪基金分红 / 东财分红接口）。

这些测试不打真实网络，用 unittest.mock 固定返回值，验证：
1. price_sync.fetch_eastmoney_quotes 正确解析东财返回、优雅处理空/坏台数据
2. price_sync.fetch_eastmoney_prices 对网络失败降级返回空 dict
3. _sync_prices_impl 写入路径：行情同步正确更新 holdings.last_price（含基金猜测源分支）
4. dividend_sync 新浪/东财分红解析 + 空接口降级

注意：conftest.app_module 会 reload 整个 backend 模块链并指向 tmp DB，故 backend 模块一律
在函数内 import，确保拿到的是 reload 后的实例、patch 到对的模块对象。
"""
from unittest import mock

import pytest


# ---------- 1. 东财行情解析 ----------

def test_eastmoney_quotes_parses_and_derives_change(monkeypatch):
    import price_sync as ps

    fake_resp = mock.Mock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "data": {
            "diff": [
                {"f12": "600519", "f14": "贵州茅台", "f2": "1000.0", "f3": "1.2", "f18": "988.0"},
                {"f12": "000001", "f14": "平安银行", "f2": "11.5", "f3": "-", "f18": "11.0"},
                {"f12": "999999", "f14": "坏行情", "f2": "-", "f3": "-", "f18": "1.0"},
            ]
        },
        "rc": 0,
    }
    with mock.patch.object(ps, "requests") as mock_req, mock.patch.object(ps, "_CACHE_TTL", 0):
        mock_req.get.return_value = fake_resp
        quotes = ps.fetch_eastmoney_quotes(["600519", "000001", "999999"])

    # 正常价 + 变动率
    assert quotes["600519"]["price"] == 1000.0
    assert quotes["600519"]["change_pct"] == 1.2
    # 缺 change 但昨收有 → 推导
    assert quotes["000001"]["price"] == 11.5
    assert quotes["000001"]["change_pct"] == pytest.approx((11.5 / 11.0 - 1) * 100)
    # 坏价("-") → 丢弃
    assert "999999" not in quotes


def test_eastmoney_quotes_missing_data_returns_empty(monkeypatch):
    import price_sync as ps

    fake_resp = mock.Mock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {"data": None}  # 接口空返回
    with mock.patch.object(ps, "requests") as mock_req, mock.patch.object(ps, "_CACHE_TTL", 0):
        mock_req.get.return_value = fake_resp
        quotes = ps.fetch_eastmoney_quotes(["600519"])
    assert quotes == {}


def test_eastmoney_prices_survives_network_error(monkeypatch):
    import price_sync as ps

    with mock.patch.object(ps, "requests") as mock_req, mock.patch.object(ps, "_CACHE_TTL", 0):
        mock_req.get.side_effect = Exception("connection refused")
        # 网络失败 → 异常上抛（由 _sync_prices_impl 顶层 catch 或跳过），不进缓存、不吞
        with pytest.raises(Exception):
            ps.fetch_eastmoney_prices(["600519"])


# ---------- 2. 同步入口写入路径 ----------

def test_sync_prices_impl_updates_holdings(app_module, monkeypatch):
    """mock 掉东财/基金净值/k线，验证同步主循环正确写 DB。"""
    from routers_holdings import _sync_prices_impl
    from database import db_session

    # 造两条持仓：一条普通股(6位)、一条基(F开头)
    with db_session() as conn:
        conn.execute("DELETE FROM holdings")
        conn.execute(
            "INSERT INTO holdings (code,name,category,quantity,avg_cost,diluted_cost,total_dividend,last_price) "
            "VALUES ('600519','贵州茅台','A股权益',100,900,900,0,900.0)"
        )
        conn.execute(
            "INSERT INTO holdings (code,name,category,quantity,avg_cost,diluted_cost,total_dividend,last_price) "
            "VALUES ('f002001','华夏成长','债基',1000,1.0,1.0,0,1.0)"
        )
        conn.commit()

    def fake_eastmoney_prices(codes):
        # _sync_prices_impl 调用 fetch_eastmoney_prices(codes)，返回扁平 {code: price}
        # 只有普通股走这里；基金码 f002001 在下方代码走 fetch_open_fund_nav
        return {"600519": 1050.0}

    def fake_fund_nav(code):
        return 1.10

    monkeypatch.setattr("routers_holdings.fetch_eastmoney_prices", fake_eastmoney_prices)
    monkeypatch.setattr("routers_holdings.fetch_open_fund_nav", fake_fund_nav)
    # 尾部的 kline 增量同步是真实网络，直接 patch kline_cache 源码避免联外
    monkeypatch.setattr("kline_cache.sync_klines_for_holdings", lambda conn, *a, **k: {})

    result = _sync_prices_impl(backup=False)

    assert result["status"] == "success"
    assert result["updated"] == 2
    assert result["checked"] == 2
    assert not result["failed"]

    with db_session() as conn:
        rows = {r["code"]: r["last_price"] for r in conn.execute("SELECT code,last_price FROM holdings")}
    assert rows["600519"] == 1050.0
    assert rows["f002001"] == 1.10


def test_sync_prices_impl_handles_missing_quotes(app_module, monkeypatch):
    """行情缺失 → 进 failed，不炸库。"""
    from routers_holdings import _sync_prices_impl
    from database import db_session

    with db_session() as conn:
        conn.execute("DELETE FROM holdings")
        conn.execute(
            "INSERT INTO holdings (code,name,category,quantity,avg_cost,diluted_cost,total_dividend,last_price) "
            "VALUES ('600000','浦发银行','A股权益',100,10,10,0,10.0)"
        )
        conn.commit()

    monkeypatch.setattr("routers_holdings.fetch_eastmoney_prices", lambda codes: {})
    monkeypatch.setattr("routers_holdings.fetch_open_fund_nav", lambda code: None)
    # kline 增量同步在函数内 `from .kline_cache import sync_klines_for_holdings`，
    # 需 patch 源模块函数（函数内 import 取的是 kline_cache.sync_klines_for_holdings）
    monkeypatch.setattr("kline_cache.sync_klines_for_holdings", lambda conn, *a, **k: {})

    result = _sync_prices_impl(backup=False)
    assert result["status"] == "success"
    assert result["failed"] and result["failed"][0]["code"] == "600000"
    assert result["updated"] == 0


# ---------- 3. 分红同步（新浪 / 东财） ----------

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_sina_fund_dividends_parses(monkeypatch):
    import dividend_sync as ds

    payload = {
        "result": {
            "status": {"code": 0, "msg": "ok"},
            "data": {
                "fhdata": [
                    {"djr": "2026-06-20", "fhr": "2026-06-24", "mffh": "0.05"},
                    {"djr": "2025-12-10", "fhr": "2025-12-15", "mffh": "0.0"},  # 0 分红 → 丢弃
                    {"djr": "", "fhr": "", "mffh": "0.1"},  # 无日期 → 丢弃
                ]
            },
        }
    }
    monkeypatch.setattr(ds, "_HTTP_CACHE", {})  # 清空缓存，强制走 http
    with mock.patch.object(ds._HTTP_SESSION, "get", return_value=_FakeResp(payload)):
        rows = ds.fetch_sina_fund_dividends("510880", page_size=40)

    assert len(rows) == 1
    row = rows[0]
    assert row["SECURITY_CODE"] == "510880"
    assert row["_source"] == "sina_fund_fh"
    assert row["PRETAX_BONUS_RMB"] == 0.5  # 每份0.05 → 每10份0.5
    assert row["EX_DIVIDEND_DATE"] == "2026-06-24"


def test_eastmoney_share_bonus_empty_result(monkeypatch):
    import dividend_sync as ds

    payload = {"result": None}  # 空
    monkeypatch.setattr(ds, "_HTTP_CACHE", {})
    with mock.patch.object(ds._HTTP_SESSION, "get", return_value=_FakeResp(payload)):
        rows = ds.fetch_eastmoney_share_bonus("601398")
    assert rows == []


def test_sina_dividends_network_error_degrades(monkeypatch):
    import dividend_sync as ds

    monkeypatch.setattr(ds, "_HTTP_CACHE", {})
    with mock.patch.object(ds._HTTP_SESSION, "get", side_effect=Exception("conn reset")):
        # 单测声明接口异常会上抛（调用方 build_draft 会 catch 并跳过）
        with pytest.raises(Exception):
            ds.fetch_sina_fund_dividends("510880")