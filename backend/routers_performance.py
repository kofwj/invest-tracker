import sqlite3
from datetime import date as dt_date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from .database import open_db
    from .performance import (
        build_performance_contribution,
        build_performance_summary,
        build_performance_timeline,
    )
    from .snapshots import ensure_portfolio_cash_flows_table
except ImportError:
    from database import open_db
    from performance import (
        build_performance_contribution,
        build_performance_summary,
        build_performance_timeline,
    )
    from snapshots import ensure_portfolio_cash_flows_table

router = APIRouter()


class PortfolioCashFlowBase(BaseModel):
    date: dt_date
    flow_type: str
    amount: float
    source: Optional[str] = None
    remark: Optional[str] = None


class PortfolioCashFlowUpdate(BaseModel):
    date: Optional[dt_date] = None
    flow_type: Optional[str] = None
    amount: Optional[float] = None
    source: Optional[str] = None
    remark: Optional[str] = None


@router.get("/portfolio-cash-flows")
def list_portfolio_cash_flows(start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = open_db(row_factory=sqlite3.Row)
    ensure_portfolio_cash_flows_table(conn)
    query = "SELECT * FROM portfolio_cash_flows"
    params = []
    if start_date and end_date:
        query += " WHERE date BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE date >= ?"
        params = [start_date]
    elif end_date:
        query += " WHERE date <= ?"
        params = [end_date]
    query += " ORDER BY date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/portfolio-cash-flows")
def add_portfolio_cash_flow(flow: PortfolioCashFlowBase):
    conn = open_db()
    ensure_portfolio_cash_flows_table(conn)
    conn.execute(
        "INSERT INTO portfolio_cash_flows (date, flow_type, amount, source, remark) VALUES (?,?,?,?,?)",
        (flow.date.isoformat(), flow.flow_type, flow.amount, flow.source, flow.remark),
    )
    conn.commit()
    conn.close()
    return {"status": "success"}


@router.put("/portfolio-cash-flows/{flow_id}")
def update_portfolio_cash_flow(flow_id: int, flow: PortfolioCashFlowUpdate):
    conn = open_db(row_factory=sqlite3.Row)
    ensure_portfolio_cash_flows_table(conn)
    existing = conn.execute("SELECT * FROM portfolio_cash_flows WHERE id=?", (flow_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Flow not found")
    d = flow.date.isoformat() if flow.date else existing["date"]
    t = flow.flow_type if flow.flow_type else existing["flow_type"]
    a = flow.amount if flow.amount is not None else existing["amount"]
    s = flow.source if flow.source is not None else existing["source"]
    r = flow.remark if flow.remark is not None else existing["remark"]
    conn.execute(
        "UPDATE portfolio_cash_flows SET date=?, flow_type=?, amount=?, source=?, remark=? WHERE id=?",
        (d, t, a, s, r, flow_id),
    )
    conn.commit()
    conn.close()
    return {"status": "success"}


@router.delete("/portfolio-cash-flows/{flow_id}")
def delete_portfolio_cash_flow(flow_id: int):
    conn = open_db()
    ensure_portfolio_cash_flows_table(conn)
    conn.execute("DELETE FROM portfolio_cash_flows WHERE id=?", (flow_id,))
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Flow not found")
    conn.commit()
    conn.close()
    return {"status": "success"}


@router.get("/performance/summary")
def performance_summary():
    conn = open_db(row_factory=sqlite3.Row)
    ensure_portfolio_cash_flows_table(conn)
    data = build_performance_summary(conn)
    conn.close()
    return data


@router.get("/performance/timeline")
def performance_timeline(start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = open_db(row_factory=sqlite3.Row)
    ensure_portfolio_cash_flows_table(conn)
    result = build_performance_timeline(conn, start_date, end_date)
    conn.close()
    return result


@router.get("/performance/contribution")
def performance_contribution():
    conn = open_db(row_factory=sqlite3.Row)
    rows = build_performance_contribution(conn)
    conn.close()
    return rows
