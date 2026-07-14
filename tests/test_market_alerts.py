import sqlite3


def test_alert_rule_crud_and_check_triggers(client, app_module, monkeypatch):
    # Create holding via transaction so market summary has portfolio context
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
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE holdings SET last_price = 12 WHERE code = '600000'")
    conn.commit()
    conn.close()

    # Stub network quotes used by market module
    def fake_quotes(codes, secid_map=None):
        out = {}
        for c in codes:
            code = str(c).strip()
            if code == "600000":
                out[code] = {"price": 12.5, "change_pct": 1.2, "name": "浦发银行"}
            elif code == "000300":
                out[code] = {"price": 3800.0, "change_pct": -0.5, "name": "沪深300"}
            elif code == "000001":
                out[code] = {"price": 3100.0, "change_pct": -0.3, "name": "上证指数"}
            else:
                out[code] = {"price": 100.0, "change_pct": 0.0, "name": code}
        return out

    monkeypatch.setattr("market.fetch_eastmoney_quotes", fake_quotes)
    monkeypatch.setattr("price_sync.fetch_eastmoney_quotes", fake_quotes)

    bad = client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "condition": "sideways",
            "threshold": 12,
        },
    )
    assert bad.status_code == 400

    created = client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "name": "浦发银行",
            "condition": "above",
            "threshold": 12.0,
            "enabled": True,
        },
    )
    assert created.status_code == 200
    rule = created.json()["rule"]
    assert rule["code"] == "600000"
    rule_id = rule["id"]

    listed = client.get("/market/alert-rules")
    assert listed.status_code == 200
    assert any(r["id"] == rule_id for r in listed.json())

    # price 12.5 >= 12 → trigger
    checked = client.post("/market/alerts/check")
    assert checked.status_code == 200
    body = checked.json()
    assert body["checked_count"] == 1
    assert body["trigger_count"] == 1
    assert body["triggered"][0]["code"] == "600000"

    # Raise threshold so it no longer triggers
    updated = client.put(
        f"/market/alert-rules/{rule_id}",
        json={"threshold": 20.0},
    )
    assert updated.status_code == 200
    checked2 = client.post("/market/alerts/check")
    assert checked2.json()["trigger_count"] == 0

    # Summary works with stubbed quotes
    summary = client.get("/market/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert "indices" in data
    assert "signals" in data
    assert any(i["code"] == "000300" for i in data["indices"])

    deleted = client.delete(f"/market/alert-rules/{rule_id}")
    assert deleted.status_code == 200
    assert client.get("/market/alert-rules").json() == []


def test_market_summary_graceful_when_quote_fails(client, app_module, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("network down")

    monkeypatch.setattr("market.fetch_eastmoney_quotes", boom)

    res = client.get("/market/summary")
    assert res.status_code == 200
    data = res.json()
    assert "indices" in data
    assert data.get("index_error")
    assert "signals" in data
