"""Cron-only HTTP endpoints.

These are the public contract for scripts/cron_sync_prices.sh.
Auth is X-Cron-Token only (independent from the login password).
Do not hang user-facing routers on this token — keep the blast radius small.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

try:
    from .dashboard import build_dashboard
    from .database import db_session, local_today_iso
    from .market import check_alerts
    from .notify import run_scheduled_events
    from .routers_holdings import _sync_prices_impl
    from .snapshots import create_snapshot_record
    from .trading_calendar import trading_day_status
except ImportError:
    from dashboard import build_dashboard
    from database import db_session, local_today_iso
    from market import check_alerts
    from notify import run_scheduled_events
    from routers_holdings import _sync_prices_impl
    from snapshots import create_snapshot_record
    from trading_calendar import trading_day_status

router = APIRouter()


class CronAlertCheckBody(BaseModel):
    notify: bool = False
    webhook: Optional[str] = None


class CronNotifyBody(BaseModel):
    deposit: bool = True
    discipline: bool = True
    force: bool = False


@router.post("/cron/sync-prices")
def cron_sync_prices():
    return _sync_prices_impl(backup=False)


@router.get("/cron/trading-day")
def cron_trading_day(date: Optional[str] = None):
    with db_session(row_factory=sqlite3.Row) as conn:
        return trading_day_status(date or None, conn=conn)


@router.post("/cron/snapshot")
def cron_snapshot():
    with db_session(row_factory=sqlite3.Row) as conn:
        dash = build_dashboard(conn)
        today = local_today_iso()
        snapshot_id, action = create_snapshot_record(conn, today, dash)
        conn.commit()
    return {
        "status": "success",
        "action": action,
        "id": snapshot_id,
        "date": today,
        "lifetime_profit": dash.get("lifetime_profit"),
    }


@router.post("/cron/check-alerts")
def cron_check_alerts(body: CronAlertCheckBody = CronAlertCheckBody()):
    webhook = str(body.webhook or "").strip() or None
    with db_session(row_factory=sqlite3.Row) as conn:
        result = check_alerts(conn, record_events=True, notify=bool(body.notify), webhook=webhook)
        conn.commit()
    result["status"] = "success"
    return result


@router.post("/cron/notify-events")
def cron_notify_events(body: CronNotifyBody = CronNotifyBody()):
    with db_session() as conn:
        result = run_scheduled_events(
            conn,
            deposit=body.deposit,
            discipline=body.discipline,
            force=body.force,
        )
        conn.commit()
    return {"status": "success", **result}