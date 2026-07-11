import sqlite3


def test_pending_purchase_is_counted_once_in_dashboard(client, app_module):
    conn = sqlite3.connect(app_module.DB_PATH)
    app_module.set_setting(conn, "securities_cash", 10000)
    app_module.set_setting(conn, "securities_cash_base", 10000)
    conn.commit()
    conn.close()

    resp = client.post(
        "/transactions",
        json={
            "date": "2026-05-19",
            "code": "110001",
            "name": "待确认申购",
            "category": "债券",
            "account": "华泰证券",
            "direction": "申购待确认",
            "quantity": 0,
            "price": 1,
            "amount": 3000,
            "fee": 0,
            "remark": "",
        },
    )
    assert resp.status_code == 200

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["pending_purchase"] == 3000.0
    assert data["pending_count"] == 1
    assert data["securities_cash"] == 7000.0
    assert data["total_assets"] == 10000.0


def test_dashboard_total_assets_matches_market_cash_bank_and_pending(client, app_module):
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    app_module.set_setting(conn, "securities_cash_base", 5000)
    conn.execute(
        "INSERT INTO holdings (code, name, category, quantity, avg_cost, diluted_cost, total_dividend, last_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("600010", "包钢股份", "A股权益", 100, 8.0, 8.0, 0, 12.0),
    )
    conn.execute(
        "INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark) VALUES (?, ?, ?, ?, ?)",
        ("招商银行", 2000, 1.5, "2026-12-31", "test deposit"),
    )
    conn.execute(
        "INSERT INTO transactions (date, code, name, category, account, direction, quantity, price, amount, fee, remark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("2026-05-19", "110002", "待确认申购2", "债券", "华泰证券", "待确认申购", 0, 1, 500, 0, ""),
    )
    conn.commit()
    conn.close()

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["total_market_value"] == 1200.0
    assert data["bank_balance"] == 2000.0
    assert data["pending_purchase"] == 500.0
    assert data["pending_count"] == 1
    assert data["securities_cash"] == 4500.0
    assert data["total_assets"] == 8200.0
