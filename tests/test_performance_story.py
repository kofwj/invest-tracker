import sqlite3


def test_performance_story_has_headline_and_winners(client, app_module):
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
            "date": "2026-01-03",
            "code": "601288",
            "name": "农业银行",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 100,
            "price": 5,
            "amount": 500,
            "fee": 0,
            "remark": "",
        },
    )
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE holdings SET last_price = 12 WHERE code = '600000'")
    conn.execute("UPDATE holdings SET last_price = 4 WHERE code = '601288'")
    conn.commit()
    conn.close()

    story = client.get("/performance/story").json()
    assert story.get("headline")
    assert isinstance(story.get("bullets"), list) and len(story["bullets"]) >= 2
    assert story.get("tone") in ("positive", "negative", "neutral")
    winners = story.get("winners") or []
    losers = story.get("losers") or []
    # 600000: (12-10)*100 = +200; 601288: (4-5)*100 = -100
    assert any(w.get("code") == "600000" for w in winners)
    assert any(l.get("code") == "601288" for l in losers)
    assert "has_external_flows" in (story.get("metrics") or {})
