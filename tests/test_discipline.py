import sqlite3


def test_discipline_report_and_policy(client, app_module):
    # cash + one big holding
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('cash_base', '100000')")
    conn.execute(
        "INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark) VALUES (?,?,?,?,?)",
        ("测试银行", 50000, 2.0, "2027-01-01", "t"),
    )
    conn.commit()
    conn.close()

    r = client.post(
        "/transactions",
        json={
            "date": "2026-01-02",
            "code": "000651",
            "name": "格力电器",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 2000,
            "price": 40,
            "amount": 80000,
            "fee": 0,
            "remark": "",
        },
    )
    assert r.status_code == 200, r.text

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE holdings SET last_price = 40 WHERE code = '000651'")
    conn.commit()
    conn.close()

    report = client.get("/discipline/report")
    assert report.status_code == 200
    data = report.json()
    assert "breaches" in data and isinstance(data["breaches"], list)
    assert "actions" in data and isinstance(data["actions"], list)
    assert "snapshot" in data
    assert "summary" in data
    assert "policy" in data

    policy = client.get("/discipline/policy")
    assert policy.status_code == 200
    assert "equity_max_pct" in policy.json()

    saved = client.put(
        "/discipline/policy",
        json={
            "equity_max_pct": 50,
            "single_holding_max_pct": 15,
            "targets": {"equity_pct": 40, "fixed_income_pct": 30, "deposit_pct": 30},
        },
    )
    assert saved.status_code == 200
    assert saved.json()["policy"]["equity_max_pct"] == 50

    # drafts create (may be 0 if no actions under current numbers)
    created = client.post("/discipline/drafts", json={})
    assert created.status_code == 200
    assert "count" in created.json()

    drafts = client.get("/discipline/drafts?status=draft")
    assert drafts.status_code == 200


def test_discipline_confirm_buy_creates_pending_tx(client, app_module):
    client.post(
        "/discipline/drafts",
        json={
            "actions": [
                {
                    "side": "buy",
                    "code": "159352",
                    "name": "中证A500ETF",
                    "category": "A股ETF",
                    "account": "华泰证券",
                    "amount": 5000,
                    "quantity": 0,
                    "price": 0,
                    "reason": "测试买入草稿",
                }
            ]
        },
    )
    drafts = client.get("/discipline/drafts?status=draft").json()
    assert drafts
    did = drafts[0]["id"]
    conf = client.post(f"/discipline/drafts/{did}/confirm")
    assert conf.status_code == 200
    body = conf.json()
    assert body["direction"] in ("申购待确认", "买入")
    assert body.get("transaction_id")

    # second confirm should fail
    again = client.post(f"/discipline/drafts/{did}/confirm")
    assert again.status_code in (400, 404)
