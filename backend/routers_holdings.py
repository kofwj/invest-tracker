import logging
import sqlite3
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from .csv_utils import create_safety_backup
    from .database import LOCAL_TZ
    from .database import db_session, open_db
    from .holdings import (
        calculate_trailing_return_1y,
        ensure_holding_return_columns,
        fetch_eastmoney_prices,
        fetch_open_fund_nav,
    )
except ImportError:
    from csv_utils import create_safety_backup
    from database import LOCAL_TZ
    from database import db_session, open_db
    from holdings import (
        calculate_trailing_return_1y,
        ensure_holding_return_columns,
        fetch_eastmoney_prices,
        fetch_open_fund_nav,
    )

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
    updated_at: datetime
    expected_return: Optional[float] = 0.0
    trailing_return_1y: Optional[float] = None
    trailing_return_1y_source: Optional[str] = None
    trailing_return_1y_updated_at: Optional[datetime] = None


@router.get("/holdings", response_model=List[HoldingSchema])
def list_holdings():
    try:
        with db_session(row_factory=sqlite3.Row) as conn:
            rows = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Holdings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync-trailing-returns")
def sync_trailing_returns(backup: bool = False):
    """同步当前持仓近一年标的收益率。该收益率是标的自身价格/净值回溯，不等于账户实际持有收益。"""
    backup_path = create_safety_backup("before_sync_trailing_returns") if backup else None
    conn = open_db(row_factory=sqlite3.Row)
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
        conn.execute("""
            UPDATE holdings
            SET trailing_return_1y = ?, trailing_return_1y_source = ?, trailing_return_1y_updated_at = ?
            WHERE code = ?
        """, (pct, source, now, code))
        details.append({"code": code, "name": row["name"], "trailing_return_1y": pct, "source": source})
    conn.commit()
    conn.close()
    return {"status": "success", "checked": len(rows), "updated": updated, "failed": failed, "details": details, "backup": backup_path}


@router.get("/sync-prices")
def sync_prices(backup: bool = False):
    backup_path = create_safety_backup("before_sync_prices") if backup else None
    conn = open_db(row_factory=sqlite3.Row)
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

            conn.execute("UPDATE holdings SET last_price = ?, updated_at = ? WHERE code = ?", (float(price), now, code))
            if abs(price - old_price) >= 1e-8:
                updated += 1
            else:
                unchanged += 1
            details.append({"code": code, "name": row["name"], "old_price": old_price, "new_price": float(price), "source": source})
        except Exception as e:
            logger.error(f"Error syncing {code}: {e}")
            failed.append({"code": code, "name": row["name"], "reason": str(e)})

    conn.commit()
    conn.close()
    return {"status": "success", "updated": updated, "unchanged": unchanged, "failed": failed, "details": details, "checked": len(rows), "backup": backup_path}
