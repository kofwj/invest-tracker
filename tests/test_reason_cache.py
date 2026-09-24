from datetime import datetime
from unittest.mock import patch


def _holding(conn, code="000651"):
    conn.execute(
        "INSERT OR REPLACE INTO holdings (code, name, category, quantity, avg_cost, last_price) "
        "VALUES (?, '格力', 'A股权益', 100, 10, 12)",
        (code,),
    )


def test_move_dedupe(app_module):
    from reason_cache import refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _holding(conn)
        event = {
            "code": "000651",
            "name": "格力",
            "kind": "move",
            "board": "大笔卖出",
            "event_time": "10:01:00",
            "date": "2026-09-24",
        }
        with patch("reason_cache.fetch_intraday_moves", return_value=[event, event]), \
             patch("reason_cache.fetch_stock_news", return_value=[]), \
             patch("reason_cache.fetch_notices", return_value=[]), \
             patch("reason_cache.fetch_global_news", return_value=[]):
            refresh_reasons(conn, now=datetime(2026, 9, 24, 15, 30), force=True)
        n = conn.execute("SELECT COUNT(*) FROM intraday_move_cache").fetchone()[0]
        assert n == 1


def test_notice_outside_window_excluded(app_module):
    from reason_cache import reasons_for_holdings

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO notice_cache (code, date, title) VALUES ('000651', '2026-08-01', '旧公告')"
        )
        conn.commit()
        data = reasons_for_holdings(conn, ["000651"], as_of="2026-09-24")
        assert data["reasons"] == []


def test_non_holding_notice_not_stored(app_module):
    from reason_cache import refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _holding(conn, "000651")
        notices = [
            {"code": "600000", "date": "2026-09-24", "title": "别人的公告", "name": "浦发", "notice_type": "其他", "url": ""},
            {"code": "000651", "date": "2026-09-24", "title": "格力公告", "name": "格力", "notice_type": "其他", "url": ""},
        ]
        with patch("reason_cache.fetch_intraday_moves", return_value=[]), \
             patch("reason_cache.fetch_stock_news", return_value=[]), \
             patch("reason_cache.fetch_notices", return_value=notices), \
             patch("reason_cache.fetch_global_news", return_value=[]):
            refresh_reasons(conn, now=datetime(2026, 9, 24, 16, 0), force=True)
        codes = [r[0] for r in conn.execute("SELECT code FROM notice_cache").fetchall()]
        assert codes == ["000651"]


def test_moves_throttle(app_module):
    from cash import set_setting
    from reason_cache import SETTING_MOVES_POLLED_AT, refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _holding(conn)
        set_setting(conn, SETTING_MOVES_POLLED_AT, "2026-09-24 10:10:00")
        conn.commit()
        with patch("reason_cache.fetch_intraday_moves") as mock_moves, \
             patch("reason_cache.fetch_stock_news", return_value=[]), \
             patch("reason_cache.fetch_notices", return_value=[]), \
             patch("reason_cache.fetch_global_news", return_value=[]):
            mock_moves.return_value = []
            r = refresh_reasons(conn, now=datetime(2026, 9, 24, 10, 15, 0), force=False)
            assert "moves" in r["skipped"]
            assert mock_moves.call_count == 0
            r2 = refresh_reasons(conn, now=datetime(2026, 9, 24, 10, 26, 0), force=False)
            assert mock_moves.call_count == 1
            assert "moves" not in r2["skipped"]


def test_notices_once_per_day(app_module):
    from cash import set_setting
    from reason_cache import SETTING_NOTICES_FETCHED_DATE, refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        set_setting(conn, SETTING_NOTICES_FETCHED_DATE, "2026-09-24 16:40:00")
        conn.commit()
        with patch("reason_cache.fetch_notices") as mock_n:
            mock_n.return_value = []
            with patch("reason_cache.fetch_intraday_moves", return_value=[]), \
                 patch("reason_cache.fetch_stock_news", return_value=[]), \
                 patch("reason_cache.fetch_global_news", return_value=[]):
                r = refresh_reasons(conn, now=datetime(2026, 9, 24, 17, 10), force=False)
            assert "notices" in r["skipped"]
            assert mock_n.call_count == 0

def test_empty_window_is_normal(app_module):
    from reason_cache import reasons_for_holdings

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        data = reasons_for_holdings(conn, ["000651", "601288"], as_of="2026-09-24")
        assert data["reasons"] == []
        assert data["moves"] == []
        assert data["reason_coverage"]["note"]


