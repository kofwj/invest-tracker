"""Compatibility facade for holding-related helpers.

New code should import from:
- holding_calculator.py for transaction/category/holding recalculation logic
- price_sync.py for latest price/NAV fetching
- return_sync.py for trailing return calculations
"""
try:
    from .holding_calculator import infer_category, latest_holding_corrections, normalized_transaction_cash, recalc_holdings
    from .price_sync import eastmoney_sec_id, fetch_eastmoney_prices, fetch_open_fund_nav
    from .return_sync import calculate_trailing_return_1y, ensure_holding_return_columns, fetch_tencent_kline_closes, market_prefix, nearest_numeric_value
except ImportError:
    from holding_calculator import infer_category, latest_holding_corrections, normalized_transaction_cash, recalc_holdings
    from price_sync import eastmoney_sec_id, fetch_eastmoney_prices, fetch_open_fund_nav
    from return_sync import calculate_trailing_return_1y, ensure_holding_return_columns, fetch_tencent_kline_closes, market_prefix, nearest_numeric_value
