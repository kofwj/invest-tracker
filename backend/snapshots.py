import logging
import sqlite3
from datetime import date as dt_date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from .database import LOCAL_TZ
except ImportError:
    from database import LOCAL_TZ


def ensure_snapshot_columns(conn):
    cols = [row[1] for row in conn.execute("PRAGMA table_info(daily_snapshots)").fetchall()]
    if "pending_purchase" not in cols:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN pending_purchase REAL DEFAULT 0")
    if "lifetime_profit" not in cols:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN lifetime_profit REAL DEFAULT 0")


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
    lifetime = dashboard.get("lifetime_profit", 0)
    existing = conn.execute("SELECT id FROM daily_snapshots WHERE date = ?", (today_iso,)).fetchone()
    if existing:
        conn.execute("""
            UPDATE daily_snapshots
            SET total_assets = ?, total_market_value = ?, bank_balance = ?, securities_cash = ?,
                pending_purchase = ?, total_profit = ?, lifetime_profit = ?, holdings_count = ?, created_at = ?
            WHERE date = ?
        """, (
            dashboard['total_assets'],
            dashboard['total_market_value'],
            dashboard['bank_balance'],
            dashboard['securities_cash'],
            dashboard.get('pending_purchase', 0),
            dashboard['total_profit'],
            lifetime,
            dashboard['holdings_count'],
            now,
            today_iso,
        ))
        return existing['id'], 'updated'

    conn.execute("""
        INSERT INTO daily_snapshots
        (date, total_assets, total_market_value, bank_balance, securities_cash, pending_purchase,
         total_profit, lifetime_profit, holdings_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        today_iso,
        dashboard['total_assets'],
        dashboard['total_market_value'],
        dashboard['bank_balance'],
        dashboard['securities_cash'],
        dashboard.get('pending_purchase', 0),
        dashboard['total_profit'],
        lifetime,
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
    anomaly = None
    prev = dict(rows[-2])
    try:
        prev_assets = float(prev.get("total_assets") or 0)
        last_assets = float(last.get("total_assets") or 0)
        if prev_assets > 0:
            day_chg_pct = (last_assets / prev_assets - 1.0) * 100.0
            day_chg_amt = last_assets - prev_assets
            # 异常：单日总资产变动 ≥2% 且金额 ≥1万
            if abs(day_chg_pct) >= 2.0 and abs(day_chg_amt) >= 10000:
                direction = "涨" if day_chg_amt > 0 else "跌"
                anomaly = {
                    "from_date": prev.get("date"),
                    "to_date": last.get("date"),
                    "change_amount": round(day_chg_amt, 2),
                    "change_pct": round(day_chg_pct, 2),
                    "text": (
                        f"盘后留意：总资产从 {prev.get('date')} 到 {last.get('date')} "
                        f"大约{direction}了 {abs(day_chg_amt):.0f} 元（{day_chg_pct:+.2f}%）。"
                        f"可能是行情、入金/出金或记账变动，建议对照资金流水。"
                    ),
                }
    except Exception as exc:
        logger.warning("snapshots_summary_data: day_over_day_anomaly failed: %s", exc)
        anomaly = None

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
        "lifetime_profit": {
            "start": first.get('lifetime_profit', 0) or 0,
            "end": last.get('lifetime_profit', 0) or 0,
            "change": (last.get('lifetime_profit', 0) or 0) - (first.get('lifetime_profit', 0) or 0),
        },
        "day_over_day_anomaly": anomaly,
    }
