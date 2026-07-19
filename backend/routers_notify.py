"""Notify API: status, settings, test, deposit/discipline checks, scheduled run."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from .database import db_session
    from .notify import (
        check_deposit_due,
        check_discipline_summary,
        dispatch,
        list_notify_logs,
        notify_deposit_due,
        notify_discipline,
        notify_status,
        run_scheduled_events,
        save_notify_settings,
    )
except ImportError:
    from database import db_session
    from notify import (
        check_deposit_due,
        check_discipline_summary,
        dispatch,
        list_notify_logs,
        notify_deposit_due,
        notify_discipline,
        notify_status,
        run_scheduled_events,
        save_notify_settings,
    )

router = APIRouter(tags=["notify"])


class NotifyTestBody(BaseModel):
    text: str = "invest-tracker 通知测试"
    title: str = "测试推送"
    channels: Optional[List[str]] = None
    event: str = "test"
    force: bool = True


class NotifySettingsBody(BaseModel):
    enabled: Optional[bool] = None
    cooldown_minutes: Optional[int] = Field(default=None, ge=0, le=10080)
    template: Optional[str] = None  # short | medium
    event_channels: Optional[Dict[str, Any]] = None


class NotifyRunBody(BaseModel):
    deposit: bool = True
    discipline: bool = True
    force: bool = False


@router.get("/notify/status")
def get_notify_status():
    with db_session() as conn:
        return notify_status(conn)


@router.put("/notify/settings")
def put_notify_settings(body: NotifySettingsBody):
    if body.template is not None and body.template not in ("short", "medium"):
        raise HTTPException(status_code=400, detail="template 只能是 short 或 medium")
    with db_session() as conn:
        data = save_notify_settings(
            conn,
            enabled=body.enabled,
            cooldown_minutes=body.cooldown_minutes,
            template=body.template,
            event_channels=body.event_channels,
        )
        conn.commit()
    return data


@router.get("/notify/logs")
def get_notify_logs(limit: int = 20):
    with db_session() as conn:
        return {"items": list_notify_logs(conn, limit=limit)}


@router.post("/notify/test")
def post_notify_test(body: NotifyTestBody = NotifyTestBody()):
    with db_session() as conn:
        result = dispatch(
            body.text,
            title=body.title,
            event=body.event or "test",
            channels=body.channels,
            conn=conn,
            force=bool(body.force),
            respect_cooldown=False,
        )
        conn.commit()
    return result


@router.get("/notify/deposit-due")
def get_deposit_due():
    with db_session() as conn:
        return check_deposit_due(conn)


@router.post("/notify/deposit-due")
def post_deposit_due(force: bool = False):
    with db_session() as conn:
        result = notify_deposit_due(conn, force=force)
        conn.commit()
    return result


@router.get("/notify/discipline")
def get_discipline_notify_preview():
    with db_session() as conn:
        return check_discipline_summary(conn)


@router.post("/notify/discipline")
def post_discipline_notify(force: bool = False, only_if_breaches: bool = True):
    with db_session() as conn:
        result = notify_discipline(conn, force=force, only_if_breaches=only_if_breaches)
        conn.commit()
    return result


@router.post("/notify/run")
def post_notify_run(body: NotifyRunBody = NotifyRunBody()):
    """Cron / manual: deposit due + discipline breaches."""
    with db_session() as conn:
        result = run_scheduled_events(
            conn,
            deposit=body.deposit,
            discipline=body.discipline,
            force=body.force,
        )
        conn.commit()
    return result
