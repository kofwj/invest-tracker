import logging
from datetime import date as dt_date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from .csv_utils import create_safety_backup
    from .database import db_session
    from .dividend_sync import (
        DEFAULT_LOOKBACK_DAYS,
        confirm_dividend_drafts,
        scan_dividend_drafts,
    )
    from .holding_calculator import recalc_holdings
except ImportError:
    from csv_utils import create_safety_backup
    from database import db_session
    from dividend_sync import (
        DEFAULT_LOOKBACK_DAYS,
        confirm_dividend_drafts,
        scan_dividend_drafts,
    )
    from holding_calculator import recalc_holdings

import sqlite3

logger = logging.getLogger(__name__)
router = APIRouter()


class DividendScanRequest(BaseModel):
    lookback_days: int = Field(default=DEFAULT_LOOKBACK_DAYS, ge=30, le=2000)
    codes: Optional[List[str]] = None


class DividendDraftConfirmItem(BaseModel):
    code: str
    name: Optional[str] = None
    category: Optional[str] = None
    account: Optional[str] = None
    event_date: dt_date
    amount: float
    fee: float = 0.0
    remark: Optional[str] = None
    plan_profile: Optional[str] = None
    direction: str = "分红"
    draft_key: Optional[str] = None


class DividendConfirmRequest(BaseModel):
    drafts: List[DividendDraftConfirmItem]
    backup: bool = True


@router.post("/dividends/scan")
def scan_dividends(payload: DividendScanRequest = DividendScanRequest()):
    """Scan holdings and return semi-automatic cash-dividend drafts with dedupe status."""
    try:
        with db_session(row_factory=sqlite3.Row) as conn:
            result = scan_dividend_drafts(
                conn,
                lookback_days=payload.lookback_days,
                codes=payload.codes,
            )
        return result
    except Exception as e:
        logger.exception("dividend scan failed")
        raise HTTPException(status_code=500, detail=f"分红扫描失败: {e}")


@router.get("/dividends/scan")
def scan_dividends_get(lookback_days: int = DEFAULT_LOOKBACK_DAYS, codes: Optional[str] = None):
    code_list = [c.strip() for c in (codes or "").split(",") if c.strip()] or None
    return scan_dividends(DividendScanRequest(lookback_days=lookback_days, codes=code_list))


@router.post("/dividends/confirm")
def confirm_dividends(payload: DividendConfirmRequest):
    """Confirm selected drafts and write them as 分红 transactions."""
    if not payload.drafts:
        raise HTTPException(status_code=400, detail="请至少选择一条分红草稿")

    backup_path = create_safety_backup("before_confirm_dividends") if payload.backup else None
    items = [d.model_dump() if hasattr(d, "model_dump") else d.dict() for d in payload.drafts]
    # normalize date fields to iso strings expected by confirm helper
    for item in items:
        if isinstance(item.get("event_date"), dt_date):
            item["event_date"] = item["event_date"].isoformat()

    try:
        with db_session(row_factory=sqlite3.Row) as conn:
            result = confirm_dividend_drafts(conn, items, recheck_existing=True)
            if result["created_count"] > 0:
                codes = {str(c.get("code") or "").strip() for c in result.get("created") or []}
                codes.discard("")
                recalc_holdings(conn, codes=codes or None)
            conn.commit()
    except Exception as e:
        logger.exception("dividend confirm failed")
        raise HTTPException(status_code=500, detail=f"确认分红失败: {e}")

    return {
        "status": "success",
        "backup": backup_path,
        **result,
    }
