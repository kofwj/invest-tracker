import sqlite3
from datetime import date as dt_date, datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

try:
    from . import database as database_module
    from .database import LOCAL_TZ, db_session
    from .csv_utils import create_safety_backup, csv_response
    from .dashboard import build_dashboard
    from .snapshots import create_snapshot_record, list_snapshots_rows, snapshots_summary_data
except ImportError:
    import database as database_module
    from database import LOCAL_TZ, db_session
    from csv_utils import create_safety_backup, csv_response
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


@router.post("/snapshots")
def create_snapshot():
    with db_session(row_factory=sqlite3.Row) as conn:
        dash = build_dashboard(conn)
        today = database_module.local_today_iso()
        snapshot_id, action = create_snapshot_record(conn, today, dash)
        conn.commit()
    return {"status": "success", "action": action, "id": snapshot_id, "date": today, "snapshot": dash}


@router.get("/snapshots")
def list_snapshots(start_date: Optional[str] = None, end_date: Optional[str] = None):
    with db_session(row_factory=sqlite3.Row) as conn:
        rows = list_snapshots_rows(conn, start_date, end_date)
    return rows


@router.get("/snapshots/summary")
def snapshots_summary(start_date: Optional[str] = None, end_date: Optional[str] = None):
    with db_session(row_factory=sqlite3.Row) as conn:
        changes = snapshots_summary_data(conn, start_date, end_date)
    return changes


SNAPSHOT_CSV_COLUMNS = [
    "date",
    "total_assets",
    "total_market_value",
    "bank_balance",
    "securities_cash",
    "pending_purchase",
    "total_profit",
    "holdings_count",
]


@router.get("/snapshots/export")
def export_snapshots(start_date: Optional[str] = None, end_date: Optional[str] = None):
    with db_session(row_factory=sqlite3.Row) as conn:
        rows = list_snapshots_rows(conn, start_date, end_date)
    rows_asc = sorted(rows, key=lambda r: str(r.get("date") or ""))
    data = [[r.get(k, "") for k in SNAPSHOT_CSV_COLUMNS] for r in rows_asc]
    suffix = database_module.local_today_iso()
    return csv_response(f"snapshots_{suffix}.csv", SNAPSHOT_CSV_COLUMNS, data)


@router.post("/snapshots/compact")
def compact_snapshots(keep_recent_days: int = 365, weekly_before_days: int = 1095):
    if keep_recent_days < 30:
        keep_recent_days = 30
    if weekly_before_days < keep_recent_days:
        weekly_before_days = keep_recent_days
    backup_path = create_safety_backup("before_compact_snapshots")
    with db_session(row_factory=sqlite3.Row) as conn:
        rows = conn.execute("SELECT id, date FROM daily_snapshots ORDER BY date ASC, id ASC").fetchall()
        today = datetime.now(LOCAL_TZ).date()
        keep_ids = set()
        weekly = {}
        monthly = {}
        for row in rows:
            try:
                d = dt_date.fromisoformat(str(row["date"]))
            except Exception:
                keep_ids.add(row["id"])
                continue
            age = (today - d).days
            if age <= keep_recent_days:
                keep_ids.add(row["id"])
            elif age <= weekly_before_days:
                weekly[d.isocalendar()[:2]] = row["id"]
            else:
                monthly[(d.year, d.month)] = row["id"]
        keep_ids.update(weekly.values())
        keep_ids.update(monthly.values())
        before = len(rows)
        deleted = 0
        if rows:
            delete_ids = [row["id"] for row in rows if row["id"] not in keep_ids]
            if delete_ids:
                conn.executemany("DELETE FROM daily_snapshots WHERE id = ?", [(i,) for i in delete_ids])
                deleted = len(delete_ids)
        conn.commit()
        after = before - deleted
    return {
        "status": "success",
        "before": before,
        "after": after,
        "deleted": deleted,
        "backup": backup_path,
        "keep_recent_days": keep_recent_days,
        "weekly_before_days": weekly_before_days,
    }
