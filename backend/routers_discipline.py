import sqlite3
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from .database import db_session
    from .discipline import (
        build_discipline_report,
        confirm_draft,
        confirm_drafts,
        create_drafts_from_actions,
        delete_draft,
        get_policy,
        list_drafts,
        set_policy,
    )
except ImportError:
    from database import db_session
    from discipline import (
        build_discipline_report,
        confirm_draft,
        confirm_drafts,
        create_drafts_from_actions,
        delete_draft,
        get_policy,
        list_drafts,
        set_policy,
    )

router = APIRouter()


class PolicyBody(BaseModel):
    equity_min_pct: Optional[float] = None
    equity_max_pct: Optional[float] = None
    defensive_min_pct: Optional[float] = None
    single_holding_max_pct: Optional[float] = None
    named_limits: Optional[list] = None
    targets: Optional[dict] = None
    rebalance_band_pct: Optional[float] = None
    preferred_buy_code: Optional[str] = None
    preferred_buy_name: Optional[str] = None
    preferred_buy_category: Optional[str] = None
    preferred_buy_account: Optional[str] = None
    no_new_codes: Optional[list] = None
    fixed_income_categories: Optional[list] = None
    defensive_extra_categories: Optional[list] = None


class CreateDraftsBody(BaseModel):
    """If empty, generate drafts from current report actions."""
    actions: Optional[List[dict]] = None


class ConfirmDraftsBody(BaseModel):
    draft_ids: List[int] = Field(default_factory=list)


@router.get("/discipline/report")
def discipline_report():
    with db_session(row_factory=sqlite3.Row) as conn:
        return build_discipline_report(conn)


@router.get("/discipline/policy")
def discipline_get_policy():
    with db_session(row_factory=sqlite3.Row) as conn:
        return get_policy(conn)


@router.put("/discipline/policy")
def discipline_put_policy(body: PolicyBody):
    payload = body.model_dump(exclude_unset=True)
    try:
        with db_session(row_factory=sqlite3.Row) as conn:
            policy = set_policy(conn, payload)
            conn.commit()
        return {"status": "success", "policy": policy}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/discipline/drafts")
def discipline_list_drafts(status: Optional[str] = "draft"):
    with db_session(row_factory=sqlite3.Row) as conn:
        return list_drafts(conn, status=status)


@router.post("/discipline/drafts")
def discipline_create_drafts(body: CreateDraftsBody = CreateDraftsBody()):
    with db_session(row_factory=sqlite3.Row) as conn:
        result = create_drafts_from_actions(conn, actions=body.actions, use_report_actions=body.actions is None)
        conn.commit()
    return {"status": "success", **result}


@router.delete("/discipline/drafts/{draft_id}")
def discipline_delete_draft(draft_id: int):
    with db_session(row_factory=sqlite3.Row) as conn:
        ok = delete_draft(conn, draft_id)
        conn.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="草稿不存在或已确认")
    return {"status": "success", "id": draft_id}


@router.post("/discipline/drafts/{draft_id}/confirm")
def discipline_confirm_one(draft_id: int):
    try:
        with db_session(row_factory=sqlite3.Row) as conn:
            result = confirm_draft(conn, draft_id)
            conn.commit()
        return {"status": "success", **result}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/discipline/drafts/confirm")
def discipline_confirm_many(body: ConfirmDraftsBody):
    if not body.draft_ids:
        raise HTTPException(status_code=400, detail="请提供 draft_ids")
    with db_session(row_factory=sqlite3.Row) as conn:
        result = confirm_drafts(conn, body.draft_ids)
        conn.commit()
    return {"status": "success", **result}
