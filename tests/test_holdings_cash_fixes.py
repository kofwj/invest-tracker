import sqlite3


def test_update_expected_return(client, app_module):
    client.post(
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
            "fee": 0,
            "remark": "",
        },
    )
    resp = client.put("/holdings/600000", json={"expected_return": 6.5})
    assert resp.status_code == 200

    holdings = client.get("/holdings").json()
    row = next(h for h in holdings if h["code"] == "600000")
    assert row["expected_return"] == 6.5


def test_holding_correction_roundtrip(client, app_module):
    client.post(
        "/transactions",
        json={
            "date": "2026-01-01",
            "code": "601288",
            "name": "农业银行",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 1000,
            "price": 5,
            "amount": 5000,
            "fee": 0,
            "remark": "",
        },
    )
    corr = client.post(
        "/holding-corrections",
        json={
            "date": "2026-05-01",
            "code": "601288",
            "name": "农业银行",
            "category": "A股权益",
            "actual_quantity": 1200,
            "actual_avg_cost": 4.5,
            "actual_total_dividend": 100,
            "remark": "broker snapshot",
        },
    )
    assert corr.status_code == 200
    corr_id = corr.json()["id"]

    holdings = client.get("/holdings").json()
    row = next(h for h in holdings if h["code"] == "601288")
    assert row["quantity"] == 1200
    assert abs(row["avg_cost"] - 4.5) < 1e-9
    assert abs(row["total_dividend"] - 100) < 1e-9

    listed = client.get("/holding-corrections?code=601288").json()
    assert len(listed) == 1
    assert listed[0]["id"] == corr_id

    deleted = client.delete(f"/holding-corrections/{corr_id}")
    assert deleted.status_code == 200

    holdings2 = client.get("/holdings").json()
    row2 = next(h for h in holdings2 if h["code"] == "601288")
    assert row2["quantity"] == 1000


def test_cash_flow_type_only_update_renormalizes_amount(client, app_module):
    conn = sqlite3.connect(app_module.DB_PATH)
    app_module.set_setting(conn, "securities_cash_base", 10000)
    conn.commit()
    conn.close()

    created = client.post(
        "/cash-flows",
        json={
            "date": "2026-05-19",
            "account": "华泰证券",
            "flow_type": "银证转入",
            "amount": 1000,
            "remark": "in",
        },
    )
    assert created.status_code == 200
    flow_id = created.json()["id"]
    assert created.json()["amount"] == 1000

    dash1 = client.get("/dashboard").json()
    assert dash1["securities_cash"] == 11000

    updated = client.put(f"/cash-flows/{flow_id}", json={"flow_type": "银证转出"})
    assert updated.status_code == 200
    assert updated.json()["normalized_amount"] == -1000

    dash2 = client.get("/dashboard").json()
    assert dash2["securities_cash"] == 9000
