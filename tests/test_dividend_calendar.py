from datetime import date, timedelta
from unittest.mock import patch

from dividend_calendar import (
    _bucket_for,
    check_dividend_upcoming,
    cleanup_dividend_events,
    notify_dividend_upcoming,
    refresh_dividend_events,
)


TODAY = date(2026, 9, 26)


def _local_today():
    from database import local_today_iso

    return date.fromisoformat(local_today_iso())


def _seed_holding(conn, code="601288", name="农业银行", category="A股权益"):
    conn.execute(
        "INSERT OR REPLACE INTO holdings (code, name, category, quantity, avg_cost, last_price) "
        "VALUES (?, ?, ?, 100, 4, 5)",
        (code, name, category),
    )
    conn.commit()


def _market_row(ex_date, *, record=None, plan="10派1.30元", pretax=1.30, progress="实施分配"):
    return {
        "EX_DIVIDEND_DATE": ex_date,
        "EQUITY_RECORD_DATE": record or ex_date,
        "IMPL_PLAN_PROFILE": plan,
        "PRETAX_BONUS_RMB": pretax,
        "ASSIGN_PROGRESS": progress,
        "_source": "eastmoney",
    }


def _insert_event(conn, code, name, ex_date, plan="10派1元"):
    conn.execute(
        "INSERT INTO dividend_events (code, name, ex_date, record_date, per_share, plan_text, source, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'eastmoney', '2026-09-01 10:00:00')",
        (code, name, ex_date, ex_date, 0.1, plan),
    )
    conn.commit()


def test_schema_v20_creates_table_idempotent(app_module):
    from schema import SCHEMA_VERSION, migrate_to_v20_dividend_events

    assert SCHEMA_VERSION == 20
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        migrate_to_v20_dividend_events(conn)
        migrate_to_v20_dividend_events(conn)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(dividend_events)").fetchall()]
    assert "ex_date" in cols
    assert "code" in cols


def test_partial_fetch_failure_keeps_other_codes(app_module):
    today = _local_today()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn, "601288", "农业银行")
        _seed_holding(conn, "600028", "中国石化")

        def fetch(code, kind):
            if code == "600028":
                raise RuntimeError("akshare down")
            return [_market_row((today + timedelta(days=5)).isoformat())]

        result = refresh_dividend_events(conn, fetch_fn=fetch)
        rows = conn.execute("SELECT code FROM dividend_events ORDER BY code").fetchall()
    assert result["ok"] is True
    assert result["source_status"] == "partial"
    assert "600028" in result["failed_codes"]
    assert [r[0] for r in rows] == ["601288"]


def test_all_fetch_fail_keeps_old_and_marks_stale(app_module):
    today = _local_today()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn)
        _insert_event(conn, "601288", "农业银行", (today + timedelta(days=2)).isoformat())
        before = conn.execute("SELECT COUNT(*) FROM dividend_events").fetchone()[0]

        def boom(code, kind):
            raise RuntimeError("network")

        result = refresh_dividend_events(conn, fetch_fn=boom)
        after = conn.execute("SELECT COUNT(*) FROM dividend_events").fetchone()[0]
        info = check_dividend_upcoming(conn, today=today, source_status=result["source_status"])
    assert result["ok"] is False
    assert result["source_status"] == "stale"
    assert before == after == 1
    assert info["has_actionable"] is True
    assert info["source_status"] == "stale"


def test_all_fetch_fail_without_local_events_empty_reminder(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn)

        def boom(code, kind):
            raise RuntimeError("network")

        result = refresh_dividend_events(conn, fetch_fn=boom)
        info = check_dividend_upcoming(conn, today=TODAY, source_status=result["source_status"])
        n = conn.execute("SELECT COUNT(*) FROM dividend_events").fetchone()[0]
    assert n == 0
    assert result["source_status"] == "unavailable"
    assert info["has_actionable"] is False
    assert "无除权除息" in info["text"]


