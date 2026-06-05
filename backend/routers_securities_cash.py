import sqlite3
from datetime import date as dt_date

from fastapi import APIRouter
from pydantic import BaseModel

try:
    from .cash import DEFAULT_ACCOUNT, cash_flow_adjustment, calculated_securities_cash, set_setting
    from .database import open_db
except ImportError:
    from cash import DEFAULT_ACCOUNT, cash_flow_adjustment, calculated_securities_cash, set_setting
    from database import open_db

router = APIRouter()


class SecuritiesCashUpdate(BaseModel):
    amount: float


@router.get("/securities-cash")
def get_securities_cash():
    conn = open_db(row_factory=sqlite3.Row)
    amount, base, flow = calculated_securities_cash(conn)
    manual_flow = cash_flow_adjustment(conn)
    conn.commit()
    conn.close()
    return {"amount": amount, "base_amount": base, "cash_flow_adjustment": manual_flow, "transaction_cash_flow": flow}


@router.put("/securities-cash")
def update_securities_cash(data: SecuritiesCashUpdate):
    conn = open_db(row_factory=sqlite3.Row)
    current, base, tx_flow = calculated_securities_cash(conn)
    delta = float(data.amount or 0) - current
    if abs(delta) >= 0.005:
        conn.execute("""
            INSERT INTO cash_flows (date, account, flow_type, amount, balance_before, balance_after, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (dt_date.today().isoformat(), DEFAULT_ACCOUNT, '现金校准', delta, current, float(data.amount or 0), '现金设置页手动校准'))
    set_setting(conn, 'securities_cash', data.amount)
    manual_flow = cash_flow_adjustment(conn)
    conn.commit()
    conn.close()
    return {"status": "success", "amount": data.amount, "base_amount": base, "cash_flow_adjustment": manual_flow, "transaction_cash_flow": tx_flow, "delta": delta}
