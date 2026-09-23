import logging
import sqlite3
from datetime import date as dt_date, datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from .cash import set_setting
    from .csv_utils import create_safety_backup
    from .database import LOCAL_TZ, db_session
    from .holding_calculator import infer_category, recalc_holdings, validate_holding_history
    from .return_sync import calculate_trailing_return_1y, ensure_holding_return_columns
    from .price_sync import fetch_eastmoney_prices, fetch_open_fund_nav
except ImportError:
    from cash import set_setting
    from csv_utils import create_safety_backup
    from database import LOCAL_TZ, db_session
    from holding_calculator import infer_category, recalc_holdings, validate_holding_history
    from return_sync import calculate_trailing_return_1y, ensure_holding_return_columns
    from price_sync import fetch_eastmoney_prices, fetch_open_fund_nav

logger = logging.getLogger(__name__)
router = APIRouter()


class HoldingSchema(BaseModel):
    code: str
    name: str
    category: Optional[str] = None
    quantity: float
    avg_cost: float
    diluted_cost: float
    total_dividend: float
    last_price: float
    updated_at: Optional[datetime] = None
    expected_return: Optional[float] = 0.0
    trailing_return_1y: Optional[float] = None
    trailing_return_1y_source: Optional[str] = None
    trailing_return_1y_updated_at: Optional[datetime] = None


class HoldingUpdate(BaseModel):
    expected_return: Optional[float] = None
    name: Optional[str] = None
    category: Optional[str] = None


class HoldingCorrectionBase(BaseModel):
    date: dt_date
    code: str
    name: Optional[str] = None
    category: Optional[str] = None
    actual_quantity: float
    actual_avg_cost: float
    actual_total_dividend: float = 0.0
    remark: Optional[str] = None


@router.get("/holdings", response_model=List[HoldingSchema])
def list_holdings():
    try:
        with db_session(row_factory=sqlite3.Row) as conn:
            rows = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Holdings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/holdings/{code}")
def update_holding(code: str, payload: HoldingUpdate):
    code = str(code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="代码不能为空")
    updates = []
    vals = []
    if payload.expected_return is not None:
        updates.append("expected_return = ?")
        vals.append(float(payload.expected_return))
    if payload.name is not None:
        updates.append("name = ?")
        vals.append(payload.name)
    if payload.category is not None:
        updates.append("category = ?")
        vals.append(payload.category)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates.append("updated_at = ?")
    vals.append(datetime.now(LOCAL_TZ).replace(tzinfo=None))
    vals.append(code)
    with db_session() as conn:
        conn.execute(f"UPDATE holdings SET {', '.join(updates)} WHERE code = ?", vals)
        if conn.total_changes == 0:
            raise HTTPException(status_code=404, detail="Holding not found")
        conn.commit()
    return {"status": "success", "code": code}


