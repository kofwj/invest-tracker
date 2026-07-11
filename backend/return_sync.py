import json as pyjson
import logging
import urllib.request
from datetime import date as dt_date

logger = logging.getLogger(__name__)


def ensure_holding_return_columns(conn):
    """Add cached trailing-return columns for holdings if missing."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(holdings)").fetchall()]
    if "trailing_return_1y" not in cols:
        conn.execute("ALTER TABLE holdings ADD COLUMN trailing_return_1y REAL")
    if "trailing_return_1y_source" not in cols:
        conn.execute("ALTER TABLE holdings ADD COLUMN trailing_return_1y_source TEXT")
    if "trailing_return_1y_updated_at" not in cols:
        conn.execute("ALTER TABLE holdings ADD COLUMN trailing_return_1y_updated_at DATETIME")


def nearest_numeric_value(df, date_col_candidates, value_col_candidates, target_date, direction="before"):
    """Pick nearest numeric historical value on/before or on/after target_date."""
    import pandas as pd  # lazy

    if df is None or df.empty:
        return None, None
    date_col = next((c for c in date_col_candidates if c in df.columns), None)
    value_col = next((c for c in value_col_candidates if c in df.columns), None)
    if not date_col or not value_col:
        return None, None
    tmp = df[[date_col, value_col]].copy()
    tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
    tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
    tmp = tmp.dropna().sort_values(date_col)
    if tmp.empty:
        return None, None
    target = pd.to_datetime(target_date)
    if direction == "before":
        cand = tmp[tmp[date_col] <= target]
        if cand.empty:
            cand = tmp[tmp[date_col] >= target]
            if cand.empty:
                return None, None
            row = cand.iloc[0]
        else:
            row = cand.iloc[-1]
    else:
        cand = tmp[tmp[date_col] >= target]
        if cand.empty:
            cand = tmp[tmp[date_col] <= target]
            if cand.empty:
                return None, None
            row = cand.iloc[-1]
        else:
            row = cand.iloc[0]
    return float(row[value_col]), row[date_col].date().isoformat()


def market_prefix(code: str):
    c = str(code or "").strip().lower().replace("f", "")
    return "sh" if c.startswith(("5", "6", "9")) else "sz"


def fetch_tencent_kline_closes(code: str, start: dt_date, end: dt_date):
    """Fetch qfq daily closes from Tencent quote API. Returns [(date, close)]."""
    c = str(code or "").strip().lower().replace("f", "")
    symbol = market_prefix(c) + c
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,420,qfq"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    data = pyjson.loads(raw).get("data", {}).get(symbol, {})
    rows = data.get("qfqday") or data.get("day") or []
    out = []
    for row in rows:
        try:
            d = str(row[0])
            if d >= start.isoformat() and d <= end.isoformat():
                out.append((d, float(row[2])))
        except Exception:
            pass
    return out


def calculate_trailing_return_1y(code: str, current_price: float = None):
    """Return (pct, source). pct uses price/NAV one-year change; A-share/ETF uses qfq close when available."""
    import akshare as ak  # lazy: not required for app boot / unit tests

    c = str(code or "").strip().lower()
    end = dt_date.today()
    start = end.replace(year=end.year - 1)
    try:
        if c.startswith("f"):
            fund_code = c.replace("f", "")
            try:
                df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累计净值走势")
                value_cols = ["累计净值", "净值"]
                source_name = "天天基金累计净值"
            except Exception:
                df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
                value_cols = ["单位净值", "净值"]
                source_name = "天天基金单位净值"
            start_val, start_date = nearest_numeric_value(df, ["净值日期", "日期", "date"], value_cols, start, "before")
            end_val, end_date = nearest_numeric_value(df, ["净值日期", "日期", "date"], value_cols, end, "before")
        else:
            symbol = c.replace("f", "")
            try:
                klines = fetch_tencent_kline_closes(symbol, start, end)
                if klines:
                    start_date, start_val = klines[0]
                    end_date, end_val = klines[-1]
                    source_name = "腾讯前复权K线"
                else:
                    start_val = end_val = start_date = end_date = None
                    source_name = "腾讯前复权K线"
            except Exception:
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust="qfq",
                )
                start_val, start_date = nearest_numeric_value(df, ["日期"], ["收盘"], start, "after")
                end_val, end_date = nearest_numeric_value(df, ["日期"], ["收盘"], end, "before")
                source_name = "AKShare前复权收盘"
            if (not end_val or end_val <= 0) and current_price:
                end_val = float(current_price)
                end_date = end.isoformat()
        if not start_val or start_val <= 0 or not end_val or end_val <= 0:
            return None, "暂无足够历史数据"
        pct = (float(end_val) / float(start_val) - 1) * 100
        return round(pct, 4), f"{source_name}：{start_date}→{end_date}"
    except Exception as e:
        logger.warning(f"Trailing return failed for {code}: {e}")
        return None, f"计算失败：{e}"
