import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

try:
    from .database import db_session
    from .market import (
        build_market_summary,
        check_alerts,
        create_alert_rule,
        delete_alert_rule,
        list_alert_events,
        list_alert_rules,
        update_alert_rule,
    )
except ImportError:
    from database import db_session
    from market import (
        build_market_summary,
        check_alerts,
        create_alert_rule,
        delete_alert_rule,
        list_alert_events,
        list_alert_rules,
        update_alert_rule,
    )

router = APIRouter()


class AlertRuleCreate(BaseModel):
    target_type: str = Field(..., description="holding | index")
    code: str
    name: Optional[str] = ""
    condition: str = Field(..., description="above | below")
    threshold: float
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    target_type: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    condition: Optional[str] = None
    threshold: Optional[float] = None
    enabled: Optional[bool] = None


class AlertCheckRequest(BaseModel):
    notify: bool = False


@router.get("/market/summary")
def market_summary():
    with db_session(row_factory=sqlite3.Row) as conn:
        data = build_market_summary(conn)
        conn.commit()
    return data


@router.get("/market/alert-rules")
def get_alert_rules():
    with db_session(row_factory=sqlite3.Row) as conn:
        return list_alert_rules(conn)


@router.post("/market/alert-rules")
def post_alert_rule(body: AlertRuleCreate):
    try:
        with db_session(row_factory=sqlite3.Row) as conn:
            rule = create_alert_rule(
                conn,
                target_type=body.target_type,
                code=body.code,
                condition=body.condition,
                threshold=body.threshold,
                name=body.name or "",
                enabled=body.enabled,
            )
            conn.commit()
        return {"status": "success", "rule": rule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/market/alert-rules/{rule_id}")
def put_alert_rule(rule_id: int, body: AlertRuleUpdate):
    payload = body.model_dump(exclude_unset=True)
    try:
        with db_session(row_factory=sqlite3.Row) as conn:
            rule = update_alert_rule(conn, rule_id, payload)
            conn.commit()
        return {"status": "success", "rule": rule}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/market/alert-rules/{rule_id}")
def remove_alert_rule(rule_id: int):
    with db_session(row_factory=sqlite3.Row) as conn:
        ok = delete_alert_rule(conn, rule_id)
        conn.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"status": "success", "id": rule_id}


@router.get("/market/alert-events")
def get_alert_events(
    limit: int = Query(50, ge=1, le=500),
    code: Optional[str] = None,
):
    with db_session(row_factory=sqlite3.Row) as conn:
        return list_alert_events(conn, limit=limit, code=code)


@router.post("/market/alerts/check")
def post_alerts_check(body: AlertCheckRequest = AlertCheckRequest()):
    notify = bool(body.notify)
    with db_session(row_factory=sqlite3.Row) as conn:
        result = check_alerts(conn, record_events=True, notify=notify)
        conn.commit()
    return result
