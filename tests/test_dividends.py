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


def _fund_market_rows(code="513530", per_share=0.01):
    today = date.today()
    # Sina-normalized shape used by fetch_sina_fund_dividends
    return [
        {
            "SECURITY_CODE": code,
            "SECURITY_NAME_ABBR": "",
            "IMPL_PLAN_PROFILE": f"每份派{per_share:g}元",
            "PRETAX_BONUS_RMB": per_share * 10,
            "EQUITY_RECORD_DATE": (today - timedelta(days=12)).isoformat(),
            "EX_DIVIDEND_DATE": (today - timedelta(days=5)).isoformat(),
            "ASSIGN_PROGRESS": "实施分配",
            "NOTICE_DATE": (today - timedelta(days=12)).isoformat(),
            "_source": "sina_fund_fh",
            "_cash_per_share": per_share,
        },
        {
            "SECURITY_CODE": code,
            "SECURITY_NAME_ABBR": "",
            "IMPL_PLAN_PROFILE": f"每份派{per_share:g}元",
            "PRETAX_BONUS_RMB": per_share * 10,
            "EQUITY_RECORD_DATE": (today - timedelta(days=40)).isoformat(),
            "EX_DIVIDEND_DATE": (today - timedelta(days=35)).isoformat(),
            "ASSIGN_PROGRESS": "实施分配",
            "NOTICE_DATE": (today - timedelta(days=40)).isoformat(),
            "_source": "sina_fund_fh",
            "_cash_per_share": per_share,
        },
    ]


def test_dividend_scan_listed_fund_uses_sina_source(client, app_module, monkeypatch):
    import dividend_sync

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        _seed_holding(conn, code="513530", name="港股通红利ETF", qty=10000, category="港股ETF")
        _seed_holding(conn, code="508056", name="中金普洛斯REIT", qty=2000, category="REITs")
        # open-end short bond should remain unsupported
        _seed_holding(conn, code="002864", name="某短债", qty=1000, category="债基")
        conn.commit()

    equity_called = {"n": 0}
    fund_called = {"codes": []}

    def fake_equity(code, page_size=30):
        equity_called["n"] += 1
        return _market_rows()

    def fake_fund(code, page_size=40):
        fund_called["codes"].append(code)
        if code == "513530":
            return _fund_market_rows("513530", 0.01)
        if code == "508056":
            return _fund_market_rows("508056", 0.04)
        return []

    monkeypatch.setattr(dividend_sync, "fetch_eastmoney_share_bonus", fake_equity)
    monkeypatch.setattr(dividend_sync, "fetch_sina_fund_dividends", fake_fund)

    res = client.post("/dividends/scan", json={"lookback_days": 120})
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["scanned_fund_holdings"] == 2
    assert data["summary"]["unsupported_holdings"] == 1
    assert equity_called["n"] == 0
    assert set(fund_called["codes"]) == {"513530", "508056"}

    drafts = data["drafts"]
    assert len(drafts) == 4  # 2 codes * 2 events
    by_code = {}
    for d in drafts:
        by_code.setdefault(d["code"], []).append(d)
    # 10000 * 0.01 = 100
    hk = [d for d in by_code["513530"] if d["status"] == "new"]
    assert hk
    assert abs(hk[0]["amount"] - 100) < 0.01
    assert hk[0]["source"] == "sina_fund_fh"
    # 2000 * 0.04 = 80
    reit = [d for d in by_code["508056"] if d["status"] == "new"]
    assert reit
    assert abs(reit[0]["amount"] - 80) < 0.01


def test_dividend_scan_skips_open_end_bond(client, app_module, monkeypatch):
    import dividend_sync

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        _seed_holding(conn, code="002864", name="某短债", qty=1000, category="债基")
        conn.commit()

    monkeypatch.setattr(dividend_sync, "fetch_sina_fund_dividends", lambda code, page_size=40: (_ for _ in ()).throw(AssertionError("should not fetch")))
    res = client.post("/dividends/scan", json={"lookback_days": 120})
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["scanned_holdings"] == 0
    assert data["summary"]["unsupported_holdings"] == 1
