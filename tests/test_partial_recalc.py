import sqlite3


def test_partial_recalc_only_touches_target_code(client, app_module):
    # Seed two holdings via buys
    for code, name, price in (
        ("600000", "浦发银行", 10),
        ("601288", "农业银行", 5),
    ):
        resp = client.post(
            "/transactions",
            json={
                "date": "2026-01-02",
                "code": code,
                "name": name,
                "category": "A股权益",
                "account": "华泰证券",
                "direction": "买入",
                "quantity": 100,
                "price": price,
                "amount": 100 * price,
                "fee": 0,
                "remark": "",
            },
        )
        assert resp.status_code == 200

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    # Mark last_price distinctly so we can detect accidental full rebuild side-effects
    conn.execute("UPDATE holdings SET last_price = 11, expected_return = 7.7 WHERE code = '600000'")
    conn.execute("UPDATE holdings SET last_price = 6.6, expected_return = 3.3 WHERE code = '601288'")
    conn.commit()

    # Another buy on only 601288 — partial recalc
    resp = client.post(
        "/transactions",
        json={
            "date": "2026-02-01",
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
    assert resp.status_code == 200

    h600 = dict(conn.execute("SELECT * FROM holdings WHERE code='600000'").fetchone())
    h288 = dict(conn.execute("SELECT * FROM holdings WHERE code='601288'").fetchone())
    conn.close()

    # Unrelated code keeps price/return metadata
    assert abs(h600["last_price"] - 11) < 1e-9
    assert abs(h600["expected_return"] - 7.7) < 1e-9
    assert abs(h600["quantity"] - 100) < 1e-9

    # Target code quantity updated; last_price preserved from old row when present
    assert abs(h288["quantity"] - 200) < 1e-9
    assert abs(h288["last_price"] - 6.6) < 1e-9
    assert abs(h288["expected_return"] - 3.3) < 1e-9
