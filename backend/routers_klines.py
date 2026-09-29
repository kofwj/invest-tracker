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
        index_lookup_for,
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
        index_lookup_for,
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
    # f 前缀 = 场外开放式基金（如 f002864 安泽短债），没有股票式 K 线。
    # 若当股票查，_tencent_symbol 会把 f 剥掉变成另一个 A 股代码（串台）。
    if code.lower().startswith("f"):
        return {"code": code, "days": days, "count": 0, "rows": [], "is_fund": True}
    days = max(1, min(int(days), 500))
    index_hit = None
    with db_session() as conn:
        ensure_kline_cache_table(conn)
        # 这个代码是不是已知指数（判定见 market.index_lookup）：前端靠它标注"按指数取数"，
        # 取数口径也由它决定 —— 手输 000001 时按上证指数走，而不是同号的平安银行。
        index_hit = index_lookup_for(conn, code)
        conn.commit()
    rows = get_cached_klines(code, days=days)
    if not rows:
        # 尝试拉一次
        with db_session() as conn:
            ensure_kline_cache_table(conn)
            n = sync_kline_for_code(conn, code, force=True)
            conn.commit()
        if n > 0:
            rows = get_cached_klines(code, days=days)
    payload = {"code": code, "days": days, "count": len(rows), "rows": rows}
    if index_hit:
        payload["symbol"] = index_hit.get("symbol") or ""
        payload["index_name"] = index_hit.get("name") or ""
    return payload


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
