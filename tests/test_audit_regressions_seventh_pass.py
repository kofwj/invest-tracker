# -*- coding: utf-8 -*-
"""第七轮审计回归：首轮修复后复核发现的问题。

1. period_gain 无基准快照且本期之前已有资金 → 必须返回 None，不得捏数字
2. target_return_pct 单位：前端直接拼 %，必须是 4.0 而不是 0.04
3. TWR/Sharpe 共用同一套现金流剥离日收益（前缀和区间求和）
"""
from performance import _daily_returns, _flow_prefix_sums, _flows_between


# ----------------------------- 问题 1 -----------------------------

def test_period_gain_is_none_without_baseline_and_prior_capital(client):
    """本期之前已有在册资金、却没有起点快照 → 期间收益不可知。

    修复前 period_gain = total_assets(50万) − period_net(1万) = 49万，
    再除以 period_net 报 +4900%，而真实全周期收益是 0%。
    """
    assert client.put("/securities-cash", json={"amount": 0}).status_code == 200
    # 本期之前的资金
    assert client.post(
        "/portfolio-cash-flows",
        json={"date": "2024-01-01", "flow_type": "投入", "amount": 490000},
    ).status_code == 200
    # 本期净投入
    assert client.post(
        "/portfolio-cash-flows",
        json={"date": "2026-08-01", "flow_type": "投入", "amount": 10000},
    ).status_code == 200

    summary = client.get("/performance/summary", params={"start_date": "2026-08-01"}).json()
    assert summary["period_gain"] is None
    assert summary["period_gain_pct"] is None
    # 全周期口径仍然可用，前端据此回退展示
    assert summary["total_gain"] is not None
    assert summary["total_gain_pct"] is not None


def test_period_gain_still_computed_when_all_capital_in_period(client):
    """本期之前没有任何在册资金时，净投入即全部本金，仍可正常算期间收益。"""
    assert client.put("/securities-cash", json={"amount": 0}).status_code == 200
    assert client.post("/transactions", json={
        "date": "2026-01-02", "code": "600111", "name": "回归标的", "category": "A股权益",
        "account": "华泰证券", "direction": "买入", "quantity": 100, "price": 10,
        "amount": 1000, "fee": 0, "remark": "",
    }).status_code == 200
    assert client.post(
        "/portfolio-cash-flows",
        json={"date": "2026-01-01", "flow_type": "投入", "amount": 1000},
    ).status_code == 200

    summary = client.get("/performance/summary", params={"start_date": "2026-01-01"}).json()
    # 全部本金都在本期 → period_net(1000) == net_contribution(1000)，可以算
    assert summary["period_gain"] is not None
    assert summary["period_gain_pct"] is not None


# ----------------------------- 问题 2 -----------------------------

def test_target_return_pct_is_percentage(client):
    """前端 performance.js 直接把该值拼上 '%'，必须是 4.0 而不是 0.04。"""
    summary = client.get("/performance/summary").json()
    assert abs(summary["target_return_pct"] - 4.0) < 1e-9


# ----------------------------- 问题 3 -----------------------------

def test_daily_returns_strip_cash_flows():
    """一次 100 万转入不能被当成行情暴涨（TWR 与 Sharpe 共用此序列）。"""
    rets = _daily_returns(
        [100000.0, 1100000.0],
        dates=["2026-01-01", "2026-01-02"],
        flows_by_date={"2026-01-02": 1000000.0},
    )
    assert len(rets) == 1
    assert abs(rets[0] - 0.0) < 1e-9


def test_daily_returns_keeps_market_move():
    """无现金流时就是普通日收益。"""
    rets = _daily_returns([100.0, 110.0, 121.0])
    assert len(rets) == 2
    assert abs(rets[0] - 0.1) < 1e-9
    assert abs(rets[1] - 0.1) < 1e-9


def test_flows_between_is_half_open_interval():
    """区间为 (lo, hi]：左开右闭，与快照日期约定一致。"""
    dates, cum = _flow_prefix_sums({"2026-01-01": 100.0, "2026-01-05": 50.0, "2026-01-10": -20.0})
    # (01-01, 01-05] 只含 01-05 的 50，不含 01-01 的 100
    assert abs(_flows_between(dates, cum, "2026-01-01", "2026-01-05") - 50.0) < 1e-9
    # 全区间合计 100 + 50 − 20
    assert abs(_flows_between(dates, cum, "2025-12-31", "2026-01-10") - 130.0) < 1e-9
    # 空区间
    assert abs(_flows_between(dates, cum, "2026-01-05", "2026-01-05") - 0.0) < 1e-9


def test_flows_between_handles_empty():
    dates, cum = _flow_prefix_sums({})
    assert _flows_between(dates, cum, "2026-01-01", "2026-01-31") == 0.0
