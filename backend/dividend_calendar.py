"""N5 ex-dividend calendar: after-hours fetch, local table, upcoming reminders.

Task order is fixed: fetch → filter usable → upsert → prune → compute windows → notify.
Fetch failures never wipe unexpired rows of current targets. Calendar HTTP reads the local table only.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

try:
    from .cash import set_setting
    from .database import LOCAL_TZ, local_today_iso
    from .dividend_sync import (
        _cash_per_share,
        _event_usable,
        dividend_asset_kind,
        fetch_market_dividend_rows,
        normalize_code,
        parse_date_value,
    )
    from .market import get_watchlist
except ImportError:
    from cash import set_setting
    from database import LOCAL_TZ, local_today_iso
    from dividend_sync import (
        _cash_per_share,
        _event_usable,
        dividend_asset_kind,
        fetch_market_dividend_rows,
        normalize_code,
        parse_date_value,
    )
    from market import get_watchlist

SOURCE_STATUS_KEY = "dividend_events_source_status"
FETCHED_AT_KEY = "dividend_events_fetched_at"
FAILED_CODES_KEY = "dividend_events_failed_codes"
NOTIFY_STAMP_KEY = "dividend_upcoming_notify_stamp"
DEFAULT_WINDOWS = (0, 3, 7)
INGEST_LOOKBACK_DAYS = 14
OVERDUE_MAX_DAYS = 7
RETENTION_DAYS = 30


def _now_local() -> datetime:
    if LOCAL_TZ is not None:
        return datetime.now(LOCAL_TZ).replace(tzinfo=None)
    return datetime.now()


def _as_dict(row: Any, columns: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return dict(row)
    if columns:
        return {columns[i]: row[i] for i in range(min(len(columns), len(row)))}
    return {}


def _get_setting(conn, key: str) -> Optional[str]:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    value = row["value"] if hasattr(row, "keys") else row[0]
    return None if value is None else str(value)


def _prefer(old: Any, new: Any) -> Any:
    """Keep existing non-empty values when the incoming value is empty."""
    if new in (None, ""):
        return old
    return new


def _prefer_num(old: Any, new: Any) -> Any:
    if new in (None, ""):
        return old
    try:
        value = float(new)
    except (TypeError, ValueError):
        return old
    if value <= 0:
        return old
    return value


def ensure_dividend_event_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dividend_events (
            code TEXT NOT NULL,
            name TEXT,
            ex_date TEXT NOT NULL,
            record_date TEXT,
            per_share REAL,
            plan_text TEXT,
            source TEXT,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (code, ex_date)
        )
        """
    )


def load_calendar_targets(conn) -> Tuple[List[Dict[str, str]], bool]:
    """Holdings qty>0 ∪ watchlist. Second value is False if a source query failed."""
    seen = set()
    out: List[Dict[str, str]] = []
    holdings_ok = True
    watch_ok = True

    try:
        rows = conn.execute(
            "SELECT code, name, category FROM holdings WHERE quantity > 0"
        ).fetchall()
    except Exception:
        logger.exception("calendar_targets: holdings failed")
        rows = []
        holdings_ok = False
    for row in rows:
        item = _as_dict(row, ("code", "name", "category"))
        code = normalize_code(item.get("code"))
        if not code or code in seen:
            continue
        name = str(item.get("name") or code)
        kind = dividend_asset_kind(code, item.get("category"), name)
        if kind is None:
            continue
        seen.add(code)
        out.append({"code": code, "name": name, "kind": kind})

    try:
        watch = get_watchlist(conn) or []
    except Exception:
        logger.exception("calendar_targets: watchlist failed")
        watch = []
        watch_ok = False
    for item in watch:
        if not isinstance(item, dict):
            continue
        code = normalize_code(item.get("code"))
        if not code or code in seen:
            continue
        name = str(item.get("name") or code)
        kind = dividend_asset_kind(code, None, name)
        if kind is None:
            continue
        seen.add(code)
        out.append({"code": code, "name": name, "kind": kind})
    return out, holdings_ok and watch_ok


def calendar_targets(conn) -> List[Dict[str, str]]:
    items, _ok = load_calendar_targets(conn)
    return items


