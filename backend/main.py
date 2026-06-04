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

class SecuritiesCashUpdate(BaseModel):
    amount: float

class CashFlowBase(BaseModel):
    date: dt_date
    account: Optional[str] = None
    flow_type: str
    amount: float
    remark: Optional[str] = None

class CashFlowUpdate(BaseModel):
    date: Optional[dt_date] = None
    account: Optional[str] = None
    flow_type: Optional[str] = None
    amount: Optional[float] = None
    remark: Optional[str] = None

DEFAULT_FEE_RULES = {
    "A股权益": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0005, "transfer_fee_rate": 0.00001, "min_commission": 0.0},
    "A股ETF": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "港股ETF": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "REITs": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "黄金": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "债基": {"commission_rate": 0.0, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "其他": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0}
}
class FeeSettingsUpdate(BaseModel):
    accounts: Optional[List[str]] = None
    active_account: Optional[str] = None
    settings: dict

def normalize_fee_rule(rule=None, default=None):
    base = (default or {"commission_rate": 0.0, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0}).copy()
    if isinstance(rule, dict):
        for key in ["commission_rate", "stamp_tax_rate", "transfer_fee_rate", "min_commission"]:
            try:
                base[key] = float(rule.get(key, base.get(key, 0.0)) or 0.0)
            except Exception:
                pass
    return base

def normalize_category_settings(raw=None):
    merged = {k: v.copy() for k, v in DEFAULT_FEE_RULES.items()}
    if isinstance(raw, dict):
        for cat, rule in raw.items():
            merged[cat] = normalize_fee_rule(rule, merged.get(cat))
    return merged

def normalize_fee_settings(raw=None):
    # New format: {accounts: [], active_account: str, settings: {account: {category: rule}}}
    # Important: when `accounts` is explicitly provided, it is the source of truth.
    # Do not resurrect deleted accounts from stale `settings` keys.
    if isinstance(raw, dict) and isinstance(raw.get("settings"), dict):
        explicit_accounts = "accounts" in raw and raw.get("accounts") is not None
        accounts = [str(a).strip() for a in raw.get("accounts", []) if str(a).strip()]
        if not explicit_accounts:
            accounts = [str(a).strip() for a in raw.get("settings", {}).keys() if str(a).strip()]
        accounts = list(dict.fromkeys(accounts))
        if not accounts:
            accounts = [DEFAULT_ACCOUNT]

        settings_by_account = {}
        for acc in accounts:
            rules = raw.get("settings", {}).get(acc, {})
            settings_by_account[acc] = normalize_category_settings(rules)

        active = str(raw.get("active_account") or accounts[0] or DEFAULT_ACCOUNT).strip()
        if active not in accounts:
            active = accounts[0]
        return {"accounts": accounts, "active_account": active, "settings": settings_by_account}

    # Old flat format: {category: rule}; migrate to single default account
    flat = normalize_category_settings(raw if isinstance(raw, dict) else None)
    return {"accounts": [DEFAULT_ACCOUNT], "active_account": DEFAULT_ACCOUNT, "settings": {DEFAULT_ACCOUNT: flat}}

def get_fee_settings_from_conn(conn):
    row = conn.execute("SELECT value FROM settings WHERE key='fee_settings'").fetchone()
    raw = None
    if row:
        try:
            value = row["value"] if isinstance(row, sqlite3.Row) else row[0]
            raw = json.loads(value)
        except Exception:
            raw = None
    return normalize_fee_settings(raw)

@app.get("/fee-settings")
def get_fee_settings():
    conn = open_db()
    conn.row_factory = sqlite3.Row
    data = get_fee_settings_from_conn(conn)
    conn.close()
    return data

@app.put("/fee-settings")
def update_fee_settings(data: FeeSettingsUpdate):
    conn = open_db()
    normalized = normalize_fee_settings({
        "accounts": data.accounts or [],
        "active_account": data.active_account,
        "settings": data.settings
    })
    set_setting(conn, 'fee_settings', json.dumps(normalized, ensure_ascii=False))
    conn.commit()
    conn.close()
    return {"status": "success", **normalized}

@app.post("/fee-settings/reset")
def reset_fee_settings():
    conn = open_db()
    normalized = normalize_fee_settings({"accounts": [DEFAULT_ACCOUNT], "active_account": DEFAULT_ACCOUNT, "settings": {DEFAULT_ACCOUNT: DEFAULT_FEE_RULES}})
    set_setting(conn, 'fee_settings', json.dumps(normalized, ensure_ascii=False))
    conn.commit()
    conn.close()
    return {"status": "success", **normalized}

