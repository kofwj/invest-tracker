import sqlite3
from datetime import date as dt_date
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

try:
    from .database import open_db
    from .csv_utils import (
        TRANSACTION_CSV_COLUMNS,
        TRANSACTION_HEADER_ALIASES,
        create_import_backup,
        csv_response,
        normalize_csv_row,
        normalize_date_string,
        parse_float,
        read_upload_csv,
    )
    from .holdings import infer_category, recalc_holdings
except ImportError:
    from database import open_db
    from csv_utils import (
        TRANSACTION_CSV_COLUMNS,
        TRANSACTION_HEADER_ALIASES,
        create_import_backup,
        csv_response,
        normalize_csv_row,
        normalize_date_string,
        parse_float,
        read_upload_csv,
    )
    from holdings import infer_category, recalc_holdings

router = APIRouter()


class TransactionBase(BaseModel):
    date: dt_date
    code: str
    name: str
    category: Optional[str] = None
    account: Optional[str] = None
    direction: str
    quantity: float
    price: float
    amount: float
    fee: float = 0.0
    remark: Optional[str] = None


class TransactionUpdate(BaseModel):
    date: Optional[dt_date] = None
    code: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    account: Optional[str] = None
    direction: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    fee: Optional[float] = None
    remark: Optional[str] = None


def ensure_transaction_columns(conn):
    cols = [row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if "category" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN category TEXT")
    if "account" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN account TEXT")


@router.get("/transactions/template")
def download_transactions_template():
    rows = [
        [dt_date.today().isoformat(), "华泰证券", "601288", "农业银行", "A股权益", "买入", "1000", "6.00", "6000.00", "5.00", "示例：请删除后填写真实交易"],
        [dt_date.today().isoformat(), "华泰证券", "f004388", "鹏华丰享", "债基", "申购待确认", "0", "0", "50000.00", "0.00", "场外基金份额未确认时使用"],
        [dt_date.today().isoformat(), "华泰证券", "f004388", "鹏华丰享", "债基", "分红再投资", "95.2381", "1.0500", "100.00", "0.00", "示例：100元分红按1.05净值再投"],
    ]
    return csv_response("transactions_template.csv", TRANSACTION_CSV_COLUMNS, rows)


@router.get("/transactions/export")
def export_transactions():
    conn = open_db(row_factory=sqlite3.Row)
    rows = conn.execute("""
        SELECT date, COALESCE(account, '华泰证券') AS account, code, name, category, direction, quantity, price, amount, fee, remark
        FROM transactions
        ORDER BY date DESC, id DESC
    """).fetchall()
    conn.close()
    data = [[r[k] for k in TRANSACTION_CSV_COLUMNS] for r in rows]
    return csv_response(f"transactions_{dt_date.today().isoformat()}.csv", TRANSACTION_CSV_COLUMNS, data)


@router.post("/transactions/import")
async def import_transactions(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="目前仅支持 CSV 文件")
    raw_rows = read_upload_csv(await file.read())
    if not raw_rows:
        raise HTTPException(status_code=400, detail="CSV为空")
    backup_path = create_import_backup("before_import_transactions")
    conn = open_db(row_factory=sqlite3.Row)
    ensure_transaction_columns(conn)
    success = 0
    errors = []
    allowed_directions = {"买入", "卖出", "分红", "分红再投资", "申购待确认", "待确认申购"}
    try:
        for idx, raw in enumerate(raw_rows, start=2):
            try:
                row = normalize_csv_row(raw, TRANSACTION_HEADER_ALIASES)
                date_str = normalize_date_string(row.get("date"))
                code = str(row.get("code") or "").strip()
                name = str(row.get("name") or "").strip()
                direction = str(row.get("direction") or "").strip()
                if not code:
                    raise ValueError("代码不能为空")
                if not name:
                    raise ValueError("名称不能为空")
                if direction not in allowed_directions:
                    raise ValueError("方向必须是：买入/卖出/分红/分红再投资/申购待确认")
                category = row.get("category") or infer_category(code, name)
                account = row.get("account") or "华泰证券"
                quantity = parse_float(row.get("quantity"), 0.0)
                price = parse_float(row.get("price"), 0.0)
                amount = parse_float(row.get("amount"), 0.0)
                fee = parse_float(row.get("fee"), 0.0)
                remark = row.get("remark") or ""
                if amount < 0:
                    raise ValueError("金额不能为负；买卖方向通过direction表示")
                conn.execute("""
                    INSERT INTO transactions (date, code, name, category, account, direction, quantity, price, amount, fee, remark)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (date_str, code, name, category, account, direction, quantity, price, amount, fee, remark))
                success += 1
            except Exception as e:
                errors.append({"row": idx, "error": str(e)})
        if success:
            recalc_holdings(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"status": "success", "imported": success, "failed": len(errors), "errors": errors[:50], "backup": backup_path}


@router.get("/transactions")
def list_transactions(code: Optional[str] = None):
    conn = open_db(row_factory=sqlite3.Row)
    if code:
        rows = conn.execute("SELECT * FROM transactions WHERE code = ? ORDER BY date DESC, id DESC", (code,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.post("/transactions")
def add_transaction(trans: TransactionBase):
    conn = open_db()
    ensure_transaction_columns(conn)
    conn.execute("""
        INSERT INTO transactions (date, code, name, category, account, direction, quantity, price, amount, fee, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (trans.date.isoformat(), trans.code, trans.name, trans.category, trans.account or "华泰证券", trans.direction, trans.quantity, trans.price, trans.amount, trans.fee, trans.remark))
    recalc_holdings(conn)
    conn.commit()
    conn.close()
    return {"status": "success"}


@router.put("/transactions/{transaction_id}")
def update_transaction(transaction_id: int, trans: TransactionUpdate):
    conn = open_db()
    ensure_transaction_columns(conn)
    updates = []
    vals = []
    for field in ["date", "code", "name", "category", "account", "direction", "quantity", "price", "amount", "fee", "remark"]:
        v = getattr(trans, field)
        if v is not None:
            updates.append(f"{field} = ?")
            vals.append(v.isoformat() if field == "date" else v)
    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")
    vals.append(transaction_id)
    conn.execute(f"UPDATE transactions SET {', '.join(updates)} WHERE id = ?", vals)
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")
    recalc_holdings(conn)
    conn.commit()
    conn.close()
    return {"status": "success"}


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: int):
    conn = open_db()
    conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")
    recalc_holdings(conn)
    conn.commit()
    conn.close()
    return {"status": "success"}