def _event_from_market_row(target: Dict[str, str], row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict) or not _event_usable(row):
        return None
    ex = parse_date_value(row.get("EX_DIVIDEND_DATE"))
    if ex is None:
        return None
    record = parse_date_value(row.get("EQUITY_RECORD_DATE"))
    per_share = _cash_per_share(row)
    return {
        "code": target["code"],
        "name": target.get("name") or target["code"],
        "ex_date": ex.isoformat(),
        "record_date": record.isoformat() if record else None,
        "per_share": per_share,
        "plan_text": str(row.get("IMPL_PLAN_PROFILE") or "").strip() or None,
        "source": str(row.get("_source") or "").strip() or None,
        "fetched_at": _now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _upsert_event(conn, event: Dict[str, Any]) -> str:
    code = event["code"]
    ex_date = event["ex_date"]
    existing = conn.execute(
        "SELECT code, name, ex_date, record_date, per_share, plan_text, source, fetched_at "
        "FROM dividend_events WHERE code = ? AND ex_date = ?",
        (code, ex_date),
    ).fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO dividend_events
                (code, name, ex_date, record_date, per_share, plan_text, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                event.get("name") or code,
                ex_date,
                event.get("record_date"),
                event.get("per_share"),
                event.get("plan_text"),
                event.get("source"),
                event.get("fetched_at"),
            ),
        )
        return "insert"

    old = _as_dict(existing, ("code", "name", "ex_date", "record_date", "per_share", "plan_text", "source", "fetched_at"))
    conn.execute(
        """
        UPDATE dividend_events
        SET name = ?, record_date = ?, per_share = ?, plan_text = ?, source = ?, fetched_at = ?
        WHERE code = ? AND ex_date = ?
        """,
        (
            _prefer(old.get("name"), event.get("name")),
            _prefer(old.get("record_date"), event.get("record_date")),
            _prefer_num(old.get("per_share"), event.get("per_share")),
            _prefer(old.get("plan_text"), event.get("plan_text")),
            _prefer(old.get("source"), event.get("source")),
            event.get("fetched_at") or old.get("fetched_at"),
            code,
            ex_date,
        ),
    )
    return "update"


def _has_unexpired_events(conn, today: Optional[date] = None) -> bool:
    """True if local table still has an ex-date on or after today."""
    if today is None:
        today = date.fromisoformat(local_today_iso())
    try:
        row = conn.execute(
            "SELECT 1 FROM dividend_events WHERE ex_date >= ? LIMIT 1",
            (today.isoformat(),),
        ).fetchone()
    except Exception:
        return False
    return bool(row)


def cleanup_dividend_events(
    conn,
    *,
    today: Optional[date] = None,
    keep_codes: Optional[Sequence[str]] = None,
    targets_ok: bool = True,
) -> Dict[str, int]:
    """Drop sold/watchlist-removed codes and rows older than RETENTION_DAYS.

    If target lists could not be read, skip the code prune so a transient
    query failure cannot wipe the table.
    """
    ensure_dividend_event_tables(conn)
    if today is None:
        today = date.fromisoformat(local_today_iso())
    if keep_codes is None:
        items, targets_ok = load_calendar_targets(conn)
        keep_codes = [item["code"] for item in items]
    cutoff = (today - timedelta(days=RETENTION_DAYS)).isoformat()
    dropped_old = 0
    dropped_codes = 0
    try:
        cur = conn.execute("DELETE FROM dividend_events WHERE ex_date < ?", (cutoff,))
        dropped_old = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        if not targets_ok:
            return {"dropped_old": dropped_old, "dropped_codes": 0}
        if keep_codes:
            placeholders = ",".join("?" * len(keep_codes))
            cur = conn.execute(
                "DELETE FROM dividend_events WHERE code NOT IN (%s)" % placeholders,
                list(keep_codes),
            )
        else:
            cur = conn.execute("DELETE FROM dividend_events")
        dropped_codes = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    except Exception:
        logger.exception("cleanup_dividend_events failed")
    return {"dropped_old": dropped_old, "dropped_codes": dropped_codes}



