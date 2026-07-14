"""A-share trading day helpers (weekends + known closed holidays).

Used by cron snapshot skip. Not a legal exchange feed — extend via
settings key `market_extra_closed_dates` (JSON list of YYYY-MM-DD) when needed.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Iterable, Optional, Set, Union

# Built-in A-share closed days (weekends excluded; weekends handled separately).
# Covers 2025–2027 major public holidays commonly observed by SSE/SZSE.
# Source: public holiday notices; adjust yearly via settings if exchange tweaks.
BUILTIN_CLOSED_DAYS: Set[str] = {
    # 2025
    "2025-01-01",
    "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
    "2025-02-01", "2025-02-02", "2025-02-03", "2025-02-04",
    "2025-04-04", "2025-04-05", "2025-04-06",
    "2025-05-01", "2025-05-02", "2025-05-03", "2025-05-04", "2025-05-05",
    "2025-05-31", "2025-06-01", "2025-06-02",
    "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-04",
    "2025-10-05", "2025-10-06", "2025-10-07", "2025-10-08",
    # 2026
    "2026-01-01", "2026-01-02",
    "2026-02-15", "2026-02-16", "2026-02-17", "2026-02-18",
    "2026-02-19", "2026-02-20", "2026-02-21", "2026-02-22", "2026-02-23",
    "2026-04-04", "2026-04-05", "2026-04-06",
    "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",
    "2026-06-19", "2026-06-20", "2026-06-21",
    "2026-09-25", "2026-09-26", "2026-09-27",
    "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
    "2026-10-05", "2026-10-06", "2026-10-07",
    # 2027 (provisional major blocks)
    "2027-01-01",
    "2027-02-06", "2027-02-07", "2027-02-08", "2027-02-09",
    "2027-02-10", "2027-02-11", "2027-02-12",
    "2027-04-03", "2027-04-04", "2027-04-05",
    "2027-05-01", "2027-05-02", "2027-05-03",
    "2027-06-09", "2027-06-10", "2027-06-11",
    "2027-09-15", "2027-09-16", "2027-09-17",
    "2027-10-01", "2027-10-02", "2027-10-03", "2027-10-04",
    "2027-10-05", "2027-10-06", "2027-10-07",
}


def _to_date(value: Union[str, date, datetime, None]) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _extra_closed_from_conn(conn) -> Set[str]:
    if conn is None:
        return set()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("market_extra_closed_dates",),
        ).fetchone()
    except Exception:
        return set()
    if not row:
        return set()
    raw = row["value"] if hasattr(row, "keys") else row[0]
    try:
        data = json.loads(raw or "[]")
    except Exception:
        return set()
    if not isinstance(data, list):
        return set()
    out = set()
    for item in data:
        d = _to_date(item)
        if d:
            out.add(d.isoformat())
    return out


def closed_day_set(conn=None, extra: Optional[Iterable[str]] = None) -> Set[str]:
    days = set(BUILTIN_CLOSED_DAYS)
    days |= _extra_closed_from_conn(conn)
    if extra:
        for item in extra:
            d = _to_date(item)
            if d:
                days.add(d.isoformat())
    return days


def is_a_share_trading_day(
    value: Union[str, date, datetime, None] = None,
    *,
    conn=None,
    extra: Optional[Iterable[str]] = None,
) -> bool:
    """True if the given calendar day is expected to be an A-share trading day."""
    d = _to_date(value)
    if d is None:
        d = date.today()
    # Sat=5 Sun=6
    if d.weekday() >= 5:
        return False
    if d.isoformat() in closed_day_set(conn, extra):
        return False
    return True


def trading_day_status(
    value: Union[str, date, datetime, None] = None,
    *,
    conn=None,
) -> dict:
    d = _to_date(value) or date.today()
    iso = d.isoformat()
    trading = is_a_share_trading_day(d, conn=conn)
    reason = "trading"
    if d.weekday() >= 5:
        reason = "weekend"
    elif iso in closed_day_set(conn):
        reason = "holiday"
    return {
        "date": iso,
        "is_trading_day": trading,
        "reason": reason if not trading else "trading",
    }
