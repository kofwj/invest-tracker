from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import date as dt_date, datetime
import sqlite3
import pandas as pd
import akshare as ak
import os
import logging
import requests
import urllib.request
import json as pyjson
import math
import json
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

try:
    from .database import (
        APP_CONFIG,
        DB_PATH,
        LOCAL_TZ,
        check_database_health as _check_database_health,
        db_session,
        fetch_all_as_dicts,
        get_db_connection,
        open_db,
    )
except ImportError:  # Allows tests to load this file directly via importlib.
    from database import (
        APP_CONFIG,
        DB_PATH,
        LOCAL_TZ,
        check_database_health as _check_database_health,
        db_session,
        fetch_all_as_dicts,
        get_db_connection,
        open_db,
    )

try:
    from .csv_utils import (
        DEPOSIT_CSV_COLUMNS,
        DEPOSIT_HEADER_ALIASES,
        TRANSACTION_CSV_COLUMNS,
        TRANSACTION_HEADER_ALIASES,
        create_import_backup,
        csv_response,
        normalize_csv_row,
        normalize_date_string,
        parse_float,
        read_upload_csv,
    )
    from .holdings import (
        calculate_trailing_return_1y,
        eastmoney_sec_id,
        ensure_holding_return_columns,
        fetch_eastmoney_prices,
        fetch_open_fund_nav,
        infer_category,
        latest_holding_corrections,
        market_prefix,
        normalized_transaction_cash,
        recalc_holdings,
    )
    from .cash import (
        DEFAULT_ACCOUNT,
        cash_flow_adjustment,
        calculated_securities_cash,
        ensure_cash_base,
        get_setting_float,
        normalize_cash_flow_amount,
        set_setting,
        transaction_cash_flow,
    )
    from .performance import (
        build_performance_contribution,
        build_performance_summary,
        build_performance_timeline,
        calculate_xirr,
    )
    from .snapshots import (
        create_snapshot_record,
        ensure_portfolio_cash_flows_table as ensure_portfolio_cash_flows_table_impl,
        ensure_snapshot_columns as ensure_snapshot_columns_impl,
        list_snapshots_rows,
        snapshots_summary_data,
    )
    from .routers_deposits import router as deposits_router
    from .routers_transactions import router as transactions_router
    from .routers_cash import router as cash_router
except ImportError:  # Allows tests to load this file directly via importlib.
    from csv_utils import (
        DEPOSIT_CSV_COLUMNS,
        DEPOSIT_HEADER_ALIASES,
        TRANSACTION_CSV_COLUMNS,
        TRANSACTION_HEADER_ALIASES,
        create_import_backup,
        csv_response,
        normalize_csv_row,
        normalize_date_string,
        parse_float,
        read_upload_csv,
    )
    from holdings import (
        calculate_trailing_return_1y,
        eastmoney_sec_id,
        ensure_holding_return_columns,
        fetch_eastmoney_prices,
        fetch_open_fund_nav,
        infer_category,
        latest_holding_corrections,
        market_prefix,
        normalized_transaction_cash,
        recalc_holdings,
    )
    from cash import (
        DEFAULT_ACCOUNT,
        cash_flow_adjustment,
        calculated_securities_cash,
        ensure_cash_base,
        get_setting_float,
        normalize_cash_flow_amount,
        set_setting,
        transaction_cash_flow,
    )
    from performance import (
        build_performance_contribution,
        build_performance_summary,
        build_performance_timeline,
        calculate_xirr,
    )
    from snapshots import (
        create_snapshot_record,
        ensure_portfolio_cash_flows_table as ensure_portfolio_cash_flows_table_impl,
        ensure_snapshot_columns as ensure_snapshot_columns_impl,
        list_snapshots_rows,
        snapshots_summary_data,
    )
    from routers_deposits import router as deposits_router
    from routers_transactions import router as transactions_router
    from routers_cash import router as cash_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Investment Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(deposits_router)
app.include_router(transactions_router)
app.include_router(cash_router)

def local_today_iso():
    return datetime.now(LOCAL_TZ).date().isoformat()


def check_database_health():
    return _check_database_health(DB_PATH)


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "database": check_database_health(),
        "timezone": str(APP_CONFIG.local_timezone),
        "db_path": DB_PATH,
    }

class TransactionBase(BaseModel):
    date: dt_date
    code: str
    name: str
    category: Optional[str] = None
    account: Optional[str] = None
    direction: str
    quantity: float
    price: float
    amount: float
    fee: float = 0.0
    remark: Optional[str] = None

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

