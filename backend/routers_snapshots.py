import sqlite3
from datetime import date as dt_date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from . import database as database_module
    from .database import LOCAL_TZ, db_session
    from .csv_utils import create_safety_backup, csv_response
    from .total_asset_calibration import apply_calibration, calibration_status
    from .dashboard import build_dashboard
    from .snapshots import (
        create_snapshot_record,
        latest_reconcile_with_gap,
        list_snapshots_rows,
        resolve_snapshot_price_state,
        save_reconcile,
        snapshots_summary_data,
        stale_price_detail,
    )
except ImportError:
    import database as database_module
    from database import LOCAL_TZ, db_session
    from csv_utils import create_safety_backup, csv_response
    from dashboard import build_dashboard
    from snapshots import (
        create_snapshot_record,
        latest_reconcile_with_gap,
        list_snapshots_rows,
        resolve_snapshot_price_state,
        save_reconcile,
        snapshots_summary_data,
        stale_price_detail,
    )
    from total_asset_calibration import apply_calibration, calibration_status

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


class ReconcileSchema(BaseModel):
    date: dt_date
    manual_total_assets: float
    note: Optional[str] = None


class CalibrationSchema(BaseModel):
    manual_total_assets: float
    note: Optional[str] = None


@router.post("/snapshots")
def create_snapshot(force: bool = False):
    with db_session(row_factory=sqlite3.Row) as conn:
        dash = build_dashboard(conn)
        today = database_module.local_today_iso()
        # 价格闸门：最新价不是今天的 → 记下来的当日收益会失真（沿用旧价），
        # 除非用户显式 force（此时照写，但落库 price_stale=1 + 旧价日期）。
        price_state = resolve_snapshot_price_state(conn, today)
        if price_state["needs_fresh_price"] and price_state["is_stale"] and not force:
            raise HTTPException(
                status_code=409, detail=stale_price_detail(price_state, today)
            )
        snapshot_id, action = create_snapshot_record(conn, today, dash)
        conn.commit()
    return {
        "status": "success",
        "action": action,
        "id": snapshot_id,
        "date": today,
        "lifetime_profit": dash.get("lifetime_profit"),
        "snapshot": dash,
        "price_stale": int(price_state["is_stale"]),
        "price_date": price_state["price_date"],
    }


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


@router.post("/snapshots/reconcile")
def save_snapshot_reconcile(payload: ReconcileSchema):
    with db_session(row_factory=sqlite3.Row) as conn:
        result = save_reconcile(
            conn,
            payload.date.isoformat(),
            payload.manual_total_assets,
            payload.note or "",
        )
        conn.commit()
    return result


@router.get("/snapshots/reconcile")
def get_snapshot_reconcile():
    with db_session(row_factory=sqlite3.Row) as conn:
        return latest_reconcile_with_gap(conn)


@router.post("/snapshots/reconcile/apply")
def apply_total_asset_calibration(payload: CalibrationSchema):
    """把「实测总资产」吸收成一条可见的记账平差。

    持仓差异归券商 CSV 导入、证券现金差异归现金校准，这里只吃「合起来对不上」的那部分。
    """
    with db_session(row_factory=sqlite3.Row) as conn:
        displayed = float(build_dashboard(conn).get("total_assets") or 0.0)
        try:
            result = apply_calibration(
                conn,
                payload.manual_total_assets,
                displayed_total_assets=displayed,
                note=payload.note or "",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        conn.commit()
        # 校准后回读：让前端直接拿到对齐后的总资产，不必自己再算一遍
        result["total_assets"] = build_dashboard(conn).get("total_assets")
    return result


@router.get("/snapshots/reconcile/total-assets")
def get_total_asset_calibration():
    with db_session(row_factory=sqlite3.Row) as conn:
        return calibration_status(conn)


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
