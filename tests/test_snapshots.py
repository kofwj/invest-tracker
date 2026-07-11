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
