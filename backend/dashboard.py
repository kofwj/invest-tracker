try:
    from .portfolio_totals import compute_portfolio_totals
except ImportError:
    from portfolio_totals import compute_portfolio_totals

# Re-export for older imports / tests that may reference this name.
PENDING_DIRECTIONS = ("申购待确认", "待确认申购")


def build_dashboard(conn):
    totals = compute_portfolio_totals(conn)

    price_row = conn.execute(
        "SELECT MAX(updated_at) AS latest FROM holdings WHERE quantity > 0 AND updated_at IS NOT NULL"
    ).fetchone()
    snapshot_row = conn.execute("SELECT MAX(date) AS latest FROM daily_snapshots").fetchone()

    return {
        "total_market_value": totals["total_market_value"],
        "bank_balance": totals["bank_balance"],
        "securities_cash": totals["securities_cash"],
        "pending_purchase": totals["pending_purchase"],
        "pending_count": totals["pending_count"],
        "total_assets": totals["total_assets"],
        "total_profit": totals["total_profit"],
        "lifetime_profit": totals["lifetime_profit"],
        "holdings_count": totals["holdings_count"],
        "latest_price_updated_at": price_row["latest"] if price_row else None,
        "latest_snapshot_date": snapshot_row["latest"] if snapshot_row else None,
    }
