from datetime import datetime


def test_local_today_iso_respects_app_timezone(app_module, monkeypatch):
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 18, 16, 30, tzinfo=tz)

    import database as db

    monkeypatch.setattr(db, "datetime", FakeDateTime)
    assert app_module.local_today_iso() == "2026-05-18"
    assert db.local_today_iso() == "2026-05-18"


def test_create_snapshot_updates_same_day_record(client, app_module, monkeypatch):
    import database as db

    monkeypatch.setattr(db, "local_today_iso", lambda: "2026-05-19")

    first = client.post("/snapshots")
    assert first.status_code == 200
    assert first.json()["action"] == "created"

    second = client.post("/snapshots")
    assert second.status_code == 200
    data = second.json()
    assert data["action"] == "updated"
    assert data["date"] == "2026-05-19"

    snapshots = client.get("/snapshots")
    assert snapshots.status_code == 200
    rows = snapshots.json()
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-05-19"


def test_snapshot_summary_day_over_day_anomaly(client, app_module):
    import sqlite3

    conn = sqlite3.connect(app_module.DB_PATH)
    # ensure daily_snapshots table exists via app schema
    app_module.initialize_database()
    conn.execute(
        """
        INSERT OR REPLACE INTO daily_snapshots
        (date, total_assets, total_market_value, bank_balance, securities_cash, pending_purchase,
         total_profit, lifetime_profit, holdings_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-05-18", 1000000, 500000, 400000, 100000, 0, 0, 0, 1),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO daily_snapshots
        (date, total_assets, total_market_value, bank_balance, securities_cash, pending_purchase,
         total_profit, lifetime_profit, holdings_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-05-19", 1030000, 530000, 400000, 100000, 0, 0, 0, 1),
    )
    conn.commit()
    conn.close()

    res = client.get("/snapshots/summary")
    assert res.status_code == 200
    data = res.json()
    assert data.get("day_over_day_anomaly")
    assert abs(float(data["day_over_day_anomaly"]["change_pct"])) >= 2.0
