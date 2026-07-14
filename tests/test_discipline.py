import sqlite3


def _seed_gree_heavy_portfolio(client, app_module, cash_base=200000, deposit=50000, qty=2000, price=40):
    conn = sqlite3.connect(app_module.DB_PATH)
    app_module.set_setting(conn, "securities_cash_base", cash_base)
    # keep displayed securities_cash in sync for any legacy readers
    app_module.set_setting(conn, "securities_cash", cash_base)
    conn.execute(
        "INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark) VALUES (?,?,?,?,?)",
        ("测试银行", deposit, 2.0, "2027-01-01", "t"),
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
            "quantity": qty,
            "price": price,
            "amount": qty * price,
            "fee": 0,
            "remark": "",
        },
    )
    assert r.status_code == 200, r.text

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE holdings SET last_price = ? WHERE code = '000651'", (price,))
    conn.commit()
    conn.close()


def test_discipline_report_and_policy(client, app_module):
    _seed_gree_heavy_portfolio(client, app_module)

    report = client.get("/discipline/report")
    assert report.status_code == 200
    data = report.json()
    assert "breaches" in data and isinstance(data["breaches"], list)
    assert "actions" in data and isinstance(data["actions"], list)
    assert "snapshot" in data
    assert data["snapshot"]["securities_cash"] > 0
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

    # invalid policy: min > max
    bad = client.put("/discipline/policy", json={"equity_min_pct": 60, "equity_max_pct": 40})
    assert bad.status_code == 400

    # invalid targets sum
    bad2 = client.put(
        "/discipline/policy",
        json={"targets": {"equity_pct": 90, "fixed_income_pct": 90, "deposit_pct": 90}},
    )
    assert bad2.status_code == 400

    created = client.post("/discipline/drafts", json={})
    assert created.status_code == 200
    body = created.json()
    assert "count" in body
    assert body["count"] >= 1

    drafts = client.get("/discipline/drafts?status=draft")
    assert drafts.status_code == 200
    assert len(drafts.json()) >= 1


def test_discipline_draft_dedupe_same_code_side(client, app_module):
    _seed_gree_heavy_portfolio(client, app_module)
    first = client.post("/discipline/drafts", json={})
    assert first.status_code == 200
    n1 = first.json()["count"]
    assert n1 >= 1
    ids1 = {d["id"] for d in client.get("/discipline/drafts?status=draft").json()}

    second = client.post("/discipline/drafts", json={})
    assert second.status_code == 200
    assert second.json().get("updated_count", 0) + second.json().get("created_count", 0) >= 1
    ids2 = {d["id"] for d in client.get("/discipline/drafts?status=draft").json()}
    # open drafts should not grow unboundedly for same actions
    assert len(ids2) == len(ids1)
    assert ids2 == ids1


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


def test_discipline_confirm_sell_without_qty_fails(client, app_module):
    client.post(
        "/discipline/drafts",
        json={
            "actions": [
                {
                    "side": "sell",
                    "code": "000651",
                    "name": "格力电器",
                    "category": "A股权益",
                    "account": "华泰证券",
                    "amount": 10000,
                    "quantity": 0,
                    "price": 0,
                    "reason": "无价卖出",
                }
            ]
        },
    )
    drafts = client.get("/discipline/drafts?status=draft").json()
    did = drafts[0]["id"]
    conf = client.post(f"/discipline/drafts/{did}/confirm")
    assert conf.status_code == 400


def test_discipline_update_draft_and_batch_confirm(client, app_module):
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
                    "amount": 3000,
                    "quantity": 0,
                    "price": 0,
                    "reason": "批1",
                },
                {
                    "side": "buy",
                    "code": "518880",
                    "name": "黄金ETF",
                    "category": "黄金",
                    "account": "华泰证券",
                    "amount": 2000,
                    "quantity": 0,
                    "price": 0,
                    "reason": "批2",
                },
            ]
        },
    )
    drafts = client.get("/discipline/drafts?status=draft").json()
    assert len(drafts) >= 2
    d0 = drafts[0]
    upd = client.put(
        f"/discipline/drafts/{d0['id']}",
        json={"amount": 3500, "reason": "手改金额"},
    )
    assert upd.status_code == 200, upd.text
    assert float(upd.json()["draft"]["amount"]) == 3500

    ids = [d["id"] for d in drafts[:2]]
    batch = client.post("/discipline/drafts/confirm", json={"draft_ids": ids})
    assert batch.status_code == 200
    body = batch.json()
    assert body["count"] >= 1


def test_discipline_report_includes_plans_and_help(client, app_module):
    _seed_gree_heavy_portfolio(client, app_module, cash_base=300000, deposit=800000, qty=100, price=40)
    r = client.get("/discipline/report")
    assert r.status_code == 200
    data = r.json()
    assert "plans" in data and isinstance(data["plans"], list)
    assert "help_notes" in data and len(data["help_notes"]) >= 1
    assert any(
        "A500" in (p.get("title") or "") or str(p.get("code") or "").startswith("a500")
        for p in data["plans"]
    )