class HoldingCorrectionBase(BaseModel):
    date: dt_date
    code: str
    name: Optional[str] = None
    category: Optional[str] = None
    actual_quantity: float
    actual_avg_cost: float
    actual_total_dividend: Optional[float] = 0.0
    remark: Optional[str] = None

class HoldingCorrectionUpdate(BaseModel):
    date: Optional[dt_date] = None
    name: Optional[str] = None
    category: Optional[str] = None
    actual_quantity: Optional[float] = None
    actual_avg_cost: Optional[float] = None
    actual_total_dividend: Optional[float] = None
    remark: Optional[str] = None

class DepositSchema(BaseModel):
    id: Optional[int] = None
    bank_name: str
    amount: float
    interest_rate: Optional[float] = None
    due_date: Optional[str] = None
    remark: Optional[str] = None


def ensure_core_tables(conn):
    """Create the core application tables required for a fresh SQLite database."""
    conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        code TEXT,
        name TEXT,
        category TEXT,
        account TEXT DEFAULT '华泰证券',
        direction TEXT,
        quantity REAL DEFAULT 0,
        price REAL DEFAULT 0,
        amount REAL DEFAULT 0,
        fee REAL DEFAULT 0,
        remark TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        name TEXT,
        category TEXT,
        quantity REAL DEFAULT 0,
        avg_cost REAL DEFAULT 0,
        diluted_cost REAL DEFAULT 0,
        total_dividend REAL DEFAULT 0,
        last_price REAL DEFAULT 0,
        updated_at DATETIME,
        expected_return REAL DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_name TEXT,
        amount REAL,
        interest_rate REAL,
        due_date TEXT,
        remark TEXT
    )""")
    ensure_holding_return_columns(conn)


def ensure_app_schema(conn):
    ensure_core_tables(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cash_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        account TEXT DEFAULT '华泰证券',
        flow_type TEXT,
        amount REAL,
        balance_before REAL,
        balance_after REAL,
        remark TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE UNIQUE,
        total_assets REAL,
        total_market_value REAL,
        bank_balance REAL,
        securities_cash REAL,
        pending_purchase REAL DEFAULT 0,
        total_profit REAL,
        holdings_count INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS holding_corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        code TEXT NOT NULL,
        name TEXT,
        category TEXT,
        actual_quantity REAL NOT NULL,
        actual_avg_cost REAL NOT NULL,
        actual_total_dividend REAL DEFAULT 0,
        remark TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS portfolio_cash_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        flow_type TEXT NOT NULL,
        amount REAL NOT NULL,
        source TEXT,
        remark TEXT,
        created_at DATETIME DEFAULT (datetime('now','localtime'))
    )""")
    ensure_snapshot_columns(conn)


@app.get("/holdings", response_model=List[HoldingSchema])
def list_holdings():
    try:
        with db_session(row_factory=sqlite3.Row) as conn:
            rows = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Holdings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sync-trailing-returns")
def sync_trailing_returns():
    """同步当前持仓近一年标的收益率。该收益率是标的自身价格/净值回溯，不等于账户实际持有收益。"""
    conn = open_db()
    conn.row_factory = sqlite3.Row
    ensure_holding_return_columns(conn)
    rows = conn.execute("SELECT code, name, last_price FROM holdings WHERE quantity > 0").fetchall()
    updated = 0
    failed = []
    details = []
    now = datetime.now()
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
    return {"status": "success", "checked": len(rows), "updated": updated, "failed": failed, "details": details}


@app.get("/sync-prices")
def sync_prices():
    conn = open_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT code, name, last_price FROM holdings WHERE quantity > 0").fetchall()
    updated = 0
    unchanged = 0
    failed = []
    details = []
    now = datetime.now()

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
    return {"status": "success", "updated": updated, "unchanged": unchanged, "failed": failed, "details": details, "checked": len(rows)}



