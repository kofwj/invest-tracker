"""Pure-function style checks for deposit interest helpers (frontend formulas mirrored in Python)."""


def interest_for_days(amount, rate_pct, days):
    if days is None:
        return None
    d = float(days)
    if d < 0:
        return 0.0
    return float(amount or 0) * float(rate_pct or 0) / 100.0 * d / 365.0


def days_between(start_str, end_str):
    if not start_str or not end_str:
        return None
    from datetime import date
    start = date.fromisoformat(str(start_str)[:10])
    end = date.fromisoformat(str(end_str)[:10])
    return (end - start).days


def test_interest_for_days_basic():
    # 100000 * 1.825% * 365/365 = 1825
    val = interest_for_days(100000, 1.825, 365)
    assert val is not None
    assert abs(val - 1825.0) < 1e-6
    assert interest_for_days(100000, 1.3, -3) == 0.0
    assert interest_for_days(100000, 1.3, None) is None


def test_interest_remaining_vs_term():
    amount, rate = 200000, 1.3
    remaining = interest_for_days(amount, rate, 0)
    assert remaining == 0.0
    term_days = days_between("2025-07-18", "2026-07-18")
    assert term_days == 365
    term = interest_for_days(amount, rate, term_days)
    assert term is not None
    assert abs(term - amount * rate / 100) < 1e-6


def test_days_between_missing_returns_none():
    assert days_between(None, "2026-07-18") is None
    assert days_between("2025-01-01", "") is None