def refresh_dividend_events(
    conn,
    *,
    fetch_fn: Optional[Callable[[str, str], List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Fetch after hours for holdings/watchlist. Never raises. Prunes sold/old rows."""
    ensure_dividend_event_tables(conn)
    fetcher = fetch_fn or fetch_market_dividend_rows
    targets, targets_ok = load_calendar_targets(conn)
    today = date.fromisoformat(local_today_iso())
    lookback_start = today - timedelta(days=INGEST_LOOKBACK_DAYS)
    inserted = 0
    updated = 0
    failed: List[str] = []
    ok_codes: List[str] = []

    for target in targets:
        code = target["code"]
        try:
            rows = fetcher(code, target["kind"]) or []
        except Exception:
            logger.exception("refresh_dividend_events: fetch failed for %s", code)
            failed.append(code)
            continue
        if not isinstance(rows, list):
            rows = []
        ok_codes.append(code)
        for row in rows:
            event = _event_from_market_row(target, row)
            if not event:
                continue
            ex = parse_date_value(event.get("ex_date"))
            if ex is None or ex < lookback_start:
                continue
            try:
                action = _upsert_event(conn, event)
            except Exception:
                logger.exception("refresh_dividend_events: upsert failed for %s", code)
                continue
            if action == "insert":
                inserted += 1
            else:
                updated += 1

    cleanup_dividend_events(
        conn,
        today=today,
        keep_codes=[item["code"] for item in targets],
        targets_ok=targets_ok,
    )
    fetch_failed_all = bool(targets) and not ok_codes
    has_local = _has_unexpired_events(conn, today=today)
    if fetch_failed_all and has_local:
        source_status = "stale"
    elif fetch_failed_all:
        source_status = "unavailable"
    elif failed or not targets_ok:
        source_status = "partial"
    else:
        source_status = "ok"

    fetched_at = _now_local().strftime("%Y-%m-%d %H:%M:%S")
    try:
        set_setting(conn, SOURCE_STATUS_KEY, source_status)
        set_setting(conn, FETCHED_AT_KEY, fetched_at)
        set_setting(conn, FAILED_CODES_KEY, ",".join(failed))
    except Exception:
        logger.exception("refresh_dividend_events: stamp settings failed")

    return {
        "ok": not fetch_failed_all,
        "source_status": source_status,
        "targets": len(targets),
        "fetched_ok": len(ok_codes),
        "failed_codes": failed,
        "inserted": inserted,
        "updated": updated,
        "fetched_at": fetched_at,
    }


def _bucket_for(days_left: int, windows: Sequence[int]) -> Optional[str]:
    vals = list(windows)
    w0 = vals[0] if len(vals) > 0 else 0
    w3 = vals[1] if len(vals) > 1 else 3
    w7 = vals[2] if len(vals) > 2 else 7
    if days_left < 0:
        if days_left < -OVERDUE_MAX_DAYS:
            return None
        return "overdue"
    if days_left == w0:
        return "d0"
    if days_left <= w3:
        return "d3"
    if days_left <= w7:
        return "d7"
    return None


def check_dividend_upcoming(
    conn,
    *,
    windows: Sequence[int] = DEFAULT_WINDOWS,
    today: Optional[date] = None,
    source_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Upcoming ex-dates from the local table. Never fetches."""
    ensure_dividend_event_tables(conn)
    if today is None:
        today = date.fromisoformat(local_today_iso())
    if source_status is None:
        source_status = _get_setting(conn, SOURCE_STATUS_KEY) or "ok"

    buckets: Dict[str, List[Dict[str, Any]]] = {
        "overdue": [],
        "d0": [],
        "d3": [],
        "d7": [],
    }
    try:
        rows = conn.execute(
            "SELECT code, name, ex_date, record_date, per_share, plan_text, source "
            "FROM dividend_events"
        ).fetchall()
    except Exception:
        logger.exception("check_dividend_upcoming: read failed")
        rows = []

    for row in rows:
        item = _as_dict(row, ("code", "name", "ex_date", "record_date", "per_share", "plan_text", "source"))
        ex = parse_date_value(item.get("ex_date"))
        if ex is None:
            continue
        days_left = (ex - today).days
        bucket = _bucket_for(days_left, windows)
        if bucket is None:
            continue
        payload = {
            "code": item.get("code"),
            "name": item.get("name") or item.get("code"),
            "ex_date": ex.isoformat(),
            "record_date": item.get("record_date"),
            "per_share": item.get("per_share"),
            "plan_text": item.get("plan_text"),
            "days_left": days_left,
        }
        buckets[bucket].append(payload)

    for key in ("d0", "d3", "d7"):
        buckets[key].sort(key=lambda x: (x.get("ex_date") or "", x.get("code") or ""))
    buckets["overdue"].sort(key=lambda x: (x.get("code") or ""))
    buckets["overdue"].sort(key=lambda x: (x.get("ex_date") or ""), reverse=True)

    lines: List[str] = []
    if buckets["overdue"]:
        lines.append("⚠ 除权除息日已过：")
        for item in buckets["overdue"][:10]:
            lines.append(
                "· %s(%s) 除权除息 %s（过期 %s 天）"
                % (item["name"], item["code"], item["ex_date"], abs(int(item["days_left"])))
            )
    if buckets["d0"]:
        lines.append("今天除权除息：")
        for item in buckets["d0"][:10]:
            extra = (" %s" % item["plan_text"]) if item.get("plan_text") else ""
            lines.append("· %s(%s)%s" % (item["name"], item["code"], extra))
    if buckets["d3"]:
        lines.append("3 天内除权除息：")
        for item in buckets["d3"][:10]:
            lines.append(
                "· %s(%s) → %s（剩 %s 天）"
                % (item["name"], item["code"], item["ex_date"], item["days_left"])
            )
    if buckets["d7"]:
        lines.append("7 天内除权除息：")
        for item in buckets["d7"][:10]:
            lines.append(
                "· %s(%s) → %s（剩 %s 天）"
                % (item["name"], item["code"], item["ex_date"], item["days_left"])
            )

    count = sum(len(v) for v in buckets.values())
    if not count:
        text = "近 7 天内无除权除息。"
    else:
        text = "\n".join(lines)
        if source_status == "stale":
            text = "（数据可能过期，上次抓取失败）\n" + text
        elif source_status == "partial":
            text = "（部分标的抓取失败）\n" + text

    return {
        "count": count,
        "buckets": buckets,
        "text": text,
        "has_actionable": count > 0,
        "source_status": source_status,
    }


def list_dividend_calendar(
    conn,
    *,
    days: int = 30,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Read-only local calendar. Does not fetch or call a model."""
    ensure_dividend_event_tables(conn)
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 90))
    if today is None:
        today = date.fromisoformat(local_today_iso())
    end = today + timedelta(days=days)
    try:
        rows = conn.execute(
            """
            SELECT code, name, ex_date, record_date, per_share, plan_text, source, fetched_at
            FROM dividend_events
            WHERE ex_date >= ? AND ex_date <= ?
            ORDER BY ex_date ASC, code ASC
            """,
            (today.isoformat(), end.isoformat()),
        ).fetchall()
    except Exception:
        logger.exception("list_dividend_calendar: read failed")
        rows = []
    items = []
    for row in rows:
        item = _as_dict(row, ("code", "name", "ex_date", "record_date", "per_share", "plan_text", "source", "fetched_at"))
        ex = parse_date_value(item.get("ex_date"))
        days_left = (ex - today).days if ex else None
        items.append(
            {
                "code": item.get("code"),
                "name": item.get("name") or item.get("code"),
                "ex_date": item.get("ex_date"),
                "record_date": item.get("record_date"),
                "per_share": item.get("per_share"),
                "plan_text": item.get("plan_text"),
                "source": item.get("source"),
                "days_left": days_left,
            }
        )
    failed_raw = _get_setting(conn, FAILED_CODES_KEY) or ""
    failed_codes = [part.strip() for part in failed_raw.split(",") if part.strip()]
    return {
        "days": days,
        "as_of": today.isoformat(),
        "items": items,
        "source_status": _get_setting(conn, SOURCE_STATUS_KEY) or "ok",
        "fetched_at": _get_setting(conn, FETCHED_AT_KEY) or "",
        "failed_codes": failed_codes,
    }


def _notify_stamp(info: Dict[str, Any]) -> str:
    keys = []
    buckets = info.get("buckets") or {}
    for name in ("overdue", "d0", "d3", "d7"):
        for item in buckets.get(name) or []:
            keys.append("%s:%s" % (item.get("code") or "", item.get("ex_date") or ""))
    keys.sort()
    return local_today_iso() + "|" + ",".join(keys)


def notify_dividend_upcoming(
    conn,
    *,
    force: bool = False,
    source_status: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        from .notify import dispatch
    except ImportError:
        from notify import dispatch

    info = check_dividend_upcoming(conn, source_status=source_status)
    if not info.get("has_actionable") and not force:
        return {"sent": False, "reason": "nothing_due", "dividend": info, "results": []}

    stamp = _notify_stamp(info)
    if not force and stamp == (_get_setting(conn, NOTIFY_STAMP_KEY) or ""):
        return {"sent": False, "reason": "already_notified", "dividend": info, "results": []}

    # Reuse deposit_due channels; do not add an event key. Same-day stamp blocks repeats.
    result = dispatch(
        info["text"],
        title="除权除息提醒",
        event="deposit_due",
        conn=conn,
        force=force,
        respect_cooldown=False,
    )
    try:
        set_setting(conn, NOTIFY_STAMP_KEY, stamp)
    except Exception:
        logger.exception("notify_dividend_upcoming: stamp failed")
    result["dividend"] = info
    return result
