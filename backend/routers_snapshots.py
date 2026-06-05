import sqlite3
from datetime import date as dt_date, datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

try:
    from .database import LOCAL_TZ, open_db
    from .dashboard import build_dashboard
    from .snapshots import create_snapshot_record, list_snapshots_rows, snapshots_summary_data
except ImportError:
    from database import LOCAL_TZ, open_db
    from dashboard import build_dashboard
    from snapshots import create_snapshot_record, list_snapshots_rows, snapshots_summary_data

router = APIRouter()


class SnapshotSchema(BaseModel):
    date: dt_date
    total_assets: float
    total_market_value: float
    bank_balance: float
    securities_cash: float
    pending_purchase: float = 0.0
    total_profit: float
    holdings_count: int


def local_today_iso():
    return datetime.now(LOCAL_TZ).date().isoformat()


@router.post("/snapshots")
def create_snapshot():
    conn = open_db(row_factory=sqlite3.Row)
    dash = build_dashboard(conn)
    today = local_today_iso()
    snapshot_id, action = create_snapshot_record(conn, today, dash)
    conn.commit()
    conn.close()
    return {"status": "success", "action": action, "id": snapshot_id, "date": today, "snapshot": dash}


@router.get("/snapshots")
def list_snapshots(start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = open_db(row_factory=sqlite3.Row)
    rows = list_snapshots_rows(conn, start_date, end_date)
    conn.close()
    return rows


@router.get("/snapshots/summary")
def snapshots_summary(start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = open_db(row_factory=sqlite3.Row)
    changes = snapshots_summary_data(conn, start_date, end_date)
    conn.close()
    return changes
