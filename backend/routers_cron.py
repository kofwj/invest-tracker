"""Cron-only HTTP endpoints.

These are the public contract for scripts/cron_sync_prices.sh.
Auth is X-Cron-Token only (independent from the login password).
Do not hang user-facing routers on this token — keep the blast radius small.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from .ai_weekly import run_weekly_brief
    from .dashboard import build_dashboard
    from .database import db_session, local_today_iso
    from .heartbeat import check_heartbeats, record_and_ping
    from .market import check_alerts
    from .notify import run_scheduled_events
    from .reason_cache import refresh_reasons
    from .routers_holdings import _sync_prices_impl
    from .snapshots import create_snapshot_record, resolve_snapshot_price_state
    from .trading_calendar import trading_day_status
except ImportError:
    from ai_weekly import run_weekly_brief
    from dashboard import build_dashboard
    from database import db_session, local_today_iso
    from heartbeat import check_heartbeats, record_and_ping
    from market import check_alerts
    from notify import run_scheduled_events
    from reason_cache import refresh_reasons
    from routers_holdings import _sync_prices_impl
    from snapshots import create_snapshot_record, resolve_snapshot_price_state
    from trading_calendar import trading_day_status

router = APIRouter()


class CronAlertCheckBody(BaseModel):
    notify: bool = False
    webhook: Optional[str] = None


class CronNotifyBody(BaseModel):
    deposit: bool = True
    discipline: bool = True
    dividend: bool = True
    force: bool = False

@router.post("/cron/sync-prices")
def cron_sync_prices():
    return _sync_prices_impl(backup=False)


@router.get("/cron/trading-day")
def cron_trading_day(date: Optional[str] = None):
    with db_session(row_factory=sqlite3.Row) as conn:
        try:
            return trading_day_status(date or None, conn=conn)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/cron/snapshot")
def cron_snapshot():
    with db_session(row_factory=sqlite3.Row) as conn:
        dash = build_dashboard(conn)
        today = local_today_iso()
        # 价格闸门：最新价不是今天的 → 不写库（cron 只把响应 JSON 打进日志，
        # 所以返回 200 + skipped 而不是抛异常，避免 cron 侧误报失败）。
        price_state = resolve_snapshot_price_state(conn, today)
        if price_state["needs_fresh_price"] and price_state["is_stale"]:
            conn.commit()  # 保留 build_dashboard 的既有副作用（如现金基准），不写快照行
            # 心跳也要记：被闸门拦下算「没跑成」（不刷 last_ok_at）。连续 96h 都拦下，
            # /cron/notify-events 会喊；否则价格源悄悄全挂时，净值曲线只是静静停在旧日期上。
            record_and_ping(
                conn,
                "snapshot",
                ok=False,
                detail=f"price_stale price_date={price_state['price_date']}",
            )
            return {
                "status": "skipped",
                "reason": "price_stale",
                "price_date": price_state["price_date"],
            }
        snapshot_id, action = create_snapshot_record(conn, today, dash)
        record_and_ping(conn, "snapshot", ok=True, detail=f"action={action} id={snapshot_id}")
        conn.commit()
    return {
        "status": "success",
        "action": action,
        "id": snapshot_id,
        "date": today,
        "lifetime_profit": dash.get("lifetime_profit"),
    }


class CronHeartbeatBody(BaseModel):
    job: str
    ok: bool = True
    detail: str = ""


@router.post("/cron/heartbeat")
def cron_heartbeat(body: CronHeartbeatBody):
    """流水线自报心跳（scripts/backup_daily.sh 这类外部脚本用）。

    ``ok=false`` 只留痕、不刷 ``last_ok_at``：「最后一次成功」自然变旧，
    由 check_heartbeats 统一按阈值喊人，避免两处各判断一套。
    """
    job = str(body.job or "").strip()
    if not job:
        raise HTTPException(status_code=400, detail="job 不能为空")
    with db_session() as conn:
        result = record_and_ping(conn, job, ok=bool(body.ok), detail=body.detail)
        conn.commit()
    return {"status": "success", **result}


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
            dividend=body.dividend,
            force=body.force,
        )
        # 顺手判一次流水线心跳逾期，用户不用为它再改一遍 crontab。
        # check_heartbeats 自己吞掉通知异常，不会把定时事件推送带挂。
        heartbeat = check_heartbeats(conn, force=body.force)
        conn.commit()
    return {"status": "success", **result, "heartbeat": heartbeat}


class CronWeeklyBody(BaseModel):
    notify: bool = True
    force: bool = False


@router.post("/cron/weekly-brief")
def cron_weekly_brief(body: CronWeeklyBody = CronWeeklyBody()):
    """周报（N2）：按周缓存 —— 同一周只调一次模型；notify=false 只生成不推送。"""
    with db_session() as conn:
        result = run_weekly_brief(conn, notify=body.notify, force=body.force)
        conn.commit()
    return {"status": "success", **result}


class CronRefreshReasonsBody(BaseModel):
    force: bool = False


@router.post("/cron/refresh-reasons")
def cron_refresh_reasons(body: CronRefreshReasonsBody = CronRefreshReasonsBody()):
    with db_session() as conn:
        result = refresh_reasons(conn, force=bool(body.force))
        conn.commit()
    return {"status": "success", **result}