def test_empty_table_does_not_remind(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        info = check_dividend_upcoming(conn, today=TODAY)
    assert info["count"] == 0
    assert info["has_actionable"] is False


def test_window_boundaries(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _insert_event(conn, "000001", "过期", (TODAY - timedelta(days=1)).isoformat())
        _insert_event(conn, "000002", "今天", TODAY.isoformat())
        _insert_event(conn, "000003", "三天", (TODAY + timedelta(days=3)).isoformat())
        _insert_event(conn, "000004", "七天", (TODAY + timedelta(days=7)).isoformat())
        _insert_event(conn, "000005", "八天", (TODAY + timedelta(days=8)).isoformat())
        _insert_event(conn, "000006", "八天前", (TODAY - timedelta(days=8)).isoformat())
        _insert_event(conn, "000007", "很久以前", (TODAY - timedelta(days=400)).isoformat())
        info = check_dividend_upcoming(conn, today=TODAY)
    codes = lambda key: [x["code"] for x in info["buckets"][key]]
    assert codes("overdue") == ["000001"]
    assert codes("d0") == ["000002"]
    assert codes("d3") == ["000003"]
    assert codes("d7") == ["000004"]
    listed = sum((codes(k) for k in ("overdue", "d0", "d3", "d7")), [])
    assert "000005" not in listed
    assert "000006" not in listed
    assert "000007" not in listed



def test_refresh_then_same_round_can_remind(app_module):
    today = _local_today()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn)
        ex = (today + timedelta(days=1)).isoformat()

        def fetch(code, kind):
            return [_market_row(ex)]

        refresh = refresh_dividend_events(conn, fetch_fn=fetch)
        info = check_dividend_upcoming(conn, today=today, source_status=refresh["source_status"])
    assert refresh["inserted"] == 1
    assert info["has_actionable"] is True
    assert info["buckets"]["d3"][0]["code"] == "601288"


def test_duplicate_refresh_does_not_duplicate_rows(app_module):
    today = _local_today()
    ex = (today + timedelta(days=5)).isoformat()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn)

        def fetch(code, kind):
            return [_market_row(ex, plan="10派1.30元")]

        refresh_dividend_events(conn, fetch_fn=fetch)
        refresh_dividend_events(conn, fetch_fn=lambda code, kind: [_market_row(ex, plan="", pretax=None)])
        rows = conn.execute("SELECT code, ex_date, plan_text, per_share FROM dividend_events").fetchall()
    assert len(rows) == 1
    assert rows[0][2]  # plan_text kept
    assert rows[0][3]  # per_share kept, not overwritten by empty



def test_calendar_get_does_not_fetch(client, app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _insert_event(conn, "601288", "农业银行", (date.fromisoformat(__import__("database").local_today_iso()) + timedelta(days=2)).isoformat())
        conn.commit()
    with patch("dividend_sync.fetch_market_dividend_rows") as fetch:
        res = client.get("/dividends/calendar?days=30")
    assert res.status_code == 200
    assert fetch.call_count == 0
    body = res.json()
    assert any(item["code"] == "601288" for item in body["items"])
    assert "failed_codes" in body


def test_notify_same_stamp_not_repeated(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _insert_event(conn, "601288", "农业银行", (TODAY + timedelta(days=1)).isoformat())
        with patch("notify.dispatch", return_value={"sent": True, "results": []}) as send:
            with patch("dividend_calendar.local_today_iso", return_value=TODAY.isoformat()):
                first = notify_dividend_upcoming(conn, source_status="ok")
                second = notify_dividend_upcoming(conn, source_status="ok")
    assert first["sent"] is True
    assert second["sent"] is False
    assert second["reason"] == "already_notified"
    assert send.call_count == 1


def test_no_call_ai_on_module():
    import inspect
    import dividend_calendar as mod

    src = inspect.getsource(mod)
    assert "call_ai" not in src


def test_unusable_rows_not_written(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn)

        def fetch(code, kind):
            return [
                {
                    "EX_DIVIDEND_DATE": "",
                    "EQUITY_RECORD_DATE": "",
                    "IMPL_PLAN_PROFILE": "10派1元",
                    "ASSIGN_PROGRESS": "预案",
                }
            ]

        result = refresh_dividend_events(conn, fetch_fn=fetch)
        n = conn.execute("SELECT COUNT(*) FROM dividend_events").fetchone()[0]
    assert n == 0
    assert result["inserted"] == 0
    assert result["ok"] is True


def test_fetch_fail_unexpired_outside_window_stale_no_remind(app_module):
    today = _local_today()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn)
        _insert_event(conn, "601288", "农业银行", (today + timedelta(days=20)).isoformat())

        def boom(code, kind):
            raise RuntimeError("network")

        result = refresh_dividend_events(conn, fetch_fn=boom)
        info = check_dividend_upcoming(conn, today=today, source_status=result["source_status"])
        n = conn.execute("SELECT COUNT(*) FROM dividend_events").fetchone()[0]
    assert n == 1
    assert result["source_status"] == "stale"
    assert info["has_actionable"] is False


def test_run_scheduled_events_fetches_then_notifies(app_module):
    from notify import run_scheduled_events

    order = []

    def fake_refresh(conn, **kwargs):
        order.append("refresh")
        return {"source_status": "stale", "ok": False}

    def fake_notify(conn, **kwargs):
        order.append("notify")
        assert kwargs.get("source_status") == "stale"
        return {"sent": False, "reason": "nothing_due", "results": []}

    with patch("dividend_calendar.refresh_dividend_events", fake_refresh), patch(
        "dividend_calendar.notify_dividend_upcoming", fake_notify
    ):
        with app_module.get_db_connection(app_module.DB_PATH) as conn:
            out = run_scheduled_events(conn, deposit=False, discipline=False, dividend=True)
    assert order == ["refresh", "notify"]
    assert out["dividend_refresh"]["source_status"] == "stale"


def test_notify_run_does_not_fetch_by_default(client, app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn)
        conn.commit()
    with patch("dividend_calendar.refresh_dividend_events") as refresh:
        res = client.post("/notify/run", json={"deposit": False, "discipline": False})
    assert res.status_code == 200
    assert refresh.call_count == 0


def test_refresh_skips_history_older_than_lookback(app_module):
    today = _local_today()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn)

        def fetch(code, kind):
            return [
                _market_row((today - timedelta(days=400)).isoformat()),
                _market_row((today - timedelta(days=20)).isoformat()),
                _market_row((today + timedelta(days=5)).isoformat()),
            ]

        result = refresh_dividend_events(conn, fetch_fn=fetch)
        rows = conn.execute("SELECT ex_date FROM dividend_events ORDER BY ex_date").fetchall()
    assert result["inserted"] == 1
    assert [r[0] for r in rows] == [(today + timedelta(days=5)).isoformat()]


