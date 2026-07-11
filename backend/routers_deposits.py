from datetime import date as dt_date
import sqlite3
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

try:
    from .database import db_session
    from .csv_utils import (
        DEPOSIT_CSV_COLUMNS,
        DEPOSIT_HEADER_ALIASES,
        create_import_backup,
        create_safety_backup,
        csv_response,
        normalize_csv_row,
        normalize_date_string,
        parse_float,
        read_upload_csv,
    )
except ImportError:
    from database import db_session
    from csv_utils import (
        DEPOSIT_CSV_COLUMNS,
        DEPOSIT_HEADER_ALIASES,
        create_import_backup,
        create_safety_backup,
        csv_response,
        normalize_csv_row,
        normalize_date_string,
        parse_float,
        read_upload_csv,
    )

router = APIRouter()


class DepositSchema(BaseModel):
    id: Optional[int] = None
    bank_name: str
    amount: float
    interest_rate: Optional[float] = None
    due_date: Optional[str] = None
    remark: Optional[str] = None


class DepositUpdate(BaseModel):
    bank_name: Optional[str] = None
    amount: Optional[float] = None
    interest_rate: Optional[float] = None
    due_date: Optional[str] = None
    remark: Optional[str] = None


@router.get("/deposits", response_model=list[DepositSchema])
def list_deposits():
    with db_session(row_factory=sqlite3.Row) as conn:
        rows = conn.execute("SELECT * FROM deposits").fetchall()
    return [dict(row) for row in rows]


@router.get("/deposits/template")
def download_deposits_template():
    rows = [["招商银行", "100000.00", "1.80", "2026-12-31", "示例：请删除后填写真实存款"]]
    return csv_response("deposits_template.csv", DEPOSIT_CSV_COLUMNS, rows)


@router.get("/deposits/export")
def export_deposits():
    with db_session(row_factory=sqlite3.Row) as conn:
        rows = conn.execute(
            """
            SELECT bank_name, amount, interest_rate, due_date, remark
            FROM deposits
            ORDER BY COALESCE(due_date, '9999-12-31'), id
            """
        ).fetchall()
    data = [[r[k] for k in DEPOSIT_CSV_COLUMNS] for r in rows]
    return csv_response(f"deposits_{dt_date.today().isoformat()}.csv", DEPOSIT_CSV_COLUMNS, data)


@router.post("/deposits/import")
async def import_deposits(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="目前仅支持 CSV 文件")
    raw_rows = read_upload_csv(await file.read())
    if not raw_rows:
        raise HTTPException(status_code=400, detail="CSV为空")
    backup_path = create_import_backup("before_import_deposits")
    success = 0
    errors = []
    with db_session() as conn:
        try:
            for idx, raw in enumerate(raw_rows, start=2):
                try:
                    row = normalize_csv_row(raw, DEPOSIT_HEADER_ALIASES)
                    bank_name = str(row.get("bank_name") or "").strip()
                    if not bank_name:
                        raise ValueError("银行名称不能为空")
                    amount = parse_float(row.get("amount"), 0.0)
                    if amount <= 0:
                        raise ValueError("金额必须大于0")
                    interest_rate = (
                        parse_float(row.get("interest_rate"), 0.0)
                        if row.get("interest_rate") != ""
                        else None
                    )
                    due_date = normalize_date_string(row.get("due_date"), required=False) or None
                    remark = row.get("remark") or ""
                    conn.execute(
                        """
                        INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (bank_name, amount, interest_rate, due_date, remark),
                    )
                    success += 1
                except Exception as e:
                    errors.append({"row": idx, "error": str(e)})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {
        "status": "success",
        "imported": success,
        "failed": len(errors),
        "errors": errors[:50],
        "backup": backup_path,
    }


@router.post("/deposits")
def add_deposit(dep: DepositSchema):
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark)
            VALUES (?, ?, ?, ?, ?)
            """,
            (dep.bank_name, dep.amount, dep.interest_rate, dep.due_date, dep.remark),
        )
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
    return {"status": "success", "id": new_id}


@router.put("/deposits/{deposit_id}")
def update_deposit(deposit_id: int, dep: DepositUpdate):
    backup_path = create_safety_backup("before_update_deposit")
    updates = []
    vals = []
    for field in ["bank_name", "amount", "interest_rate", "due_date", "remark"]:
        v = getattr(dep, field)
        if v is not None:
            updates.append(f"{field} = ?")
            vals.append(v)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    vals.append(deposit_id)
    with db_session() as conn:
        conn.execute(f"UPDATE deposits SET {', '.join(updates)} WHERE id = ?", vals)
        if conn.total_changes == 0:
            raise HTTPException(status_code=404, detail="Deposit not found")
        conn.commit()
    return {"status": "success", "backup": backup_path}


@router.delete("/deposits/{deposit_id}")
def delete_deposit(deposit_id: int):
    backup_path = create_safety_backup("before_delete_deposit")
    with db_session() as conn:
        conn.execute("DELETE FROM deposits WHERE id = ?", (deposit_id,))
        if conn.total_changes == 0:
            raise HTTPException(status_code=404, detail="Deposit not found")
        conn.commit()
    return {"status": "success", "backup": backup_path}
