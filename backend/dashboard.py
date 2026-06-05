try:
    from .cash import calculated_securities_cash, ensure_cash_base
except ImportError:
    from cash import calculated_securities_cash, ensure_cash_base


def build_dashboard(conn):
    ensure_cash_base(conn)
    holdings = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
    deposits = conn.execute("SELECT SUM(amount) as total FROM deposits").fetchone()
    pending_row = conn.execute("""
        SELECT SUM(amount + COALESCE(fee, 0)) as total
        FROM transactions
        WHERE direction IN ('申购待确认', '待确认申购')
    """).fetchone()
    securities_cash, _, _ = calculated_securities_cash(conn)

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
        "holdings_count": len(holdings),
    }