def test_overdue_bucket_newest_first(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _insert_event(conn, "000010", "较旧", (TODAY - timedelta(days=6)).isoformat())
        _insert_event(conn, "000011", "较新", (TODAY - timedelta(days=1)).isoformat())
        _insert_event(conn, "000012", "中间", (TODAY - timedelta(days=3)).isoformat())
        info = check_dividend_upcoming(conn, today=TODAY)
    assert [x["code"] for x in info["buckets"]["overdue"]] == ["000011", "000012", "000010"]


def test_cleanup_drops_sold_and_old_rows(app_module):
    today = _local_today()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn, "601288", "农业银行")
        _insert_event(conn, "601288", "农业银行", (today + timedelta(days=4)).isoformat())
        _insert_event(conn, "601288", "农业银行旧", (today - timedelta(days=40)).isoformat())
        _insert_event(conn, "999999", "已卖出", (today + timedelta(days=3)).isoformat())

        def fetch(code, kind):
            return []

        refresh_dividend_events(conn, fetch_fn=fetch)
        rows = conn.execute("SELECT code, ex_date FROM dividend_events").fetchall()
    assert [(r[0], r[1]) for r in rows] == [("601288", (today + timedelta(days=4)).isoformat())]


def test_overdue_excludes_eighth_day(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _insert_event(conn, "000008", "八天前", (TODAY - timedelta(days=8)).isoformat())
        info = check_dividend_upcoming(conn, today=TODAY)
    assert info["buckets"]["overdue"] == []
    assert info["has_actionable"] is False
    assert info["count"] == 0


def test_cleanup_skips_code_prune_when_targets_unreadable(app_module):
    today = _local_today()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _insert_event(conn, "999999", "自选", (today + timedelta(days=3)).isoformat())
        cleanup_dividend_events(conn, today=today, keep_codes=[], targets_ok=False)
        n = conn.execute("SELECT COUNT(*) FROM dividend_events").fetchone()[0]
    assert n == 1


def test_cleanup_wipes_when_portfolio_empty(app_module):
    today = _local_today()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _insert_event(conn, "999999", "已清仓", (today + timedelta(days=3)).isoformat())
        cleanup_dividend_events(conn, today=today, keep_codes=[], targets_ok=True)
        n = conn.execute("SELECT COUNT(*) FROM dividend_events").fetchone()[0]
    assert n == 0


def test_bucket_for_two_windows_keeps_d7():
    assert _bucket_for(0, (0, 3)) == "d0"
    assert _bucket_for(3, (0, 3)) == "d3"
    assert _bucket_for(7, (0, 3)) == "d7"


def test_calendar_exposes_partial_failed_codes(app_module):
    from dividend_calendar import list_dividend_calendar

    today = _local_today()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn, "601288", "农业银行")
        _seed_holding(conn, "600028", "中国石化")

        def fetch(code, kind):
            if code == "600028":
                raise RuntimeError("akshare down")
            return [_market_row((today + timedelta(days=5)).isoformat())]

        refresh_dividend_events(conn, fetch_fn=fetch)
        cal = list_dividend_calendar(conn)
    assert cal["source_status"] == "partial"
    assert "600028" in cal["failed_codes"]
