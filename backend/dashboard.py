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

    latest_price = price_row["latest"] if price_row else None
    price_age_hours = None
    price_stale = False
    if latest_price:
        try:
            from datetime import datetime

            try:
                from .database import LOCAL_TZ
            except ImportError:
                from database import LOCAL_TZ
            raw = str(latest_price).replace("T", " ")[:19]
            ts = datetime.fromisoformat(raw)
            now = datetime.now(LOCAL_TZ).replace(tzinfo=None) if LOCAL_TZ else datetime.now()
            price_age_hours = round((now - ts).total_seconds() / 3600.0, 2)
            # 交易日口径粗略：超过 20 小时未更新视为偏旧（隔夜/周末另论）
            price_stale = price_age_hours >= 20
        except Exception:
            price_age_hours = None
            price_stale = False

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
        "latest_price_updated_at": latest_price,
        "price_age_hours": price_age_hours,
        "price_stale": price_stale,
        "latest_snapshot_date": snapshot_row["latest"] if snapshot_row else None,
    }
