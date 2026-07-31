"""日K缓存路由：前端 K线图读取 + 手动触发同步。"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from .database import db_session, local_today_iso
    from .kline_cache import (
        ensure_kline_cache_table,
        get_cached_klines,
        get_cached_klines_range,
        sync_kline_for_code,
        sync_klines_for_holdings,
    )
    from .csv_utils import create_safety_backup
except ImportError:
    from database import db_session, local_today_iso
    from kline_cache import (
        ensure_kline_cache_table,
        get_cached_klines,
        get_cached_klines_range,
        sync_kline_for_code,
        sync_klines_for_holdings,
    )
    from csv_utils import create_safety_backup

router = APIRouter()


class KlineSyncBody(BaseModel):
    code: Optional[str] = None
    force: bool = False


@router.get("/klines/{code}")
def get_klines(code: str, days: int = 120):
    """读取本地缓存的日K数据。"""
    code = str(code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="代码不能为空")
    days = max(1, min(int(days), 500))
    rows = get_cached_klines(code, days=days)
    if not rows:
        # 尝试拉一次
        with db_session() as conn:
            ensure_kline_cache_table(conn)
            n = sync_kline_for_code(conn, code, force=True)
            conn.commit()
        if n > 0:
            rows = get_cached_klines(code, days=days)
    return {"code": code, "days": days, "count": len(rows), "rows": rows}


@router.post("/klines/sync")
def sync_klines(body: KlineSyncBody):
    """手动触发日K同步。code 为空则同步所有持仓。"""
    backup_path = create_safety_backup("before_kline_sync") if body.force else None
    with db_session(row_factory=sqlite3.Row) as conn:
        ensure_kline_cache_table(conn)
        if body.code:
            code = str(body.code).strip()
            n = sync_kline_for_code(conn, code, force=body.force)
            conn.commit()
            return {"status": "success", "code": code, "upserted": n, "backup": backup_path}
        result = sync_klines_for_holdings(conn, force=body.force)
        conn.commit()
    result["backup"] = backup_path
    return {"status": "success", **result}


@router.get("/klines/{code}/range")
def get_klines_range(code: str, start_date: str, end_date: Optional[str] = None):
    """读取指定日期范围的日K。"""
    code = str(code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="代码不能为空")
    end = end_date or local_today_iso()
    rows = get_cached_klines_range(code, start_date, end)
    return {"code": code, "start_date": start_date, "end_date": end, "count": len(rows), "rows": rows}
