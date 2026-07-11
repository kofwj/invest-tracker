import sqlite3


def test_dashboard_and_performance_share_lifetime_profit(client, app_module):
    client.post(
        "/transactions",
        json={
            "date": "2026-01-02",
            "code": "600000",
            "name": "浦发银行",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 100,
            "price": 10,
            "amount": 1000,
            "fee": 0,
            "remark": "",
        },
    )
    client.post(
        "/transactions",
        json={
            "date": "2026-03-01",
            "code": "600000",
            "name": "浦发银行",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "分红",
            "quantity": 0,
            "price": 0,
            "amount": 50,
            "fee": 0,
            "remark": "",
        },
    )
    # set last_price via SQL for deterministic profit
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE holdings SET last_price = 12 WHERE code = '600000'")
    conn.commit()
    conn.close()

    dash = client.get("/dashboard").json()
    perf = client.get("/performance/summary").json()
    # float: (12-10)*100 + 50 = 250
    # lifetime diluted: net_invested = 1000-50 = 950, diluted=9.5, (12-9.5)*100=250
    assert abs(dash["total_profit"] - 250) < 1e-6
    assert abs(dash["lifetime_profit"] - 250) < 1e-6
    assert abs(perf["lifetime_profit"] - 250) < 1e-6


def test_holding_lifetime_profit_diluted_fallback():
    from portfolio_totals import holding_lifetime_profit

    # diluted missing -> use avg_cost
    row = {"quantity": 10, "last_price": 12, "avg_cost": 10, "diluted_cost": None}
    assert abs(holding_lifetime_profit(row) - 20) < 1e-9
    row2 = {"quantity": 10, "last_price": 12, "avg_cost": 10, "diluted_cost": 9}
    assert abs(holding_lifetime_profit(row2) - 30) < 1e-9
