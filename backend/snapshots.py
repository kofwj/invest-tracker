import sqlite3
from datetime import date as dt_date, datetime
from typing import Optional

try:
    from .database import LOCAL_TZ
except ImportError:
    from database import LOCAL_TZ


def ensure_snapshot_columns(conn):
    cols = [row[1] for row in conn.execute("PRAGMA table_info(daily_snapshots)").fetchall()]
    if "pending_purchase" not in cols:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN pending_purchase REAL DEFAULT 0")


def ensure_portfolio_cash_flows_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS portfolio_cash_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        flow_type TEXT NOT NULL,
        amount REAL NOT NULL,
        source TEXT,
        remark TEXT,
        created_at DATETIME DEFAULT (datetime('now','localtime'))
    )""")


def create_snapshot_record(conn, today_iso, dashboard):
    ensure_snapshot_columns(conn)
    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    existing = conn.execute("SELECT id FROM daily_snapshots WHERE date = ?", (today_iso,)).fetchone()
    if existing:
        conn.execute("""
            UPDATE daily_snapshots
            SET total_assets = ?, total_market_value = ?, bank_balance = ?, securities_cash = ?,
                pending_purchase = ?, total_profit = ?, holdings_count = ?, created_at = ?
            WHERE date = ?
        """, (
            dashboard['total_assets'],
            dashboard['total_market_value'],
            dashboard['bank_balance'],
            dashboard['securities_cash'],
            dashboard.get('pending_purchase', 0),
            dashboard['total_profit'],
            dashboard['holdings_count'],
            now,
            today_iso,
        ))
        return existing['id'], 'updated'

    conn.execute("""
        INSERT INTO daily_snapshots
        (date, total_assets, total_market_value, bank_balance, securities_cash, pending_purchase, total_profit, holdings_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        today_iso,
        dashboard['total_assets'],
        dashboard['total_market_value'],
        dashboard['bank_balance'],
        dashboard['securities_cash'],
        dashboard.get('pending_purchase', 0),
        dashboard['total_profit'],
        dashboard['holdings_count'],
        now,
    ))
    snapshot_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return snapshot_id, 'created'


def list_snapshots_rows(conn, start_date: Optional[str] = None, end_date: Optional[str] = None):
    ensure_snapshot_columns(conn)
    query = "SELECT * FROM daily_snapshots"
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
    query += " ORDER BY date DESC"
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def snapshots_summary_data(conn, start_date: Optional[str] = None, end_date: Optional[str] = None):
    ensure_snapshot_columns(conn)
    query = "SELECT * FROM daily_snapshots"
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
    query += " ORDER BY date ASC"
    rows = conn.execute(query, params).fetchall()
    if len(rows) < 2:
        return {"message": "需要至少两个快照来计算变化", "count": len(rows)}

    first = dict(rows[0])
    last = dict(rows[-1])
    return {
        "period": f"{first['date']} 至 {last['date']}",
        "days": (dt_date.fromisoformat(last['date']) - dt_date.fromisoformat(first['date'])).days,
        "total_assets": {
            "start": first['total_assets'],
            "end": last['total_assets'],
            "change": last['total_assets'] - first['total_assets'],
            "change_pct": (last['total_assets'] / first['total_assets'] - 1) * 100 if first['total_assets'] else 0,
        },
        "total_market_value": {
            "start": first['total_market_value'],
            "end": last['total_market_value'],
            "change": last['total_market_value'] - first['total_market_value'],
        },
        "bank_balance": {
            "start": first['bank_balance'],
            "end": last['bank_balance'],
            "change": last['bank_balance'] - first['bank_balance'],
        },
        "securities_cash": {
            "start": first['securities_cash'],
            "end": last['securities_cash'],
            "change": last['securities_cash'] - first['securities_cash'],
        },
        "pending_purchase": {
            "start": first.get('pending_purchase', 0),
            "end": last.get('pending_purchase', 0),
            "change": (last.get('pending_purchase', 0) or 0) - (first.get('pending_purchase', 0) or 0),
        },
    }