@app.get("/securities-cash")
def get_securities_cash():
    conn = open_db()
    conn.row_factory = sqlite3.Row
    amount, base, flow = calculated_securities_cash(conn)
    manual_flow = cash_flow_adjustment(conn)
    conn.commit()
    conn.close()
    return {"amount": amount, "base_amount": base, "cash_flow_adjustment": manual_flow, "transaction_cash_flow": flow}

@app.put("/securities-cash")
def update_securities_cash(data: SecuritiesCashUpdate):
    """手动设置当前证券现金余额：不覆盖历史，按差额写入一条“现金校准”资金流水。"""
    conn = open_db()
    conn.row_factory = sqlite3.Row
    current, base, tx_flow = calculated_securities_cash(conn)
    delta = float(data.amount or 0) - current
    if abs(delta) >= 0.005:
        conn.execute("""
            INSERT INTO cash_flows (date, account, flow_type, amount, balance_before, balance_after, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (dt_date.today().isoformat(), DEFAULT_ACCOUNT, '现金校准', delta, current, float(data.amount or 0), '现金设置页手动校准'))
    # 保留旧key为当前显示余额，兼容历史脚本/查询；实际计算以base+资金流水+交易现金流为准。
    set_setting(conn, 'securities_cash', data.amount)
    manual_flow = cash_flow_adjustment(conn)
    conn.commit()
    conn.close()
    return {"status": "success", "amount": data.amount, "base_amount": base, "cash_flow_adjustment": manual_flow, "transaction_cash_flow": tx_flow, "delta": delta}


@app.get("/cash-flows")
def list_cash_flows(start_date: Optional[str] = None, end_date: Optional[str] = None, account: Optional[str] = None, flow_type: Optional[str] = None):
    conn = open_db()
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM cash_flows WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if account:
        query += " AND account = ?"
        params.append(account)
    if flow_type:
        query += " AND flow_type = ?"
        params.append(flow_type)
    query += " ORDER BY date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/cash-flows")
def add_cash_flow(flow_data: CashFlowBase):
    conn = open_db()
    conn.row_factory = sqlite3.Row
    before, _, _ = calculated_securities_cash(conn)
    amount = normalize_cash_flow_amount(flow_data.flow_type, flow_data.amount)
    after = before + amount
    conn.execute("""
        INSERT INTO cash_flows (date, account, flow_type, amount, balance_before, balance_after, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (flow_data.date.isoformat(), flow_data.account or DEFAULT_ACCOUNT, flow_data.flow_type, amount, before, after, flow_data.remark))
    set_setting(conn, 'securities_cash', after)
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "success", "id": new_id, "amount": amount, "balance_before": before, "balance_after": after}

@app.put("/cash-flows/{flow_id}")
def update_cash_flow(flow_id: int, flow_data: CashFlowUpdate):
    conn = open_db()
    conn.row_factory = sqlite3.Row
    old = conn.execute("SELECT * FROM cash_flows WHERE id = ?", (flow_id,)).fetchone()
    if not old:
        conn.close()
        raise HTTPException(status_code=404, detail="Cash flow not found")
    updates = []
    vals = []
    if flow_data.date is not None:
        updates.append("date = ?")
        vals.append(flow_data.date.isoformat())
    if flow_data.account is not None:
        updates.append("account = ?")
        vals.append(flow_data.account or DEFAULT_ACCOUNT)
    new_type = flow_data.flow_type if flow_data.flow_type is not None else old['flow_type']
    if flow_data.flow_type is not None:
        updates.append("flow_type = ?")
        vals.append(flow_data.flow_type)
    if flow_data.amount is not None:
        updates.append("amount = ?")
        vals.append(normalize_cash_flow_amount(new_type, flow_data.amount))
    if flow_data.remark is not None:
        updates.append("remark = ?")
        vals.append(flow_data.remark)
    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")
    vals.append(flow_id)
    conn.execute(f"UPDATE cash_flows SET {', '.join(updates)} WHERE id = ?", vals)
    amount, _, _ = calculated_securities_cash(conn)
    set_setting(conn, 'securities_cash', amount)
    conn.commit()
    conn.close()
    return {"status": "success", "amount": amount}

@app.delete("/cash-flows/{flow_id}")
def delete_cash_flow(flow_id: int):
    conn = open_db()
    conn.row_factory = sqlite3.Row
    conn.execute("DELETE FROM cash_flows WHERE id = ?", (flow_id,))
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Cash flow not found")
    amount, _, _ = calculated_securities_cash(conn)
    set_setting(conn, 'securities_cash', amount)
    conn.commit()
    conn.close()
    return {"status": "success", "amount": amount}

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
