import logging
import sqlite3
from datetime import date as dt_date, datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from .csv_utils import create_safety_backup
    from .database import LOCAL_TZ, db_session
    from .holding_calculator import infer_category, recalc_holdings
    from .return_sync import calculate_trailing_return_1y, ensure_holding_return_columns
    from .price_sync import fetch_eastmoney_prices, fetch_open_fund_nav
except ImportError:
    from csv_utils import create_safety_backup
    from database import LOCAL_TZ, db_session
    from holding_calculator import infer_category, recalc_holdings
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
        recalc_holdings(conn, codes=[code] if code else None)
        conn.commit()
    return {"status": "success", "backup": backup_path}


def _sync_trailing_returns_impl(backup: bool = False):
    backup_path = create_safety_backup("before_sync_trailing_returns") if backup else None
    with db_session(row_factory=sqlite3.Row) as conn:
        ensure_holding_return_columns(conn)
        rows = conn.execute("SELECT code, name, last_price FROM holdings WHERE quantity > 0").fetchall()
        updated = 0
        failed = []
        details = []
        now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
        for row in rows:
            code = str(row["code"]).strip()
            pct, source = calculate_trailing_return_1y(code, row["last_price"])
            if pct is None:
                failed.append({"code": code, "name": row["name"], "reason": source})
            else:
                updated += 1
            conn.execute(
                """
                UPDATE holdings
                SET trailing_return_1y = ?, trailing_return_1y_source = ?, trailing_return_1y_updated_at = ?
                WHERE code = ?
                """,
                (pct, source, now, code),
            )
            details.append(
                {"code": code, "name": row["name"], "trailing_return_1y": pct, "source": source}
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
    with db_session(row_factory=sqlite3.Row) as conn:
        rows = conn.execute("SELECT code, name, last_price FROM holdings WHERE quantity > 0").fetchall()
        updated = 0
        unchanged = 0
        failed = []
        details = []
        now = datetime.now(LOCAL_TZ).replace(tzinfo=None)

        codes = [row["code"] for row in rows]
        em_prices = {}
        try:
            em_prices = fetch_eastmoney_prices(codes)
        except Exception as e:
            logger.error(f"Eastmoney batch price sync failed: {e}")

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
                    failed.append({"code": code, "name": row["name"], "reason": "未取到有效价格"})
                    continue

                conn.execute(
                    "UPDATE holdings SET last_price = ?, updated_at = ? WHERE code = ?",
                    (float(price), now, code),
                )
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

        conn.commit()
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
