import sqlite3
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

try:
    from .database import db_session
    from .market import (
        build_market_summary,
        check_alerts,
        clear_alert_events,
        create_alert_rule,
        delete_alert_rule,
        export_alert_events_csv,
        get_watchlist,
        list_alert_events,
        list_alert_rules,
        set_watchlist,
        update_alert_rule,
    )
    from .trading_calendar import trading_day_status
except ImportError:
    from database import db_session
    from market import (
        build_market_summary,
        check_alerts,
        clear_alert_events,
        create_alert_rule,
        delete_alert_rule,
        export_alert_events_csv,
        get_watchlist,
        list_alert_events,
        list_alert_rules,
        set_watchlist,
        update_alert_rule,
    )
    from trading_calendar import trading_day_status

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
    respect_cooldown: bool = True


class WatchlistItem(BaseModel):
    code: str
    name: Optional[str] = ""
    secid: Optional[str] = ""


class WatchlistBody(BaseModel):
    items: List[WatchlistItem] = Field(default_factory=list)


class ClearEventsBody(BaseModel):
    code: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    clear_all: bool = False


@router.get("/market/summary")
def market_summary():
    with db_session(row_factory=sqlite3.Row) as conn:
        data = build_market_summary(conn)
        conn.commit()
    return data


@router.get("/market/trading-day")
def market_trading_day(date: Optional[str] = None):
    with db_session(row_factory=sqlite3.Row) as conn:
        return trading_day_status(date, conn=conn)


@router.get("/market/watchlist")
def market_get_watchlist():
    with db_session(row_factory=sqlite3.Row) as conn:
        return get_watchlist(conn)


@router.put("/market/watchlist")
def market_put_watchlist(body: WatchlistBody):
    with db_session(row_factory=sqlite3.Row) as conn:
        items = set_watchlist(conn, [x.model_dump() for x in body.items])
        conn.commit()
    return {"status": "success", "items": items}


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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    with db_session(row_factory=sqlite3.Row) as conn:
        return list_alert_events(
            conn, limit=limit, code=code, start_date=start_date, end_date=end_date
        )


@router.get("/market/alert-events/export")
def export_alert_events(
    limit: int = Query(500, ge=1, le=2000),
    code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    with db_session(row_factory=sqlite3.Row) as conn:
        content = export_alert_events_csv(
            conn, limit=limit, code=code, start_date=start_date, end_date=end_date
        )
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=alert_events.csv"},
    )


@router.post("/market/alert-events/clear")
def post_clear_alert_events(body: ClearEventsBody = ClearEventsBody()):
    with db_session(row_factory=sqlite3.Row) as conn:
        if body.clear_all:
            deleted = clear_alert_events(conn)
        else:
            if not (body.code or body.start_date or body.end_date):
                raise HTTPException(
                    status_code=400,
                    detail="请指定 code/start_date/end_date，或设置 clear_all=true",
                )
            deleted = clear_alert_events(
                conn,
                code=body.code,
                start_date=body.start_date,
                end_date=body.end_date,
            )
        conn.commit()
    return {"status": "success", "deleted": deleted}


@router.post("/market/alerts/check")
def post_alerts_check(body: AlertCheckRequest = AlertCheckRequest()):
    notify = bool(body.notify)
    with db_session(row_factory=sqlite3.Row) as conn:
        result = check_alerts(
            conn,
            record_events=True,
            notify=notify,
            respect_cooldown=bool(body.respect_cooldown),
        )
        conn.commit()
    return result
