"""Reason cache: news / notices / market news / intraday moves."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

try:
    from .ai_client import purge_ai_call_log
    from .cash import set_setting
    from .database import LOCAL_TZ, local_today_iso
    from .reason_sources import (
        DEFAULT_MOVE_BOARDS,
        fetch_global_news,
        fetch_intraday_moves,
        fetch_notices,
        fetch_stock_news,
    )
except ImportError:
    from ai_client import purge_ai_call_log
    from cash import set_setting
    from database import LOCAL_TZ, local_today_iso
    from reason_sources import (
        DEFAULT_MOVE_BOARDS,
        fetch_global_news,
        fetch_intraday_moves,
        fetch_notices,
        fetch_stock_news,
    )

WINDOW_DAYS = {"news": 3, "notice": 2, "move": 2, "market_news": 1}
MOVES_POLL_MINUTES = 15
NOTICE_REFILL_HOUR = 16
NOTICE_REFILL_MINUTE = 40  # cron 16:40; empty-brief retry uses the same cutoff
CACHE_KEEP_DAYS = 30
SETTING_MOVES_POLLED_AT = "reasons_moves_polled_at"
SETTING_NOTICES_FETCHED_DATE = "reasons_notices_fetched_date"
SETTING_MARKET_FETCHED_DATE = "reasons_market_news_fetched_date"


def ensure_reason_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news_cache (
            code TEXT NOT NULL, published_at TEXT NOT NULL, title TEXT NOT NULL,
            content TEXT, source TEXT, url TEXT,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (code, published_at, title)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notice_cache (
            code TEXT NOT NULL, date TEXT NOT NULL, title TEXT NOT NULL,
            name TEXT, notice_type TEXT, url TEXT,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (code, date, title)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_news_cache (
            date TEXT NOT NULL, published_at TEXT NOT NULL, title TEXT NOT NULL,
            content TEXT, fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, published_at, title)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS intraday_move_cache (
            date TEXT NOT NULL, code TEXT NOT NULL, board TEXT NOT NULL,
            event_time TEXT NOT NULL, name TEXT,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, code, board, event_time)
        )
        """
    )


def _now_local(now=None) -> datetime:
    if now is not None:
        if isinstance(now, datetime):
            return now.replace(tzinfo=None) if now.tzinfo else now
        return datetime.fromisoformat(str(now))
    if LOCAL_TZ is not None:
        return datetime.now(LOCAL_TZ).replace(tzinfo=None)
    return datetime.now()


def _get_setting(conn, key: str) -> Optional[str]:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        value = row["value"] if hasattr(row, "keys") else row[0]
        return None if value is None else str(value)
    except Exception:
        return None


def _norm_code(code: Any) -> str:
    text = str(code or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return text
    return digits.zfill(6) if len(digits) <= 6 else digits


def _holding_codes(conn) -> List[str]:
    try:
        rows = conn.execute("SELECT code FROM holdings WHERE quantity > 0").fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for row in rows:
        code = _norm_code(row["code"] if hasattr(row, "keys") else row[0])
        if code:
            out.append(code)
    return out


def _date_of(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return "%s-%s-%s" % (digits[:4], digits[4:6], digits[6:8])
    return ""


def _parse_stamp(stamp: Optional[str]) -> Optional[datetime]:
    if not stamp:
        return None
    text = str(stamp).strip().replace("Z", "")
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:n], fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _should_fetch_after_close(last_raw: Optional[str], now: datetime, force: bool) -> bool:
    if force:
        return True
    if now.hour < 15:
        return False
    last = _parse_stamp(last_raw)
    if last is None:
        return True
    if last.date() != now.date():
        return True
    cutoff = (NOTICE_REFILL_HOUR, NOTICE_REFILL_MINUTE)
    if (now.hour, now.minute) >= cutoff and (last.hour, last.minute) < cutoff:
        return True
    return False


def _elapsed_minutes(stamp: Optional[str], now: datetime) -> float:
    if not stamp:
        return 10**9
    try:
        then = datetime.fromisoformat(str(stamp).replace("Z", ""))
        return (now - then).total_seconds() / 60.0
    except Exception:
        try:
            then = datetime.strptime(str(stamp)[:19], "%Y-%m-%d %H:%M:%S")
            return (now - then).total_seconds() / 60.0
        except Exception:
            return 10**9


def _insert_news(conn, items: Sequence[Dict[str, Any]]) -> int:
    n = 0
    for item in items:
        code = _norm_code(item.get("code"))
        published = str(item.get("published_at") or "").strip()
        title = str(item.get("title") or "").strip()
        if not code or not published or not title:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO news_cache
                (code, published_at, title, content, source, url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                published,
                title,
                item.get("content") or "",
                item.get("source") or "",
                item.get("url") or "",
            ),
        )
        n += conn.execute("SELECT changes()").fetchone()[0]
    return n