@app.get("/dashboard")
def get_dashboard():
    conn = open_db()
    conn.row_factory = sqlite3.Row
    ensure_cash_base(conn)
    holdings = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
    deposits = conn.execute("SELECT SUM(amount) as total FROM deposits").fetchone()
    pending_row = conn.execute("""
        SELECT SUM(amount + COALESCE(fee, 0)) as total
        FROM transactions
        WHERE direction IN ('申购待确认', '待确认申购')
    """).fetchone()
    securities_cash, _, _ = calculated_securities_cash(conn)
    conn.commit()
    conn.close()
    
    total_market_value = sum(h['quantity'] * h['last_price'] for h in holdings)
    bank_balance = deposits['total'] or 0
    pending_purchase = float(pending_row['total'] or 0) if pending_row else 0
    total_profit = sum((h['last_price'] - h['avg_cost']) * h['quantity'] + h['total_dividend'] for h in holdings)
    
    return {
        "total_market_value": total_market_value,
        "bank_balance": bank_balance,
        "securities_cash": securities_cash,
        "pending_purchase": pending_purchase,
        "total_assets": total_market_value + bank_balance + securities_cash + pending_purchase,
        "total_profit": total_profit,
        "holdings_count": len(holdings)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# === 新增：证券现金管理 ===

def initialize_database():
    with open_db() as conn:
        ensure_app_schema(conn)
        conn.commit()

@app.on_event("startup")
def startup():
    initialize_database()
    # 初始化/迁移证券现金：securities_cash_base 为手动基准，交易现金流自动联动
    conn = open_db()
    conn.row_factory = sqlite3.Row
    cols = [row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if "account" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN account TEXT")
        conn.execute("UPDATE transactions SET account = '华泰证券' WHERE account IS NULL OR TRIM(account) = ''")
    row = conn.execute("SELECT value FROM settings WHERE key='securities_cash'").fetchone()
    if not row:
        set_setting(conn, 'securities_cash', 0)
    ensure_cash_base(conn)
    conn.commit()
    conn.close()

# === 新增：每日资产快照 ===
class SnapshotSchema(BaseModel):
    date: dt_date
    total_assets: float
    total_market_value: float
    bank_balance: float
    securities_cash: float
    pending_purchase: float = 0.0
    total_profit: float
    holdings_count: int


def ensure_snapshot_columns(conn):
    return ensure_snapshot_columns_impl(conn)


@app.post("/snapshots")
def create_snapshot():
    """记录当前资产快照。同一天重复点击时更新当天记录，避免价格/现金变化后仍保留旧数据。"""
    conn = open_db()
    conn.row_factory = sqlite3.Row
    dash = get_dashboard()
    today = local_today_iso()
    snapshot_id, action = create_snapshot_record(conn, today, dash)
    conn.commit()
    conn.close()
    return {"status": "success", "action": action, "id": snapshot_id, "date": today, "snapshot": dash}


@app.get("/snapshots")
def list_snapshots(start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = open_db()
    conn.row_factory = sqlite3.Row
    rows = list_snapshots_rows(conn, start_date, end_date)
    conn.close()
    return rows


@app.get("/snapshots/summary")
def snapshots_summary(start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = open_db()
    conn.row_factory = sqlite3.Row
    changes = snapshots_summary_data(conn, start_date, end_date)
    conn.close()
    return changes

# === 收益分析 v1：组合外部现金流 + XIRR + 组合收益 ===

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

def ensure_portfolio_cash_flows_table(conn):
    return ensure_portfolio_cash_flows_table_impl(conn)

@app.get("/portfolio-cash-flows")
def list_portfolio_cash_flows(start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = open_db()
    conn.row_factory = sqlite3.Row
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

@app.post("/portfolio-cash-flows")
def add_portfolio_cash_flow(flow: PortfolioCashFlowBase):
    conn = open_db()
    ensure_portfolio_cash_flows_table(conn)
    conn.execute(
        "INSERT INTO portfolio_cash_flows (date, flow_type, amount, source, remark) VALUES (?,?,?,?,?)",
        (flow.date.isoformat(), flow.flow_type, flow.amount, flow.source, flow.remark)
    )
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.put("/portfolio-cash-flows/{flow_id}")
def update_portfolio_cash_flow(flow_id: int, flow: PortfolioCashFlowUpdate):
    conn = open_db()
    conn.row_factory = sqlite3.Row
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
        (d, t, a, s, r, flow_id)
    )
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/portfolio-cash-flows/{flow_id}")
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


@app.get("/performance/summary")
def performance_summary():
    conn = open_db()
    conn.row_factory = sqlite3.Row
    ensure_portfolio_cash_flows_table(conn)
    data = build_performance_summary(conn)
    conn.close()
    return data


@app.get("/performance/timeline")
def performance_timeline(start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = open_db()
    conn.row_factory = sqlite3.Row
    ensure_portfolio_cash_flows_table(conn)
    result = build_performance_timeline(conn, start_date, end_date)
    conn.close()
    return result


@app.get("/performance/contribution")
def performance_contribution():
    conn = open_db()
    conn.row_factory = sqlite3.Row
    rows = build_performance_contribution(conn)
    conn.close()
    return rows
