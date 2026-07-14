import requests


def eastmoney_sec_id(code: str) -> str:
    """Eastmoney secid: A股/深市ETF=0.xxx，上市沪市股票/ETF/REIT=1.xxx。"""
    c = str(code or "").strip().lower().replace("f", "")
    if c.startswith(("6", "5")):
        return f"1.{c}"
    return f"0.{c}"


def fetch_eastmoney_quotes(codes, secid_map=None):
    """Fetch quotes from Eastmoney push2delay.

    Returns {code: {price, change_pct, name}} for successful rows.
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

    quotes = {}
    for i in range(0, len(numeric_codes), 40):
        batch = numeric_codes[i : i + 40]
        secids = ",".join(secid_map.get(c) or eastmoney_sec_id(c) for c in batch)
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": "2",
            "invt": "2",
            "fields": "f12,f14,f2,f3",
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
            quotes[code] = {
                "price": float(price),
                "change_pct": change_pct,
                "name": str(item.get("f14") or "").strip(),
            }
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