@router.get("/holding-corrections")
def list_holding_corrections(code: Optional[str] = None):
    with db_session(row_factory=sqlite3.Row) as conn:
        if code:
            rows = conn.execute(
                "SELECT * FROM holding_corrections WHERE code = ? ORDER BY date DESC, id DESC",
                (str(code).strip(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM holding_corrections ORDER BY date DESC, id DESC"
            ).fetchall()
    return [dict(r) for r in rows]


@router.post("/holding-corrections")
def add_holding_correction(payload: HoldingCorrectionBase):
    code = str(payload.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="代码不能为空")
    if float(payload.actual_quantity or 0) < 0:
        raise HTTPException(status_code=400, detail="校正数量不能为负")
    if float(payload.actual_avg_cost or 0) < 0:
        raise HTTPException(status_code=400, detail="校正成本不能为负")
    if float(payload.actual_total_dividend or 0) < 0:
        raise HTTPException(status_code=400, detail="累计分红不能为负")

    backup_path = create_safety_backup("before_holding_correction")
    name = (payload.name or "").strip() or code
    category = (payload.category or "").strip() or infer_category(code, name)
    with db_session(row_factory=sqlite3.Row) as conn:
        conn.execute(
            """
            INSERT INTO holding_corrections
            (date, code, name, category, actual_quantity, actual_avg_cost, actual_total_dividend, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.date.isoformat(),
                code,
                name,
                category,
                float(payload.actual_quantity),
                float(payload.actual_avg_cost),
                float(payload.actual_total_dividend or 0),
                payload.remark,
            ),
        )
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        try:
            validate_holding_history(conn, code)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        recalc_holdings(conn, codes=[code])
        conn.commit()
    return {"status": "success", "id": new_id, "backup": backup_path}


@router.delete("/holding-corrections/{correction_id}")
def delete_holding_correction(correction_id: int):
    backup_path = create_safety_backup("before_delete_holding_correction")
    with db_session(row_factory=sqlite3.Row) as conn:
        existing = conn.execute(
            "SELECT code FROM holding_corrections WHERE id = ?", (correction_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Correction not found")
        code = str(existing["code"] or "").strip()
        conn.execute("DELETE FROM holding_corrections WHERE id = ?", (correction_id,))
        try:
            if code:
                validate_holding_history(conn, code)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        recalc_holdings(conn, codes=[code] if code else None)
        conn.commit()
    return {"status": "success", "backup": backup_path}


def _sync_trailing_returns_impl(backup: bool = False):
    backup_path = create_safety_backup("before_sync_trailing_returns") if backup else None
    # 阶段 1（短事务）：补齐缓存列 + 取持仓快照。读完立刻 commit 结束事务，
    # 否则下面逐只抓腾讯/akshare 的整段网络 IO 都落在写锁内（旧实现在第一只
    # UPDATE 后就开写事务，10 只持仓能占锁 10-30s，并发写请求直接 database is locked）。
    with db_session(row_factory=sqlite3.Row) as conn:
        ensure_holding_return_columns(conn)
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT code, name, last_price FROM holdings WHERE quantity > 0"
            ).fetchall()
        ]
        conn.commit()
    # 阶段 2（纯网络，不持有任何 DB 事务/锁）：结果只进内存
    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    updated = 0
    failed = []
    details = []
    pending = []
    for row in rows:
        code = str(row["code"]).strip()
        pct, source = calculate_trailing_return_1y(code, row["last_price"])
        if pct is None:
            failed.append({"code": code, "name": row["name"], "reason": source})
        else:
            updated += 1
        # 与旧实现一致：失败的标的也写 NULL（清掉过期缓存值）
        pending.append((pct, source, now, code))
        details.append(
            {"code": code, "name": row["name"], "trailing_return_1y": pct, "source": source}
        )
    # 阶段 3（短写事务）：批量落库，纯 DB 操作
    if pending:
        with db_session() as conn:
            conn.executemany(
                """
                UPDATE holdings
                SET trailing_return_1y = ?, trailing_return_1y_source = ?, trailing_return_1y_updated_at = ?
                WHERE code = ?
                """,
                pending,
            )
            conn.commit()
    return {
        "status": "success",
        "checked": len(rows),
        "updated": updated,
        "failed": failed,
        "details": details,
        "backup": backup_path,
    }


def _sync_prices_impl(backup: bool = False):
    backup_path = create_safety_backup("before_sync_prices") if backup else None
    # 阶段 1（短事务）：取持仓快照，立即结束事务——网络阶段不再持锁。
    with db_session(row_factory=sqlite3.Row) as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT code, name, last_price FROM holdings WHERE quantity > 0"
            ).fetchall()
        ]
        conn.commit()
    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)

    codes = [row["code"] for row in rows]
    em_prices = {}
    try:
        em_prices = fetch_eastmoney_prices(codes)
    except Exception as e:
        logger.error(f"Eastmoney batch price sync failed: {e}")

    # 阶段 2（纯网络）：把新价/来源/计数全部算到内存，不碰 DB。
    # 注意场外基金逐只调 fetch_open_fund_nav，以前这段是在写事务里的。
    updated = 0
    unchanged = 0
    failed = []
    details = []
    pending = []
    for row in rows:
        code = str(row["code"]).strip()
        lookup_code = code.lower().replace("f", "")
        old_price = float(row["last_price"] or 0)
        price = None
        source = ""
        try:
            if code.lower().startswith("f"):
                price = fetch_open_fund_nav(code)
                source = "天天基金净值"
            else:
                price = em_prices.get(lookup_code)
                source = "东方财富行情"

            if price is None or price <= 0:
                # 取不到净值/行情 → 保留旧价（不写库），语义与旧实现一致
                failed.append({"code": code, "name": row["name"], "reason": "未取到有效价格"})
                continue

            pending.append((float(price), now, code))
            if abs(price - old_price) >= 1e-8:
                updated += 1
            else:
                unchanged += 1
            details.append(
                {
                    "code": code,
                    "name": row["name"],
                    "old_price": old_price,
                    "new_price": float(price),
                    "source": source,
                }
            )
        except Exception as e:
            logger.error(f"Error syncing {code}: {e}")
            failed.append({"code": code, "name": row["name"], "reason": str(e)})

    # 阶段 3（短写事务）：批量落库。价格没变的标的也刷新 updated_at（与旧实现一致）。
    # 只要至少抓到一只价格就记 last_price_sync_at（本地时间、与 holdings.updated_at
    # 同格式），供快照价格闸门判断"最新价是不是今天的"；全部失败不写，保持旧值。
    if pending:
        with db_session() as conn:
            conn.executemany(
                "UPDATE holdings SET last_price = ?, updated_at = ? WHERE code = ?",
                pending,
            )
            set_setting(conn, "last_price_sync_at", now.strftime("%Y-%m-%d %H:%M:%S"))
            conn.commit()

    # 顺手增量同步日K缓存（失败不影响同步价结果）。
    # 注意：这里必须用「相对 + 绝对」双导入。生产是 uvicorn main:app 平铺加载
    # （backend/ 没有 __init__.py），routers_holdings.__package__ 为空字符串，
    # 只写相对导入会抛 ImportError 并被下面的 except 吞掉 —— 也就是说这段
    # K线同步在线上从来没执行过。全仓其它 100 处都带 ImportError 兜底，只有这里漏了。
    try:
        try:
            from .kline_cache import sync_klines_for_holdings as _sync_klines
        except ImportError:
            from kline_cache import sync_klines_for_holdings as _sync_klines
        with db_session() as conn2:
            _sync_klines(conn2, force=False)
            conn2.commit()
    except Exception as kline_exc:
        logger.warning("kline incremental sync after price sync failed: %s", kline_exc, exc_info=True)
    return {
        "status": "success",
        "updated": updated,
        "unchanged": unchanged,
        "failed": failed,
        "details": details,
        "checked": len(rows),
        "backup": backup_path,
    }


@router.post("/sync-trailing-returns")
def sync_trailing_returns_post(backup: bool = False):
    return _sync_trailing_returns_impl(backup=backup)


@router.post("/sync-prices")
def sync_prices_post(backup: bool = False):
    return _sync_prices_impl(backup=backup)