def test_akshare_all_fail_no_dirty_rows(app_module):
    from reason_cache import refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _holding(conn)
        with patch("reason_cache.fetch_intraday_moves", side_effect=RuntimeError("x")), \
             patch("reason_cache.fetch_notices", side_effect=RuntimeError("x")), \
             patch("reason_cache.fetch_global_news", side_effect=RuntimeError("x")), \
             patch("reason_cache.fetch_stock_news", side_effect=RuntimeError("x")):
            r = refresh_reasons(conn, now=datetime(2026, 9, 24, 16, 0), force=True)
        assert r["skipped"]
        assert conn.execute("SELECT COUNT(*) FROM notice_cache").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM intraday_move_cache").fetchone()[0] == 0


def test_notice_timeout_does_not_block(app_module):
    from reason_cache import refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _holding(conn)
        with patch("reason_cache.fetch_notices", return_value=[]), \
             patch("reason_cache.fetch_intraday_moves", return_value=[]), \
             patch("reason_cache.fetch_stock_news", return_value=[]), \
             patch("reason_cache.fetch_global_news", return_value=[]):
            r = refresh_reasons(conn, now=datetime(2026, 9, 24, 16, 0), force=True)
        assert r["notices"] == 0
        assert isinstance(r["skipped"], list)


def test_notices_refill_after_16(app_module):
    from cash import set_setting
    from reason_cache import SETTING_NOTICES_FETCHED_DATE, refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        set_setting(conn, SETTING_NOTICES_FETCHED_DATE, "2026-09-24 15:20:00")
        conn.commit()
        with patch("reason_cache.fetch_notices") as mock_n, \
             patch("reason_cache.fetch_intraday_moves", return_value=[]), \
             patch("reason_cache.fetch_stock_news", return_value=[]), \
             patch("reason_cache.fetch_global_news", return_value=[]):
            mock_n.return_value = []
            r = refresh_reasons(conn, now=datetime(2026, 9, 24, 16, 40), force=False)
        assert "notices" not in r["skipped"]
        assert mock_n.call_count == 1


def test_notice_failure_does_not_stamp(app_module):
    from reason_cache import SETTING_NOTICES_FETCHED_DATE, refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("reason_cache.fetch_notices", return_value=None), \
             patch("reason_cache.fetch_intraday_moves", return_value=[]), \
             patch("reason_cache.fetch_stock_news", return_value=[]), \
             patch("reason_cache.fetch_global_news", return_value=[]):
            refresh_reasons(conn, now=datetime(2026, 9, 24, 15, 30), force=True)
        stamp = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (SETTING_NOTICES_FETCHED_DATE,),
        ).fetchone()
        assert stamp is None or stamp[0] in (None, "")
        with patch("reason_cache.fetch_notices") as mock_n, \
             patch("reason_cache.fetch_intraday_moves", return_value=[]), \
             patch("reason_cache.fetch_stock_news", return_value=[]), \
             patch("reason_cache.fetch_global_news", return_value=[]):
            mock_n.return_value = []
            r = refresh_reasons(conn, now=datetime(2026, 9, 24, 16, 40), force=False)
        assert mock_n.call_count == 1
        assert "notices" not in r["skipped"]


def test_refresh_fetches_before_writes(app_module):
    from reason_cache import refresh_reasons

    events = []

    def fetch(*_a, **_k):
        events.append("fetch")
        return []

    def write(*_a, **_k):
        events.append("write")
        return 0

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _holding(conn)
        with patch("reason_cache.fetch_intraday_moves", side_effect=fetch), \
             patch("reason_cache.fetch_stock_news", side_effect=fetch), \
             patch("reason_cache.fetch_notices", side_effect=fetch), \
             patch("reason_cache.fetch_global_news", side_effect=fetch), \
             patch("reason_cache._insert_moves", side_effect=write), \
             patch("reason_cache._insert_news", side_effect=write), \
             patch("reason_cache._insert_notices", side_effect=write), \
             patch("reason_cache._insert_market_news", side_effect=write):
            refresh_reasons(conn, now=datetime(2026, 9, 24, 16, 0), force=True)
    assert "fetch" in events and "write" in events
    last_fetch = max(i for i, e in enumerate(events) if e == "fetch")
    first_write = min(i for i, e in enumerate(events) if e == "write")
    assert last_fetch < first_write


