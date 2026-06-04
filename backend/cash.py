import sqlite3

from datetime import date as dt_date

try:
    from .holdings import normalized_transaction_cash
except ImportError:
    from holdings import normalized_transaction_cash

DEFAULT_ACCOUNT = "华泰证券"


def transaction_cash_flow(conn):
    """交易对证券现金的自动影响：买入/申购待确认扣现金，卖出/分红加现金。"""
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT direction, quantity, price, amount, fee FROM transactions").fetchall()
    total = 0.0
    for r in rows:
        direction = r["direction"]
        cash = normalized_transaction_cash(direction, r["quantity"], r["price"], r["amount"], r["fee"])
        if direction in ("买入", "申购待确认", "待确认申购"):
            total -= cash
        elif direction in ("卖出", "分红"):
            total += cash
        elif direction == "分红再投资":
            # Dividend and reinvestment principal offset; fee is the only cash outflow.
            total -= float(r["fee"] or 0)
    return float(total)


def normalize_cash_flow_amount(flow_type, amount):
    """资金流水金额符号：转入为正，转出为负，校准/其他按传入差额。"""
    amt = float(amount or 0)
    if flow_type == '银证转入':
        return abs(amt)
    if flow_type == '银证转出':
        return -abs(amt)
    return amt


def cash_flow_adjustment(conn):
    """银证转入/转出/现金校准等非交易资金流水合计。"""
    try:
        row = conn.execute("SELECT SUM(COALESCE(amount, 0)) AS total FROM cash_flows").fetchone()
        return float((row['total'] if isinstance(row, sqlite3.Row) else row[0]) or 0)
    except sqlite3.OperationalError:
        return 0.0


def get_setting_float(conn, key, default=0.0):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        value = row["value"] if isinstance(row, sqlite3.Row) else row[0]
        return float(value)
    except Exception:
        return default


def set_setting(conn, key, value):
    conn.execute("""
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))


def ensure_cash_base(conn):
    """一次性把旧的 securities_cash 迁移为手动现金基准。"""
    base_row = conn.execute("SELECT value FROM settings WHERE key='securities_cash_base'").fetchone()
    if base_row:
        return
    displayed_cash = get_setting_float(conn, "securities_cash", 0.0)
    flow = transaction_cash_flow(conn)
    pending_row = conn.execute("""
        SELECT SUM(COALESCE(amount, 0) + COALESCE(fee, 0)) as total
        FROM transactions
        WHERE direction IN ('申购待确认', '待确认申购')
    """).fetchone()
    pending = float((pending_row["total"] if isinstance(pending_row, sqlite3.Row) else pending_row[0]) or 0)
    set_setting(conn, "securities_cash_base", displayed_cash - pending - flow)


def calculated_securities_cash(conn):
    ensure_cash_base(conn)
    base = get_setting_float(conn, "securities_cash_base", 0.0)
    tx_flow = transaction_cash_flow(conn)
    manual_flow = cash_flow_adjustment(conn)
    return base + manual_flow + tx_flow, base, tx_flow
