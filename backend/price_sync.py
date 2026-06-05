import akshare as ak
import requests


def eastmoney_sec_id(code: str) -> str:
    """Eastmoney secid: A股/深市ETF=0.xxx，上市沪市股票/ETF/REIT=1.xxx。"""
    c = str(code or "").strip().lower().replace("f", "")
    if c.startswith(("6", "5")):
        return f"1.{c}"
    return f"0.{c}"


def fetch_eastmoney_prices(codes):
    numeric_codes = [str(c).strip().lower().replace("f", "") for c in codes if str(c).strip().lower().replace("f", "").isdigit() and len(str(c).strip().lower().replace("f", "")) == 6]
    if not numeric_codes:
        return {}
    prices = {}
    for i in range(0, len(numeric_codes), 40):
        batch = numeric_codes[i:i + 40]
        secids = ",".join(eastmoney_sec_id(c) for c in batch)
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": "2",
            "invt": "2",
            "fields": "f12,f14,f2",
            "secids": secids,
        }
        res = requests.get(url, params=params, timeout=8, headers={"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"})
        res.raise_for_status()
        data = res.json().get("data") or {}
        for item in data.get("diff") or []:
            code = str(item.get("f12") or "").strip()
            price = item.get("f2")
            if code and price not in (None, "-"):
                prices[code] = float(price)
    return prices


def fetch_open_fund_nav(code: str):
    fund_code = str(code or "").strip().lower().replace("f", "")
    df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
    if df is None or df.empty:
        return None
    return float(df.iloc[-1]["单位净值"])
