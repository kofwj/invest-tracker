import logging
from datetime import date as dt_date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

try:
    from .csv_utils import (
        create_import_backup,
        create_safety_backup,
        csv_response,
        normalize_csv_row,
        normalize_date_string,
        parse_float,
        read_upload_csv,
    )
    from .database import db_session, local_today_iso
    from .dividend_sync import (
        DEFAULT_LOOKBACK_DAYS,
        confirm_dividend_drafts,
        scan_dividend_drafts,
    )
    from .holding_calculator import infer_category, recalc_holdings
except ImportError:
    from csv_utils import (
        create_import_backup,
        create_safety_backup,
        csv_response,
        normalize_csv_row,
        normalize_date_string,
        parse_float,
        read_upload_csv,
    )
    from database import db_session, local_today_iso
    from dividend_sync import (
        DEFAULT_LOOKBACK_DAYS,
        confirm_dividend_drafts,
        scan_dividend_drafts,
    )
    from holding_calculator import infer_category, recalc_holdings

import sqlite3

DIVIDEND_CSV_COLUMNS = ["date", "account", "code", "name", "category", "amount", "fee", "remark"]

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


@router.get("/dividends/scan", deprecated=True)
def scan_dividends_get(lookback_days: int = DEFAULT_LOOKBACK_DAYS, codes: Optional[str] = None):
    """已弃用：请用 POST /dividends/scan。GET 仍可用，避免误依赖为唯一入口。"""
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


@router.get("/dividends/template")
def download_dividend_template():
    """下载分红手工模板（纯现金分红专用，数量/单价固定为0）。"""
    rows = [
        [local_today_iso(), "华泰证券", "601288", "农业银行", "A股权益", "1234.56", "0", "手工补录：某债基或不支持标的的分红"],
        [local_today_iso(), "华泰证券", "f004388", "鹏华丰享", "债基", "80.00", "0", "场外基金分红示例"],
    ]
    return csv_response("dividends_template.csv", DIVIDEND_CSV_COLUMNS, rows)


@router.post("/dividends/import")
def import_dividends(file: UploadFile = File(...)):
    """从CSV导入手工分红（direction 固定为'分红'，qty/price=0）。"""
    if not (file and file.filename and file.filename.lower().endswith(".csv")):
        raise HTTPException(status_code=400, detail="请上传 .csv 文件")

    content = file.file.read()
    backup_path = create_import_backup("before_import_dividends")

    rows = read_upload_csv(content)
    aliases = {
        "date": "date", "日期": "date",
        "account": "account", "证券账户": "account", "账户": "account",
        "code": "code", "代码": "code",
        "name": "name", "名称": "name",
        "category": "category", "分类": "category",
        "amount": "amount", "金额": "amount", "总金额": "amount",
        "fee": "fee", "手续费": "fee",
        "remark": "remark", "备注": "remark",
    }

    success = 0
    errors = []
    affected_codes = set()

    try:
        with db_session(row_factory=sqlite3.Row) as conn:
            for idx, raw in enumerate(rows):
                try:
                    row = normalize_csv_row(raw, aliases)
                    if not row.get("date") or not row.get("code"):
                        raise ValueError("日期和代码必填")

                    date_str = normalize_date_string(row.get("date"))
                    code = str(row.get("code") or "").strip()
                    name = str(row.get("name") or "").strip() or code
                    category = row.get("category") or infer_category(code, name)
                    account = row.get("account") or "华泰证券"
                    amount = parse_float(row.get("amount"), 0.0)
                    fee = parse_float(row.get("fee"), 0.0)
                    remark = str(row.get("remark") or "").strip() or "手工分红导入"

                    if amount <= 0:
                        raise ValueError("分红金额必须 > 0")

                    conn.execute(
                        """
                        INSERT INTO transactions
                        (date, code, name, category, account, direction, quantity, price, amount, fee, remark)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (date_str, code, name, category, account, "分红", 0.0, 0.0, amount, fee, remark),
                    )
                    affected_codes.add(code)
                    success += 1
                except Exception as e:
                    errors.append({"row": idx + 1, "error": str(e)})

            if success > 0:
                recalc_holdings(conn, codes=list(affected_codes) if affected_codes else None)
            conn.commit()
    except Exception as e:
        logger.exception("dividend import failed")
        raise HTTPException(status_code=500, detail=f"分红导入失败: {e}")

    return {
        "status": "success",
        "imported": success,
        "failed": len(errors),
        "errors": errors[:30],
        "backup": backup_path,
        "affected_codes": list(affected_codes),
    }
