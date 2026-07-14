import os
import threading
import time
from typing import Dict, Optional

import requests

# Short in-process cache to cut Eastmoney chatter (summary + alerts in same minute).
_QUOTE_CACHE_LOCK = threading.Lock()
_QUOTE_CACHE: Dict[str, dict] = {}  # code -> {quote, ts}
_CACHE_TTL = max(0, int(os.environ.get("MARKET_QUOTE_CACHE_SECONDS", "120")))


def clear_quote_cache() -> None:
    """Test / admin helper."""
    with _QUOTE_CACHE_LOCK:
        _QUOTE_CACHE.clear()


def eastmoney_sec_id(code: str) -> str:
    """Eastmoney secid: A股/深市ETF=0.xxx，上市沪市股票/ETF/REIT=1.xxx。"""
    c = str(code or "").strip().lower().replace("f", "")
    if c.startswith(("6", "5")):
        return f"1.{c}"
    return f"0.{c}"


def _cache_get(codes, now: float) -> Dict[str, dict]:
    if _CACHE_TTL <= 0:
        return {}
    out = {}
    with _QUOTE_CACHE_LOCK:
        for c in codes:
            entry = _QUOTE_CACHE.get(c)
            if not entry:
                continue
            if now - entry["ts"] <= _CACHE_TTL:
                out[c] = dict(entry["quote"])
    return out


def _cache_put(quotes: dict, now: float) -> None:
    if _CACHE_TTL <= 0 or not quotes:
        return
    with _QUOTE_CACHE_LOCK:
        for code, q in quotes.items():
            _QUOTE_CACHE[code] = {"quote": dict(q), "ts": now}


def fetch_eastmoney_quotes(codes, secid_map=None, *, use_cache: bool = True):
    """Fetch quotes from Eastmoney push2delay.

    Returns {code: {price, change_pct, name, prev_close?}} for successful rows.
    secid_map: optional {code: "1.000300"} overrides eastmoney_sec_id for indices.
    """
    secid_map = secid_map or {}
    numeric_codes = []
    for c in codes:
        raw = str(c).strip().lower().replace("f", "")
        if raw.isdigit() and len(raw) == 6:
            numeric_codes.append(raw)
    if not numeric_codes:
        return {}

    now = time.time()
    quotes = {}
    if use_cache:
        quotes.update(_cache_get(numeric_codes, now))
    missing = [c for c in numeric_codes if c not in quotes]
    if not missing:
        return quotes

    for i in range(0, len(missing), 40):
        batch = missing[i : i + 40]
        secids = ",".join(secid_map.get(c) or eastmoney_sec_id(c) for c in batch)
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": "2",
            "invt": "2",
            # f2 price, f3 change%, f12 code, f14 name, f18 昨收
            "fields": "f12,f14,f2,f3,f18",
            "secids": secids,
        }
        res = requests.get(
            url,
            params=params,
            timeout=8,
            headers={"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"},
        )
        res.raise_for_status()
        data = res.json().get("data") or {}
        batch_quotes = {}
        for item in data.get("diff") or []:
            code = str(item.get("f12") or "").strip()
            price = item.get("f2")
            if not code or price in (None, "-"):
                continue
            change_pct = item.get("f3")
            if change_pct in (None, "-"):
                change_pct = None
            else:
                try:
                    change_pct = float(change_pct)
                except (TypeError, ValueError):
                    change_pct = None
            prev_close = item.get("f18")
            if prev_close in (None, "-"):
                prev_close = None
            else:
                try:
                    prev_close = float(prev_close)
                except (TypeError, ValueError):
                    prev_close = None
            # If change_pct missing but prev_close present, derive
            px = float(price)
            if change_pct is None and prev_close and prev_close > 0:
                change_pct = (px / prev_close - 1.0) * 100.0
            batch_quotes[code] = {
                "price": px,
                "change_pct": change_pct,
                "name": str(item.get("f14") or "").strip(),
                "prev_close": prev_close,
            }
        quotes.update(batch_quotes)
        _cache_put(batch_quotes, now)
    return quotes


def fetch_eastmoney_prices(codes):
    """Backward-compatible: {code: price} only."""
    quotes = fetch_eastmoney_quotes(codes)
    return {code: q["price"] for code, q in quotes.items() if q.get("price") is not None}


def fetch_open_fund_nav(code: str):
    import akshare as ak  # lazy: not required for app boot / unit tests

    fund_code = str(code or "").strip().lower().replace("f", "")
    df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
    if df is None or df.empty:
        return None
    return float(df.iloc[-1]["单位净值"])
