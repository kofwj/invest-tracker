import sqlite3


def test_performance_story_splits_bond_reit_equity(client, app_module):
    """大类贡献必须拆开：债基 / REITs / 权益，不再合成「固收相关」。"""
    samples = [
        ("f004388", "鹏华丰享", "债基", 1000, 1.0, 1.1),  # +100
        ("508056", "中金普洛斯REIT", "REITs", 1000, 3.0, 2.5),  # -500
        ("601288", "农业银行", "A股权益", 100, 5.0, 6.0),  # +100
        ("518880", "黄金ETF", "黄金", 100, 10.0, 9.0),  # -100 → 权益
    ]
    for code, name, category, qty, cost, last in samples:
        client.post(
            "/transactions",
            json={
                "date": "2026-01-02",
                "code": code,
                "name": name,
                "category": category,
                "account": "华泰证券",
                "direction": "买入",
                "quantity": qty,
                "price": cost,
                "amount": round(qty * cost, 2),
                "fee": 0,
                "remark": "",
            },
        )
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.execute(
            "UPDATE holdings SET last_price = ?, category = ? WHERE code = ?",
            (last, category, code),
        )
        conn.commit()
        conn.close()

    story = client.get("/performance/story").json()
    cats = {c["name"]: round(float(c["amount"]), 2) for c in (story.get("category_contrib") or [])}
    assert list(cats.keys()) == ["债基", "REITs", "权益"]
    assert "固收相关" not in cats
    assert "权益相关" not in cats
    assert cats["债基"] == 100.0
    assert cats["REITs"] == -500.0
    assert cats["权益"] == 0.0  # +100 农行 + (-100) 黄金
