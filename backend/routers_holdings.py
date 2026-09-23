import logging
import math
import sqlite3
from datetime import date as dt_date, datetime
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from .cash import set_setting
    from .csv_utils import create_safety_backup
    from .database import LOCAL_TZ, db_session
    from .holding_calculator import infer_category, recalc_holdings, validate_holding_history
    from .price_sync import fetch_open_fund_nav, fetch_stock_quotes
    from .return_sync import calculate_trailing_return_1y, ensure_holding_return_columns
    from .snapshots import clear_manual_price_codes, mark_manual_price_code
except ImportError:
    from cash import set_setting
    from csv_utils import create_safety_backup
    from database import LOCAL_TZ, db_session
    from holding_calculator import infer_category, recalc_holdings, validate_holding_history
    from price_sync import fetch_open_fund_nav, fetch_stock_quotes
    from return_sync import calculate_trailing_return_1y, ensure_holding_return_columns
    from snapshots import clear_manual_price_codes, mark_manual_price_code

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


class ManualPriceUpdate(BaseModel):
    """手动填某只持仓的现价。

    price 故意不声明成 float：pydantic 校验失败会走 FastAPI 的 422，
    而用户要的是「中文 400」。所以这里收下任意类型，在下面逐条给出
    给人看的报错。
    """

    price: Any = None
    note: Optional[str] = None


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


@router.put("/holdings/{code}/price")
def set_manual_holding_price(code: str, payload: ManualPriceUpdate):
    """人工填某只持仓的现价（所有行情源都挂时的兜底）。

    语义：用户明确确认了「今天的价就是这个」，所以
    - holdings.last_price / updated_at 按用户给的价刷新；
    - settings.last_price_sync_at 同时刷新 → 快照闸门（resolve_snapshot_price_state）
      放行，不需要再 force=true 记录一个用旧价算出来的错快照；
    - code 记进 settings.manual_price_codes，快照据此落 manual_price_count，
      下一次真实行情同步成功时自动撤掉标记。
    校验失败一律 400 + 给人看的中文；code 不在 holdings 表里则 404。
    """
    code = str(code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="代码不能为空")

    raw_price = payload.price
    # bool 是 int 的子类，True/False 不能当价格用
    if raw_price is None or isinstance(raw_price, bool) or not isinstance(raw_price, (int, float)):
        raise HTTPException(status_code=400, detail="价格必须是一个数字，例如 38.36")
    price = float(raw_price)
    if not math.isfinite(price):
        raise HTTPException(status_code=400, detail="价格必须是有限数字（不能是 NaN 或无穷大）")
    if price <= 0:
        raise HTTPException(status_code=400, detail="价格必须大于 0")

    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    now_text = now.strftime("%Y-%m-%d %H:%M:%S")
    with db_session(row_factory=sqlite3.Row) as conn:
        exists = conn.execute("SELECT code FROM holdings WHERE code = ?", (code,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail=f"持仓里没有 {code} 这只标的")
        conn.execute(
            "UPDATE holdings SET last_price = ?, updated_at = ? WHERE code = ?",
            (price, now, code),
        )
        # 手动价 = 用户确认过的「今天的价」→ 闸门放行（与一次成功的同步同语义）
        set_setting(conn, "last_price_sync_at", now_text)
        codes = mark_manual_price_code(conn, code)
        conn.commit()
    return {
        "status": "success",
        "code": code,
        "price": price,
        "updated_at": now_text,
        "manual_price_codes": codes,
    }


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
    # 东财优先、腾讯兜底；返回完整报价（含 source），下面按标的标出来源
    stock_quotes = {}
    try:
        stock_quotes = fetch_stock_quotes(codes)
    except Exception as e:
        logger.error(f"stock quote batch sync failed: {e}")

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
                quote = stock_quotes.get(lookup_code) or {}
                price = quote.get("price")
                # 东财实时行情整段不可用时走的是腾讯兜底，如实标出，便于排查
                source = quote.get("source") or "东方财富行情"

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
    #
    # last_price_sync_at 只在**整批都成功**时刷新。这条规则是 2026-09-23 的真实事故换来的：
    # 那天东财实时行情接口整段不可用，10 只里只有 2 只货基（走天天基金）成功，于是
    # "至少一只成功"把当天标成"价格已更新" → 16:40 的快照用 09-22 的价写下了 09-23，
    # 当日收益显示 +148（实际涨跌完全没进来），而且这个错数字会进 TWR / 今年 / 收益尺。
    # 失败的标的记进 settings，供快照闸门提示，便于定位长期取不到价的代码。
    with db_session() as conn:
        if pending:
            conn.executemany(
                "UPDATE holdings SET last_price = ?, updated_at = ? WHERE code = ?",
                pending,
            )
            # 真实行情覆盖了人工价 → 撤掉这些 code 的「人工」标记（同一个短事务里写）。
            # 整批成功时 pending 覆盖全部持仓 → 标记列表自然清空；部分成功时
            # 未成功那些标的的标记原样保留，快照据此继续如实标 manual_price_count。
            clear_manual_price_codes(conn, [row[2] for row in pending])
        if failed:
            set_setting(conn, "last_price_sync_failed", ",".join(str(f["code"]) for f in failed))
        else:
            set_setting(conn, "last_price_sync_at", now.strftime("%Y-%m-%d %H:%M:%S"))
            set_setting(conn, "last_price_sync_failed", "")
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
