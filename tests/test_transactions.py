import sqlite3


def test_add_transaction_updates_holdings_and_securities_cash(client, app_module):
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    app_module.set_setting(conn, "securities_cash_base", 10000)
    conn.commit()
    conn.close()

    resp = client.post(
        "/transactions",
        json={
            "date": "2026-05-19",
            "code": "600000",
            "name": "浦发银行",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 100,
            "price": 10,
            "amount": 1000,
            "fee": 5,
            "remark": "test buy",
        },
    )
    assert resp.status_code == 200

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT code, quantity, avg_cost FROM holdings WHERE code = ?", ("600000",)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["quantity"] == 100
    assert row["avg_cost"] == 10.05

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["securities_cash"] == 8995.0
    assert data["holdings_count"] == 1


def test_update_transaction_recalculates_holdings(client, app_module):
    create_resp = client.post(
        "/transactions",
        json={
            "date": "2026-05-19",
            "code": "600002",
            "name": "测试编辑股票",
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
    assert create_resp.status_code == 200

    txs = client.get("/transactions?legacy=1").json()
    tx_id = next(t["id"] for t in txs if t["code"] == "600002")

    update_resp = client.put(
        f"/transactions/{tx_id}",
        json={"quantity": 200, "amount": 2200, "price": 11},
    )
    assert update_resp.status_code == 200

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT quantity, avg_cost FROM holdings WHERE code = ?", ("600002",)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["quantity"] == 200
    assert row["avg_cost"] == 11.0


def test_delete_transaction_recalculates_holdings(client, app_module):
    create_resp = client.post(
        "/transactions",
        json={
            "date": "2026-05-19",
            "code": "600001",
            "name": "测试股票",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 50,
            "price": 20,
            "amount": 1000,
            "fee": 0,
            "remark": "",
        },
    )
    assert create_resp.status_code == 200

    txs = client.get("/transactions?legacy=1").json()
    tx_id = next(t["id"] for t in txs if t["code"] == "600001")

    delete_resp = client.delete(f"/transactions/{tx_id}")
    assert delete_resp.status_code == 200

    conn = sqlite3.connect(app_module.DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM holdings WHERE code = ?", ("600001",)
    ).fetchone()[0]
    conn.close()
    assert count == 0


def test_dividend_reinvestment_updates_holdings_without_cash_change(client, app_module):
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    app_module.set_setting(conn, "securities_cash_base", 10000)
    conn.commit()
    conn.close()

    resp = client.post(
        "/transactions",
        json={
            "date": "2026-05-28",
            "code": "f002864",
            "name": "广发安泽短债债券A",
            "category": "债基",
            "account": "支付宝",
            "direction": "分红再投资",
            "quantity": 623.5524,
            "price": 1.05,
            "amount": 654.73,
            "fee": 0,
            "remark": "test dividend reinvestment",
        },
    )
    assert resp.status_code == 200

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT quantity, avg_cost, diluted_cost, total_dividend FROM holdings WHERE code = ?",
        ("f002864",),
    ).fetchone()
    conn.close()

    assert row is not None
    assert round(row["quantity"], 4) == 623.5524
    assert round(row["avg_cost"], 4) == 1.05
    assert round(row["diluted_cost"], 4) == 0.0
    assert round(row["total_dividend"], 2) == 654.73

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["securities_cash"] == 10000.0
    assert data["holdings_count"] == 1


def test_oversell_is_rejected(client, app_module):
    buy = client.post(
        "/transactions",
        json={
            "date": "2026-05-19",
            "code": "600010",
            "name": "包钢股份",
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
    assert buy.status_code == 200

    sell = client.post(
        "/transactions",
        json={
            "date": "2026-05-20",
            "code": "600010",
            "name": "包钢股份",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "卖出",
            "quantity": 150,
            "price": 11,
            "amount": 1650,
            "fee": 0,
            "remark": "",
        },
    )
    assert sell.status_code == 400
    assert "超过当前持仓" in sell.json()["detail"]


def test_invalid_direction_rejected_on_add(client):
    resp = client.post(
        "/transactions",
        json={
            "date": "2026-05-19",
            "code": "600000",
            "name": "浦发银行",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "乱写",
            "quantity": 100,
            "price": 10,
            "amount": 1000,
            "fee": 0,
            "remark": "",
        },
    )
    assert resp.status_code == 400
    assert "方向必须是" in resp.json()["detail"]


def test_list_transactions_returns_pending_meta(client, app_module):
    client.post(
        "/transactions",
        json={
            "date": "2026-05-19",
            "code": "f004388",
            "name": "鹏华丰享",
            "category": "债基",
            "account": "华泰证券",
            "direction": "申购待确认",
            "quantity": 0,
            "price": 0,
            "amount": 3000,
            "fee": 0,
            "remark": "",
        },
    )
    resp = client.get("/transactions?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["pending_count"] == 1
    assert data["pending_amount"] == 3000.0

    pending = client.get("/transactions?direction=pending&page=1&page_size=10")
    assert pending.status_code == 200
    assert pending.json()["total"] == 1
