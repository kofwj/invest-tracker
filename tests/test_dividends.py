from datetime import date, timedelta

import sqlite3


def _seed_holding(conn, code="000651", name="格力电器", qty=1000, category="A股权益"):
    conn.execute(
        """
        INSERT INTO holdings (code, name, category, quantity, avg_cost, diluted_cost, total_dividend, last_price)
        VALUES (?, ?, ?, ?, 30, 30, 0, 40)
        """,
        (code, name, category, qty),
    )
    conn.execute(
        """
        INSERT INTO transactions (date, code, name, category, account, direction, quantity, price, amount, fee, remark)
        VALUES (?, ?, ?, ?, '华泰证券', '买入', ?, 30, ?, 0, 'seed buy')
        """,
        ((date.today() - timedelta(days=400)).isoformat(), code, name, category, qty, qty * 30),
    )
    conn.commit()


def _market_rows():
    # one already-recorded-ish event and one new event
    today = date.today()
    return [
        {
            "SECURITY_CODE": "000651",
            "SECURITY_NAME_ABBR": "格力电器",
            "IMPL_PLAN_PROFILE": "10派10.00元(含税)",
            "PRETAX_BONUS_RMB": 10,
            "EQUITY_RECORD_DATE": (today - timedelta(days=40)).strftime("%Y-%m-%d 00:00:00"),
            "EX_DIVIDEND_DATE": (today - timedelta(days=39)).strftime("%Y-%m-%d 00:00:00"),
            "ASSIGN_PROGRESS": "实施分配",
            "NOTICE_DATE": (today - timedelta(days=45)).strftime("%Y-%m-%d 00:00:00"),
        },
        {
            "SECURITY_CODE": "000651",
            "SECURITY_NAME_ABBR": "格力电器",
            "IMPL_PLAN_PROFILE": "10派20.00元(含税)",
            "PRETAX_BONUS_RMB": 20,
            "EQUITY_RECORD_DATE": (today - timedelta(days=10)).strftime("%Y-%m-%d 00:00:00"),
            "EX_DIVIDEND_DATE": (today - timedelta(days=9)).strftime("%Y-%m-%d 00:00:00"),
            "ASSIGN_PROGRESS": "实施分配",
            "NOTICE_DATE": (today - timedelta(days=12)).strftime("%Y-%m-%d 00:00:00"),
        },
    ]


def test_dividend_scan_marks_existing_and_new(client, app_module, monkeypatch):
    import dividend_sync

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        _seed_holding(conn)
        # existing dividend near first event
        first_ex = date.today() - timedelta(days=39)
        conn.execute(
            """
            INSERT INTO transactions (date, code, name, category, account, direction, quantity, price, amount, fee, remark)
            VALUES (?, '000651', '格力电器', 'A股权益', '华泰证券', '分红', 0, 0, 1000, 0, 'manual dividend')
            """,
            (first_ex.isoformat(),),
        )
        conn.commit()

    monkeypatch.setattr(dividend_sync, "fetch_eastmoney_share_bonus", lambda code, page_size=30: _market_rows())

    res = client.post("/dividends/scan", json={"lookback_days": 120})
    assert res.status_code == 200
    data = res.json()
    drafts = data["drafts"]
    assert len(drafts) == 2
    by_status = {d["status"]: d for d in drafts}
    assert "already_recorded" in by_status
    assert "new" in by_status
    new_draft = by_status["new"]
    # 1000 shares * 2.0 per share = 2000
    assert abs(new_draft["amount"] - 2000) < 0.01
    assert new_draft["selectable"] is True
    assert data["summary"]["already_recorded_count"] == 1
    assert data["summary"]["new_count"] == 1


def test_dividend_confirm_writes_transaction_and_dedupes(client, app_module, monkeypatch):
    import dividend_sync

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        _seed_holding(conn)
        conn.commit()

    monkeypatch.setattr(dividend_sync, "fetch_eastmoney_share_bonus", lambda code, page_size=30: _market_rows())
    scan = client.post("/dividends/scan", json={"lookback_days": 120}).json()
    new_items = [d for d in scan["drafts"] if d["status"] == "new"]
    assert new_items

    payload = {
        "backup": False,
        "drafts": [
            {
                "code": d["code"],
                "name": d["name"],
                "category": d["category"],
                "account": d["account"],
                "event_date": d["event_date"],
                "amount": d["amount"],
                "fee": 0,
                "remark": d["remark"],
                "plan_profile": d.get("plan_profile"),
            }
            for d in new_items
        ],
    }
    conf = client.post("/dividends/confirm", json=payload)
    assert conf.status_code == 200
    body = conf.json()
    assert body["created_count"] == len(new_items)

    # holdings total_dividend should increase
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT total_dividend FROM holdings WHERE code='000651'").fetchone()
        assert float(row["total_dividend"]) >= new_items[0]["amount"] - 0.01
        cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM transactions WHERE code='000651' AND direction='分红'"
        ).fetchone()["c"]
        assert cnt == len(new_items)

    # second confirm should skip as already recorded
    conf2 = client.post("/dividends/confirm", json=payload)
    assert conf2.status_code == 200
    assert conf2.json()["created_count"] == 0
    assert conf2.json()["skipped_count"] == len(new_items)


def test_dividend_scan_skips_etf(client, app_module, monkeypatch):
    import dividend_sync

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        _seed_holding(conn, code="159352", name="A500ETF", qty=10000, category="A股ETF")
        conn.commit()

    called = {"n": 0}

    def fake_fetch(code, page_size=30):
        called["n"] += 1
        return _market_rows()

    monkeypatch.setattr(dividend_sync, "fetch_eastmoney_share_bonus", fake_fetch)
    res = client.post("/dividends/scan", json={"lookback_days": 120})
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["scanned_holdings"] == 0
    assert data["summary"]["unsupported_holdings"] == 1
    assert called["n"] == 0
