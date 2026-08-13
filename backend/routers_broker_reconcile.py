"""券商对账单：上传 CSV/Excel → 差异清单 → 可选批量写入持仓校正（含应用后重扫）。"""

from __future__ import annotations

import math
import sqlite3
from datetime import date as dt_date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

try:
    from .broker_reconcile import compare_holdings, parse_broker_upload
    from .csv_utils import create_safety_backup, read_upload_bytes_limited
    from .database import db_session, local_today_iso
    from .holding_calculator import infer_category, recalc_holdings, validate_holding_history
    from .portfolio_totals import compute_portfolio_totals
except ImportError:
    from broker_reconcile import compare_holdings, parse_broker_upload
    from csv_utils import create_safety_backup, read_upload_bytes_limited
    from database import db_session, local_today_iso
    from holding_calculator import infer_category, recalc_holdings, validate_holding_history
    from portfolio_totals import compute_portfolio_totals

router = APIRouter()


class BrokerSuggestion(BaseModel):
    date: dt_date
    code: str
    name: Optional[str] = None
    category: Optional[str] = None
    actual_quantity: float
    actual_avg_cost: float
    actual_total_dividend: float = 0.0
    remark: Optional[str] = "券商对账单导入校正"


class BrokerApplyBody(BaseModel):
    items: List[BrokerSuggestion] = Field(default_factory=list)
    # optional: re-diff using last uploaded broker rows
    broker_rows: Optional[List[Dict[str, Any]]] = None
    broker_cash: Optional[float] = None
    as_of_date: Optional[str] = None


def _build_preview(
    broker_rows: List[Dict[str, Any]],
    as_of: str,
    broker_cash: Optional[float] = None,
) -> Dict[str, Any]:
    with db_session(row_factory=sqlite3.Row) as conn:
        app_rows = [dict(r) for r in conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()]
        totals = compute_portfolio_totals(conn)
        app_cash = float(totals.get("securities_cash") or 0)
    return compare_holdings(
        broker_rows,
        app_rows,
        as_of_date=as_of,
        broker_cash=broker_cash,
        app_cash=app_cash if broker_cash is not None else None,
    )


@router.post("/broker-reconcile/preview")
async def broker_reconcile_preview(
    file: UploadFile = File(...),
    as_of_date: Optional[str] = Form(None),
    broker_cash: Optional[str] = Form(None),
):
    raw = await read_upload_bytes_limited(file, max_bytes=50 * 1024 * 1024)
    if not raw:
        raise HTTPException(status_code=400, detail="上传文件为空")
    broker_rows, parse_meta = parse_broker_upload(raw, filename=file.filename or "")
    if parse_meta.get("error") and not broker_rows:
        raise HTTPException(status_code=400, detail=parse_meta.get("error"))
    as_of = (as_of_date or "").strip() or local_today_iso()
    cash_val = None
    if broker_cash is not None and str(broker_cash).strip() != "":
        try:
            cash_val = float(str(broker_cash).replace(",", "").strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="券商证券现金请填数字")
    result = _build_preview(broker_rows, as_of, broker_cash=cash_val)
    result["parse"] = parse_meta
    result["filename"] = file.filename
    result["broker_cash_input"] = cash_val
    return result


@router.post("/broker-reconcile/apply")
def broker_reconcile_apply(body: BrokerApplyBody):
    items = body.items or []
    if not items:
        raise HTTPException(status_code=400, detail="没有要应用的校正项")
    if len(items) > 200:
        raise HTTPException(status_code=400, detail="单次最多 200 条")

    backup_path = create_safety_backup("before_broker_reconcile")
    applied = []
    with db_session(row_factory=sqlite3.Row) as conn:
        codes = []
        for item in items:
            code = str(item.code or "").strip()
            if not code:
                continue
            quantity = float(item.actual_quantity)
            avg_cost = float(item.actual_avg_cost)
            total_dividend = float(item.actual_total_dividend or 0)
            if not all(math.isfinite(value) for value in (quantity, avg_cost, total_dividend)):
                raise HTTPException(status_code=400, detail=f"{code} 数量/成本/分红必须是有限数字")
            if quantity < 0 or avg_cost < 0:
                raise HTTPException(status_code=400, detail=f"{code} 数量/成本不能为负")
            if total_dividend < 0:
                raise HTTPException(status_code=400, detail=f"{code} 累计分红不能为负")
            name = (item.name or "").strip() or code
            category = (item.category or "").strip() or infer_category(code, name)
            conn.execute(
                """
                INSERT INTO holding_corrections
                (date, code, name, category, actual_quantity, actual_avg_cost, actual_total_dividend, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.date.isoformat(),
                    code,
                    name,
                    category,
                    quantity,
                    avg_cost,
                    total_dividend,
                    item.remark or "券商对账单导入校正",
                ),
            )
            codes.append(code)
            applied.append(code)
        if codes:
            unique_codes = list(dict.fromkeys(codes))
            try:
                for code in unique_codes:
                    validate_holding_history(conn, code)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            recalc_holdings(conn, codes=unique_codes)
        conn.commit()

    recheck = None
    if body.broker_rows:
        as_of = (body.as_of_date or "").strip() or local_today_iso()
        recheck = _build_preview(body.broker_rows, as_of, broker_cash=body.broker_cash)

    return {
        "status": "success",
        "applied_count": len(applied),
        "codes": applied,
        "backup": backup_path,
        "recheck": recheck,
    }