def _insert_notices(conn, items: Sequence[Dict[str, Any]], holding: set) -> int:
    n = 0
    for item in items:
        code = _norm_code(item.get("code"))
        if code not in holding:
            continue
        day = _date_of(item.get("date"))
        title = str(item.get("title") or "").strip()
        if not code or not day or not title:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO notice_cache
                (code, date, title, name, notice_type, url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                day,
                title,
                item.get("name") or "",
                item.get("notice_type") or "",
                item.get("url") or "",
            ),
        )
        n += conn.execute("SELECT changes()").fetchone()[0]
    return n


def _insert_market_news(conn, items: Sequence[Dict[str, Any]], day: str) -> int:
    n = 0
    for item in items:
        title = str(item.get("title") or "").strip()
        published = str(item.get("published_at") or "").strip() or day
        if not title:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO market_news_cache
                (date, published_at, title, content)
            VALUES (?, ?, ?, ?)
            """,
            (day, published, title, item.get("content") or ""),
        )
        n += conn.execute("SELECT changes()").fetchone()[0]
    return n


def _insert_moves(conn, items: Sequence[Dict[str, Any]], holding: set) -> int:
    n = 0
    for item in items:
        code = _norm_code(item.get("code"))
        if code not in holding:
            continue
        day = _date_of(item.get("date"))
        board = str(item.get("board") or "").strip()
        event_time = str(item.get("event_time") or "").strip()
        if not code or not day or not board or not event_time:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO intraday_move_cache
                (date, code, board, event_time, name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (day, code, board, event_time, item.get("name") or ""),
        )
        n += conn.execute("SELECT changes()").fetchone()[0]
    return n


def purge_reason_cache(conn, *, as_of: str) -> None:
    cut = _date_of(as_of)
    try:
        as_of_d = datetime.strptime(cut, "%Y-%m-%d").date()
    except ValueError:
        return
    cut = (as_of_d - timedelta(days=CACHE_KEEP_DAYS)).isoformat()
    for sql, arg in (
        ("DELETE FROM news_cache WHERE substr(published_at,1,10) < ?", cut),
        ("DELETE FROM notice_cache WHERE date < ?", cut),
        ("DELETE FROM market_news_cache WHERE date < ?", cut),
        ("DELETE FROM intraday_move_cache WHERE date < ?", cut),
    ):
        try:
            conn.execute(sql, (arg,))
        except sqlite3.OperationalError:
            pass


def refresh_reasons(conn, *, now=None, force: bool = False) -> Dict[str, Any]:
    """Fetch off the write lock, then insert in a short transaction."""
    now = _now_local(now)
    today = now.date().isoformat()
    skipped: List[str] = []
    result = {"moves": 0, "notices": 0, "market_news": 0, "skipped": skipped}
    codes = _holding_codes(conn)
    holding = set(codes)

    last_moves = _get_setting(conn, SETTING_MOVES_POLLED_AT)
    should_moves = force or _elapsed_minutes(last_moves, now) >= MOVES_POLL_MINUTES
    last_notices = _get_setting(conn, SETTING_NOTICES_FETCHED_DATE)
    should_notices = _should_fetch_after_close(last_notices, now, force)
    last_market = _get_setting(conn, SETTING_MARKET_FETCHED_DATE)
    should_market = _should_fetch_after_close(last_market, now, force)
    # Release any deferred write txn before network I/O.
    try:
        conn.commit()
    except Exception:
        pass
    moves_items = None
    news_items: List[Dict[str, Any]] = []
    notices_items = None
    market_items = None

    if should_moves:
        try:
            moves_items = fetch_intraday_moves(DEFAULT_MOVE_BOARDS, today)
            for code in codes:
                try:
                    news_items.extend(fetch_stock_news(code))
                except Exception:
                    logger.exception("stock news failed for %s", code)
        except Exception:
            logger.exception("refresh moves failed")
            moves_items = None
        if moves_items is None:
            skipped.append("moves")
    else:
        skipped.append("moves")

    if should_notices:
        try:
            notices_items = fetch_notices(today)
        except Exception:
            logger.exception("refresh notices failed")
            notices_items = None
        if notices_items is None:
            skipped.append("notices")
    else:
        skipped.append("notices")

    if should_market:
        try:
            market_items = fetch_global_news(today)
        except Exception:
            logger.exception("refresh market news failed")
            market_items = None
        if market_items is None:
            skipped.append("market_news")
    else:
        skipped.append("market_news")

    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    if news_items:
        _insert_news(conn, news_items)
    if moves_items is not None:
        result["moves"] = _insert_moves(conn, moves_items, holding)
        set_setting(conn, SETTING_MOVES_POLLED_AT, stamp)
    if notices_items is not None:
        result["notices"] = _insert_notices(conn, notices_items, holding)
        set_setting(conn, SETTING_NOTICES_FETCHED_DATE, stamp)
    if market_items is not None:
        result["market_news"] = _insert_market_news(conn, market_items, today)
        set_setting(conn, SETTING_MARKET_FETCHED_DATE, stamp)
    purge_reason_cache(conn, as_of=today)
    purge_ai_call_log(conn, as_of=today)
    return result


def reasons_for_holdings(conn, codes: Sequence[str], *, as_of: str) -> Dict[str, Any]:
    """Return windowed reasons/moves/coverage. Empty lists are normal."""
    as_of_s = str(as_of or local_today_iso())[:10]
    try:
        as_of_d = datetime.strptime(as_of_s, "%Y-%m-%d").date()
    except ValueError:
        as_of_d = datetime.strptime(local_today_iso(), "%Y-%m-%d").date()
        as_of_s = as_of_d.isoformat()

    code_list = [_norm_code(c) for c in codes if _norm_code(c)]
    code_set = set(code_list)
    news_cut = (as_of_d - timedelta(days=WINDOW_DAYS["news"])).isoformat()
    notice_cut = (as_of_d - timedelta(days=WINDOW_DAYS["notice"])).isoformat()
    move_cut = (as_of_d - timedelta(days=WINDOW_DAYS["move"])).isoformat()
    market_cut = (as_of_d - timedelta(days=WINDOW_DAYS["market_news"])).isoformat()

    reasons: List[Dict[str, Any]] = []
    moves: List[Dict[str, Any]] = []

    if code_list:
        placeholders = ",".join("?" * len(code_list))
        try:
            rows = conn.execute(
                f"""
                SELECT code, published_at, title, content, source, url
                FROM news_cache
                WHERE code IN ({placeholders}) AND published_at >= ?
                """,
                code_list + [news_cut],
            ).fetchall()
            for row in rows:
                published = row["published_at"] if hasattr(row, "keys") else row[1]
                if _date_of(published) < news_cut or _date_of(published) > as_of_s:
                    continue
                reasons.append(
                    {
                        "code": row["code"] if hasattr(row, "keys") else row[0],
                        "kind": "news",
                        "title": row["title"] if hasattr(row, "keys") else row[2],
                        "content": row["content"] if hasattr(row, "keys") else row[3],
                        "source": row["source"] if hasattr(row, "keys") else row[4],
                        "url": row["url"] if hasattr(row, "keys") else row[5],
                        "published_at": published,
                    }
                )
        except sqlite3.OperationalError:
            pass
        try:
            rows = conn.execute(
                f"""
                SELECT code, date, title, name, notice_type, url
                FROM notice_cache
                WHERE code IN ({placeholders}) AND date >= ?
                """,
                code_list + [notice_cut],
            ).fetchall()
            for row in rows:
                day = row["date"] if hasattr(row, "keys") else row[1]
                if _date_of(day) < notice_cut or _date_of(day) > as_of_s:
                    continue
                reasons.append(
                    {
                        "code": row["code"] if hasattr(row, "keys") else row[0],
                        "kind": "notice",
                        "title": row["title"] if hasattr(row, "keys") else row[2],
                        "name": row["name"] if hasattr(row, "keys") else row[3],
                        "notice_type": row["notice_type"] if hasattr(row, "keys") else row[4],
                        "url": row["url"] if hasattr(row, "keys") else row[5],
                        "date": day,
                    }
                )
        except sqlite3.OperationalError:
            pass
        try:
            rows = conn.execute(
                f"""
                SELECT date, code, board, event_time, name
                FROM intraday_move_cache
                WHERE code IN ({placeholders}) AND date >= ?
                """,
                code_list + [move_cut],
            ).fetchall()
            for row in rows:
                day = row["date"] if hasattr(row, "keys") else row[0]
                if _date_of(day) < move_cut or _date_of(day) > as_of_s:
                    continue
                moves.append(
                    {
                        "date": day,
                        "code": row["code"] if hasattr(row, "keys") else row[1],
                        "board": row["board"] if hasattr(row, "keys") else row[2],
                        "event_time": row["event_time"] if hasattr(row, "keys") else row[3],
                        "name": row["name"] if hasattr(row, "keys") else row[4],
                        "kind": "move",
                        "title": "%s %s"
                        % (
                            row["board"] if hasattr(row, "keys") else row[2],
                            row["name"] if hasattr(row, "keys") else row[4],
                        ),
                    }
                )
        except sqlite3.OperationalError:
            pass

    try:
        rows = conn.execute(
            "SELECT date, published_at, title, content FROM market_news_cache WHERE date >= ?",
            (market_cut,),
        ).fetchall()
        for row in rows:
            day = row["date"] if hasattr(row, "keys") else row[0]
            published = row["published_at"] if hasattr(row, "keys") else row[1]
            stamp = _date_of(published) or _date_of(day)
            if stamp < market_cut or stamp > as_of_s:
                continue
            reasons.append(
                {
                    "kind": "market_news",
                    "title": row["title"] if hasattr(row, "keys") else row[2],
                    "content": row["content"] if hasattr(row, "keys") else row[3],
                    "published_at": published,
                    "date": day,
                }
            )
    except sqlite3.OperationalError:
        pass

    def _stamp(item: Dict[str, Any]) -> str:
        return str(item.get("published_at") or item.get("date") or item.get("event_time") or "")

    reasons.sort(key=_stamp, reverse=True)
    moves.sort(key=lambda m: str(m.get("event_time") or m.get("date") or ""), reverse=True)

    matched_codes = {
        str(item.get("code") or "")
        for item in list(reasons) + list(moves)
        if item.get("code") in code_set
    }
    matched = len(matched_codes)
    rest = max(0, len(code_set) - matched)
    if not code_list:
        note = "当前无持仓"
    elif not reasons and not moves:
        note = "窗口内无可对应信息（%s 只持仓）" % len(code_set)
    elif rest:
        note = "其余 %s 只持仓窗口内无可对应信息" % rest
    else:
        note = "窗口内持仓均有对应信息"

    return {
        "reasons": reasons,
        "moves": moves,
        "reason_coverage": {
            "matched": matched,
            "window_days": WINDOW_DAYS["notice"],
            "note": note,
        },
    }
