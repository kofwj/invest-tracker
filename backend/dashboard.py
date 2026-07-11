try:
    from .cash import calculated_securities_cash, ensure_cash_base
except ImportError:
    from cash import calculated_securities_cash, ensure_cash_base

PENDING_DIRECTIONS = ("申购待确认", "待确认申购")


def build_dashboard(conn):
    ensure_cash_base(conn)
    holdings = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
    deposits = conn.execute("SELECT SUM(amount) as total FROM deposits").fetchone()
    pending_row = conn.execute(
        """
        SELECT SUM(amount + COALESCE(fee, 0)) as total, COUNT(*) as cnt
        FROM transactions
        WHERE direction IN ('申购待确认', '待确认申购')
        """
    ).fetchone()
    securities_cash, _, _ = calculated_securities_cash(conn)

    total_market_value = sum(h["quantity"] * h["last_price"] for h in holdings)
    bank_balance = deposits["total"] or 0
    pending_purchase = float(pending_row["total"] or 0) if pending_row else 0
    pending_count = int(pending_row["cnt"] or 0) if pending_row else 0
    total_profit = sum(
        (h["last_price"] - h["avg_cost"]) * h["quantity"] + h["total_dividend"] for h in holdings
    )
    # 全周期盈亏：Σ(最新价 − 摊薄成本)×数量；接近券商累计盈亏，分红已在摊薄中体现
    lifetime_profit = sum(
        (h["last_price"] - (h["diluted_cost"] if h["diluted_cost"] is not None else h["avg_cost"])) * h["quantity"]
        for h in holdings
    )

    price_row = conn.execute(
        "SELECT MAX(updated_at) AS latest FROM holdings WHERE quantity > 0 AND updated_at IS NOT NULL"
    ).fetchone()
    snapshot_row = conn.execute("SELECT MAX(date) AS latest FROM daily_snapshots").fetchone()

    return {
        "total_market_value": total_market_value,
        "bank_balance": bank_balance,
        "securities_cash": securities_cash,
        "pending_purchase": pending_purchase,
        "pending_count": pending_count,
        "total_assets": total_market_value + bank_balance + securities_cash + pending_purchase,
        "total_profit": total_profit,
        "lifetime_profit": lifetime_profit,
        "holdings_count": len(holdings),
        "latest_price_updated_at": price_row["latest"] if price_row else None,
        "latest_snapshot_date": snapshot_row["latest"] if snapshot_row else None,
    }
