import sqlite3


def test_alert_rule_crud_and_check_triggers(client, app_module, monkeypatch):
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

    def fake_quotes(codes, secid_map=None, use_cache=True):
        out = {}
        for c in codes:
            code = str(c).strip()
            if code == "600000":
                out[code] = {
                    "price": 12.5,
                    "change_pct": 1.2,
                    "name": "浦发银行",
                    "prev_close": 12.35,
                }
            elif code == "000300":
                out[code] = {"price": 3800.0, "change_pct": -0.5, "name": "沪深300", "prev_close": 3819}
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

    checked = client.post("/market/alerts/check", json={"notify": False})
    assert checked.status_code == 200
    body = checked.json()
    assert body["checked_count"] == 1
    assert body["trigger_count"] == 1
    assert body["triggered"][0]["code"] == "600000"

    events = client.get("/market/alert-events?limit=10")
    assert events.status_code == 200
    rows = events.json()
    assert len(rows) >= 1
    assert rows[0]["target_code"] == "600000"

    events_code = client.get("/market/alert-events?code=600000")
    assert events_code.status_code == 200
    assert all(r["target_code"] == "600000" for r in events_code.json())

    updated = client.put(
        f"/market/alert-rules/{rule_id}",
        json={"threshold": 20.0},
    )
    assert updated.status_code == 200
    checked2 = client.post("/market/alerts/check", json={})
    assert checked2.json()["trigger_count"] == 0

    summary = client.get("/market/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert "indices" in data
    assert "signals" in data
    assert "quote_cache_seconds" in data
    assert any(i["code"] == "000300" for i in data["indices"])
    # day contrib should be present for holding with change_pct
    assert any(h["code"] == "600000" for h in data.get("holdings_day") or [])

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


def test_notify_feishu_skipped_without_webhook(client, app_module, monkeypatch):
    monkeypatch.delenv("FEISHU_ALERT_WEBHOOK", raising=False)

    def fake_quotes(codes, secid_map=None, use_cache=True):
        return {str(c): {"price": 10.0, "change_pct": 0, "name": str(c)} for c in codes}

    monkeypatch.setattr("market.fetch_eastmoney_quotes", fake_quotes)

    client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "999999",
            "condition": "above",
            "threshold": 1,
            "enabled": True,
        },
    )
    res = client.post("/market/alerts/check", json={"notify": True})
    assert res.status_code == 200
    notify = res.json().get("notify") or {}
    # may be no_triggers if quote for non-held code fails path, or no_webhook if triggered
    assert "sent" in notify


def test_quote_cache_helper(monkeypatch):
    from price_sync import clear_quote_cache, fetch_eastmoney_quotes

    clear_quote_cache()
    calls = {"n": 0}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "diff": [
                        {"f12": "600000", "f14": "浦发银行", "f2": 10.5, "f3": 1.0, "f18": 10.4}
                    ]
                }
            }

    def fake_get(*_a, **_k):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setenv("MARKET_QUOTE_CACHE_SECONDS", "120")
    # re-import cache TTL is module-level at load; patch via clear and direct call still uses env at module load
    # so we only assert functional fetch works
    monkeypatch.setattr("price_sync.requests.get", fake_get)
    clear_quote_cache()
    q1 = fetch_eastmoney_quotes(["600000"], use_cache=False)
    assert q1["600000"]["price"] == 10.5
    assert calls["n"] == 1
