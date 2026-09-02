# -*- coding: utf-8 -*-
"""第五轮审计回归：P0 四条财务计算 bug。

1. period_gain_pct 无快照退化的分母错误（恒 100%）
2. calculate_twr 未剥离现金流
3. 清仓后分红未重置，泄漏到下一轮建仓
4. 券商「摊薄成本」被当未摊薄成本，分红扣两次
"""
import sqlite3

from broker_reconcile import compare_holdings, parse_broker_csv_text
from performance import calculate_twr


def _tx(code, direction, *, quantity=100, price=10, amount=None, fee=0, date="2026-01-02"):
    if amount is None:
        amount = quantity * price
    return {
        "date": date,
        "code": code,
        "name": "回归标的",
        "category": "A股权益",
        "account": "华泰证券",
        "direction": direction,
        "quantity": quantity,
        "price": price,
        "amount": amount,
        "fee": fee,
        "remark": "",
    }


# ----------------------------- bug 1 -----------------------------

def test_period_gain_pct_fallback_uses_net_invested(client, app_module):
    assert client.put("/securities-cash", json={"amount": 0}).status_code == 200
    assert client.post("/transactions", json=_tx("600111", "买入")).status_code == 200
    # 手动抬高最新价 → 市值 1100，证券现金 -1000 → 总资产 100
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE holdings SET last_price = 11 WHERE code = '600111'")
    conn.commit()
    conn.close()
    assert client.post(
        "/portfolio-cash-flows",
        json={"date": "2026-01-01", "flow_type": "投入", "amount": 1000},
    ).status_code == 200

    summary = client.get("/performance/summary", params={"start_date": "2026-01-01"}).json()
    # 无快照：period_gain = 100 - 1000 = -900；正确基 = 净投入 1000 → -90%
    assert summary["period_gain"] == -900.0
    assert summary["period_gain_pct"] == -90.0


# ----------------------------- bug 2 -----------------------------

def test_twr_strips_external_cash_flows():
    # 纯存 100 万：总资产 [10万, 110万] 但当天存入 100 万 → 真实收益 0，不能报 +1000%
    twr, status = calculate_twr(
        [100000, 1100000],
        dates=["2026-01-01", "2026-01-02"],
        flows_by_date={"2026-01-02": 1000000.0},
    )
    assert status == "ok"
    assert abs(twr - 0.0) < 1e-6


def test_twr_equals_simple_return_without_flows():
    twr, status = calculate_twr([100, 110])
    assert status == "ok"
    assert abs(twr - 10.0) < 1e-6


def test_twr_geometric_chain():
    twr, _ = calculate_twr([100, 110, 121])
    assert abs(twr - 21.0) < 1e-6


# ----------------------------- bug 3 -----------------------------

def test_dividend_reset_on_full_exit_then_rebuy(client):
    code = "600222"
    assert client.post("/transactions", json=_tx(code, "买入", date="2026-01-02")).status_code == 200
    assert client.post(
        "/transactions",
        json=_tx(code, "分红", quantity=0, price=0, amount=500, date="2026-02-02"),
    ).status_code == 200
    # 全部卖出清零
    assert client.post(
        "/transactions",
        json=_tx(code, "卖出", amount=1000, date="2026-03-02"),
    ).status_code == 200
    # 重新建仓
    assert client.post(
        "/transactions",
        json=_tx(code, "买入", date="2026-04-02"),
    ).status_code == 200

    row = next(h for h in client.get("/holdings").json() if h["code"] == code)
    assert float(row["quantity"]) == 100
    assert float(row["total_dividend"]) == 0.0


# ----------------------------- bug 4 -----------------------------

def test_broker_diluted_cost_reconstructed_to_raw():
    # 摊薄成本 9.5 + 累计分红 500、数量 100 → 还原未摊薄 = 9.5 + 500/100 = 14.5
    text = "证券代码,证券名称,证券数量,摊薄成本,累计分红\n600333,回归标的,100,9.5,500\n"
    rows, meta = parse_broker_csv_text(text)
    assert meta.get("cost_is_diluted") is True
    assert abs(rows[0]["avg_cost"] - 14.5) < 1e-9
    assert abs(rows[0]["total_dividend"] - 500.0) < 1e-9


def test_broker_raw_cost_untouched():
    text = "证券代码,证券名称,证券数量,成本价,累计分红\n600444,回归标的,100,10.5,12\n"
    rows, meta = parse_broker_csv_text(text)
    assert meta.get("cost_is_diluted") is False
    assert abs(rows[0]["avg_cost"] - 10.5) < 1e-9


def test_broker_diluted_cost_without_dividend_no_app_fallback():
    # 摊薄成本已扣分红但券商未给分红列 → 不得回填系统分红（否则双重扣减）
    broker = [
        {"code": "600555", "name": "回归标的", "quantity": 100, "avg_cost": 9.5, "total_dividend": None, "cost_is_diluted": True},
    ]
    app = [
        {"code": "600555", "name": "回归标的", "quantity": 100, "avg_cost": 10.0, "total_dividend": 500, "category": "A股权益"},
    ]
    result = compare_holdings(broker, app, as_of_date="2026-07-14")
    sug = next(s for s in result["suggestions"] if s["code"] == "600555")
    assert sug["actual_total_dividend"] == 0.0