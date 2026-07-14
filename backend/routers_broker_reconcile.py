"""券商对账单：上传 CSV → 差异清单 → 可选批量写入持仓校正。"""

from __future__ import annotations

import sqlite3
from datetime import date as dt_date
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

try:
    from .broker_reconcile import (
        compare_holdings,
        decode_upload_bytes,
        parse_broker_csv_text,
    )
    from .csv_utils import create_safety_backup
    from .database import db_session, local_today_iso
    from .holding_calculator import infer_category, recalc_holdings
except ImportError:
    from broker_reconcile import (
        compare_holdings,
        decode_upload_bytes,
        parse_broker_csv_text,
    )
    from csv_utils import create_safety_backup
    from database import db_session, local_today_iso
    from holding_calculator import infer_category, recalc_holdings

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


@router.post("/broker-reconcile/preview")
async def broker_reconcile_preview(
    file: UploadFile = File(...),
    as_of_date: Optional[str] = Form(None),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传文件为空")
    text = decode_upload_bytes(raw)
    broker_rows, parse_meta = parse_broker_csv_text(text)
    if parse_meta.get("error") and not broker_rows:
        raise HTTPException(status_code=400, detail=parse_meta.get("error"))
    as_of = (as_of_date or "").strip() or local_today_iso()
    with db_session(row_factory=sqlite3.Row) as conn:
        app_rows = [dict(r) for r in conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()]
    result = compare_holdings(broker_rows, app_rows, as_of_date=as_of)
    result["parse"] = parse_meta
    result["filename"] = file.filename
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
            if float(item.actual_quantity) < 0 or float(item.actual_avg_cost) < 0:
                raise HTTPException(status_code=400, detail=f"{code} 数量/成本不能为负")
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
                    float(item.actual_quantity),
                    float(item.actual_avg_cost),
                    float(item.actual_total_dividend or 0),
                    item.remark or "券商对账单导入校正",
                ),
            )
            codes.append(code)
            applied.append(code)
        if codes:
            recalc_holdings(conn, codes=list(dict.fromkeys(codes)))
        conn.commit()
    return {
        "status": "success",
        "applied_count": len(applied),
        "codes": applied,
        "backup": backup_path,
    }
