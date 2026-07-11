import sqlite3
from datetime import date as dt_date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from .cash import DEFAULT_ACCOUNT, calculated_securities_cash, normalize_cash_flow_amount, set_setting
    from .database import db_session
except ImportError:
    from cash import DEFAULT_ACCOUNT, calculated_securities_cash, normalize_cash_flow_amount, set_setting
    from database import db_session

router = APIRouter()


class CashFlowBase(BaseModel):
    date: dt_date
    account: Optional[str] = None
    flow_type: str
    amount: float
    remark: Optional[str] = None


class CashFlowUpdate(BaseModel):
    date: Optional[dt_date] = None
    account: Optional[str] = None
    flow_type: Optional[str] = None
    amount: Optional[float] = None
    remark: Optional[str] = None


@router.get("/cash-flows")
def list_cash_flows(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    account: Optional[str] = None,
    flow_type: Optional[str] = None,
):
    with db_session(row_factory=sqlite3.Row) as conn:
        query = "SELECT * FROM cash_flows WHERE 1=1"
        params = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if account:
            query += " AND account = ?"
            params.append(account)
        if flow_type:
            query += " AND flow_type = ?"
            params.append(flow_type)
        query += " ORDER BY date DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


@router.post("/cash-flows")
def add_cash_flow(flow_data: CashFlowBase):
    with db_session(row_factory=sqlite3.Row) as conn:
        before, _, _ = calculated_securities_cash(conn)
        amount = normalize_cash_flow_amount(flow_data.flow_type, flow_data.amount)
        after = before + amount
        conn.execute(
            """
            INSERT INTO cash_flows (date, account, flow_type, amount, balance_before, balance_after, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                flow_data.date.isoformat(),
                flow_data.account or DEFAULT_ACCOUNT,
                flow_data.flow_type,
                amount,
                before,
                after,
                flow_data.remark,
            ),
        )
        set_setting(conn, "securities_cash", after)
        conn.commit()
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return {
        "status": "success",
        "id": new_id,
        "amount": amount,
        "balance_before": before,
        "balance_after": after,
    }


@router.put("/cash-flows/{flow_id}")
def update_cash_flow(flow_id: int, flow_data: CashFlowUpdate):
    with db_session(row_factory=sqlite3.Row) as conn:
        old = conn.execute("SELECT * FROM cash_flows WHERE id = ?", (flow_id,)).fetchone()
        if not old:
            raise HTTPException(status_code=404, detail="Cash flow not found")

        new_type = flow_data.flow_type if flow_data.flow_type is not None else old["flow_type"]
        # Always re-normalize amount when type or amount changes (fixes type-only switch sign bugs).
        raw_amount = flow_data.amount if flow_data.amount is not None else old["amount"]
        new_amount = normalize_cash_flow_amount(new_type, raw_amount)

        updates = ["flow_type = ?", "amount = ?"]
        vals = [new_type, new_amount]
        if flow_data.date is not None:
            updates.append("date = ?")
            vals.append(flow_data.date.isoformat())
        if flow_data.account is not None:
            updates.append("account = ?")
            vals.append(flow_data.account or DEFAULT_ACCOUNT)
        if flow_data.remark is not None:
            updates.append("remark = ?")
            vals.append(flow_data.remark)

        vals.append(flow_id)
        conn.execute(f"UPDATE cash_flows SET {', '.join(updates)} WHERE id = ?", vals)
        amount, _, _ = calculated_securities_cash(conn)
        set_setting(conn, "securities_cash", amount)
        conn.commit()
    return {"status": "success", "amount": amount, "normalized_amount": new_amount, "flow_type": new_type}


@router.delete("/cash-flows/{flow_id}")
def delete_cash_flow(flow_id: int):
    with db_session(row_factory=sqlite3.Row) as conn:
        conn.execute("DELETE FROM cash_flows WHERE id = ?", (flow_id,))
        if conn.total_changes == 0:
            raise HTTPException(status_code=404, detail="Cash flow not found")
        amount, _, _ = calculated_securities_cash(conn)
        set_setting(conn, "securities_cash", amount)
        conn.commit()
    return {"status": "success", "amount": amount}
