"""Compatibility facade for holding-related helpers.

New code should import from:
- holding_calculator.py for transaction/category/holding recalculation logic
- price_sync.py for latest price/NAV fetching
- return_sync.py for trailing return calculations
"""
try:
    from .holding_calculator import (
        ALLOWED_DIRECTIONS,
        current_holding_quantity,
        infer_category,
        latest_holding_corrections,
        normalized_transaction_cash,
        recalc_holdings,
        validate_transaction_payload,
    )
except ImportError:
    from holding_calculator import (
        ALLOWED_DIRECTIONS,
        current_holding_quantity,
        infer_category,
        latest_holding_corrections,
        normalized_transaction_cash,
        recalc_holdings,
        validate_transaction_payload,
    )


def __getattr__(name):
    """Lazy-export price/return helpers so core app/tests boot without market deps."""
    market_names = {
        "eastmoney_sec_id",
        "fetch_eastmoney_prices",
        "fetch_open_fund_nav",
        "calculate_trailing_return_1y",
        "ensure_holding_return_columns",
        "fetch_tencent_kline_closes",
        "market_prefix",
        "nearest_numeric_value",
    }
    if name not in market_names:
        raise AttributeError(name)
    try:
        from . import price_sync, return_sync
    except ImportError:
        import price_sync
        import return_sync
    for mod in (price_sync, return_sync):
        if hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError(name)