def test_coverage_counts_moves(app_module):
    from reason_cache import reasons_for_holdings

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO intraday_move_cache (date, code, board, event_time, name) "
            "VALUES ('2026-09-24', '000651', '大笔卖出', '10:01:00', '格力')"
        )
        conn.commit()
        data = reasons_for_holdings(conn, ["000651"], as_of="2026-09-24")
        assert data["reasons"] == []
        assert data["moves"]
        assert data["reason_coverage"]["matched"] == 1
        assert "无可对应" not in data["reason_coverage"]["note"]


def test_market_news_combined_datetime_is_readable(app_module):
    from reason_cache import reasons_for_holdings

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO market_news_cache (date, published_at, title, content) "
            "VALUES ('2026-09-24', '2026-09-24 09:30:00', '标题A', '')"
        )
        conn.execute(
            "INSERT INTO market_news_cache (date, published_at, title, content) "
            "VALUES ('2026-09-24', '09:30:00', '标题B', '')"
        )
        conn.commit()
        data = reasons_for_holdings(conn, ["000651"], as_of="2026-09-24")
        titles = {r["title"] for r in data["reasons"] if r.get("kind") == "market_news"}
        assert "标题A" in titles
        assert "标题B" in titles



def test_market_fail_does_not_block_notice_stamp(app_module):
    from reason_cache import SETTING_MARKET_FETCHED_DATE, SETTING_NOTICES_FETCHED_DATE, refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("reason_cache.fetch_notices", return_value=[]), \
             patch("reason_cache.fetch_global_news", return_value=None), \
             patch("reason_cache.fetch_intraday_moves", return_value=[]), \
             patch("reason_cache.fetch_stock_news", return_value=[]):
            refresh_reasons(conn, now=datetime(2026, 9, 24, 16, 0), force=True)
        notices = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (SETTING_NOTICES_FETCHED_DATE,),
        ).fetchone()
        market = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (SETTING_MARKET_FETCHED_DATE,),
        ).fetchone()
        assert notices is not None and notices[0]
        assert market is None or market[0] in (None, "")


def test_moves_all_fail_does_not_stamp(app_module):
    from reason_cache import SETTING_MOVES_POLLED_AT, refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _holding(conn)
        with patch("reason_cache.fetch_intraday_moves", return_value=None), \
             patch("reason_cache.fetch_stock_news", return_value=[]), \
             patch("reason_cache.fetch_notices", return_value=[]), \
             patch("reason_cache.fetch_global_news", return_value=[]):
            r = refresh_reasons(conn, now=datetime(2026, 9, 24, 10, 0), force=True)
        assert "moves" in r["skipped"]
        stamp = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (SETTING_MOVES_POLLED_AT,),
        ).fetchone()
        assert stamp is None or stamp[0] in (None, "")
        with patch("reason_cache.fetch_intraday_moves") as mock_m, \
             patch("reason_cache.fetch_stock_news", return_value=[]), \
             patch("reason_cache.fetch_notices", return_value=[]), \
             patch("reason_cache.fetch_global_news", return_value=[]):
            mock_m.return_value = []
            refresh_reasons(conn, now=datetime(2026, 9, 24, 10, 5), force=False)
        assert mock_m.call_count == 1



def test_refresh_reasons_purges_old_ai_log(app_module):
    from reason_cache import refresh_reasons

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) "
            "VALUES ('2026-01-01 12:00:00', 'brief', 1)"
        )
        conn.commit()
        with patch("reason_cache.fetch_intraday_moves", return_value=[]), \
             patch("reason_cache.fetch_stock_news", return_value=[]), \
             patch("reason_cache.fetch_notices", return_value=[]), \
             patch("reason_cache.fetch_global_news", return_value=[]):
            refresh_reasons(conn, now=datetime(2026, 9, 24, 16, 0), force=True)
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM ai_call_log").fetchone()[0]
        assert n == 0



def test_should_fetch_after_close_uses_refill_minute():
    from reason_cache import _should_fetch_after_close

    last = "2026-09-24 15:20:00"
    assert _should_fetch_after_close(last, datetime(2026, 9, 24, 16, 10), False) is False
    assert _should_fetch_after_close(last, datetime(2026, 9, 24, 16, 40), False) is True
    assert _should_fetch_after_close("2026-09-24 16:45:00", datetime(2026, 9, 24, 17, 10), False) is False
