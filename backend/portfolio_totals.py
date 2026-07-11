"""Shared portfolio totals used by dashboard and performance views.

Keeps holdings/cash/bank/pending math in one place so homepage and
performance summary cannot drift.
"""
from __future__ import annotations

try:
    from .cash import calculated_securities_cash, ensure_cash_base
except ImportError:
    from cash import calculated_securities_cash, ensure_cash_base

PENDING_DIRECTIONS = ("申购待确认", "待确认申购")


def _row_get(row, key, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def holding_float_profit(row) -> float:
    """持仓浮盈 = (现价 − 普通成本)×数量 + 累计分红。"""
    qty = float(_row_get(row, "quantity", 0) or 0)
    last = float(_row_get(row, "last_price", 0) or 0)
    avg = float(_row_get(row, "avg_cost", 0) or 0)
    div = float(_row_get(row, "total_dividend", 0) or 0)
    return (last - avg) * qty + div


def holding_lifetime_profit(row) -> float:
    """全周期盈亏 = (现价 − 摊薄成本)×数量；摊薄缺省时回退普通成本。"""
    qty = float(_row_get(row, "quantity", 0) or 0)
    last = float(_row_get(row, "last_price", 0) or 0)
    diluted = _row_get(row, "diluted_cost", None)
    if diluted is None:
        diluted = _row_get(row, "avg_cost", 0) or 0
    return (last - float(diluted or 0)) * qty


def fetch_active_holdings(conn):
    return conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()


def pending_purchase_stats(conn):
    placeholders = ",".join("?" for _ in PENDING_DIRECTIONS)
    row = conn.execute(
        f"""
        SELECT SUM(amount + COALESCE(fee, 0)) as total, COUNT(*) as cnt
        FROM transactions
        WHERE direction IN ({placeholders})
        """,
        PENDING_DIRECTIONS,
    ).fetchone()
    total = float(_row_get(row, "total", 0) or 0) if row is not None else 0.0
    cnt = int(_row_get(row, "cnt", 0) or 0) if row is not None else 0
    return total, cnt


def bank_balance_total(conn) -> float:
    row = conn.execute("SELECT SUM(amount) as total FROM deposits").fetchone()
    if not row:
        return 0.0
    return float(_row_get(row, "total", 0) or 0)


def compute_portfolio_totals(conn, *, holdings=None):
    """Return market/cash/bank/pending/profits for current portfolio state."""
    ensure_cash_base(conn)
    if holdings is None:
        holdings = fetch_active_holdings(conn)

    market_value = 0.0
    total_profit = 0.0
    lifetime_profit = 0.0
    for h in holdings:
        qty = float(_row_get(h, "quantity", 0) or 0)
        last = float(_row_get(h, "last_price", 0) or 0)
        market_value += qty * last
        total_profit += holding_float_profit(h)
        lifetime_profit += holding_lifetime_profit(h)

    bank_balance = bank_balance_total(conn)
    pending_purchase, pending_count = pending_purchase_stats(conn)
    securities_cash, cash_base, tx_flow = calculated_securities_cash(conn)
    total_assets = market_value + bank_balance + securities_cash + pending_purchase

    return {
        "holdings": holdings,
        "holdings_count": len(holdings),
        "total_market_value": market_value,
        "bank_balance": bank_balance,
        "securities_cash": securities_cash,
        "cash_base": cash_base,
        "transaction_cash_flow": tx_flow,
        "pending_purchase": pending_purchase,
        "pending_count": pending_count,
        "total_assets": total_assets,
        "total_profit": total_profit,
        "lifetime_profit": lifetime_profit,
    }
