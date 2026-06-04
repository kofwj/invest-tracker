import json as pyjson
import logging
import sqlite3
import urllib.request
from datetime import date as dt_date, datetime

import akshare as ak
import pandas as pd
import requests

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
                out.append((d, float(row[2])))  # [date, open, close, high, low, volume, ...]
        except Exception:
            pass
    return out


def calculate_trailing_return_1y(code: str, current_price: float = None):
    """Return (pct, source). pct uses price/NAV one-year change; A-share/ETF uses qfq close when available."""
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
                df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"), adjust="qfq")
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


def infer_category(code: str, name: str = ""):
    c = str(code or "").strip().lower()
    n = str(name or "")
    if c.startswith("f"):
        return "债基"
    if c == "513530":
        return "港股ETF"
    if c == "518880":
        return "黄金"
    if c.startswith("508") or "REIT" in n.upper():
        return "REITs"
    if c.startswith("159") or c.startswith("51"):
        return "A股ETF"
    if any(k in n for k in ["短债", "债", "丰享"]):
        return "债基"
    if "黄金" in n:
        return "黄金"
    if any(k in n for k in ["港股", "恒生", "红利ETF"]):
        return "港股ETF"
    if "ETF" in n.upper():
        return "A股ETF"
    if len(c) == 6 and c.isdigit():
        return "A股权益"
    return "其他"


def normalized_transaction_cash(direction, quantity, price, amount, fee):
    """Return cash/cost amount with fee counted exactly once."""
    direction = str(direction or "")
    qty = float(quantity or 0)
    px = float(price or 0)
    amt = float(amount or 0)
    f = float(fee or 0)
    gross = qty * px if qty > 0 and px > 0 else 0.0
    tol = max(0.05, abs(gross) * 0.00002)

    if direction in ("买入", "申购待确认", "待确认申购"):
        if gross > 0:
            if abs(amt - (gross + f)) <= tol:
                return amt
            if abs(amt - gross) <= tol:
                return amt + f
        return amt

    if direction == "卖出":
        if gross > 0:
            if abs(amt - (gross - f)) <= tol:
                return amt
            if abs(amt - gross) <= tol:
                return amt - f
        return amt

    if direction == "分红":
        return amt - f

    if direction == "分红再投资":
        # Dividend amount is immediately reinvested. Treat amount as reinvested principal;
        # any fee is the only extra cash/cost component.
        if gross > 0:
            if abs(amt - (gross + f)) <= tol:
                return amt
            if abs(amt - gross) <= tol:
                return amt + f
        return amt + f

    return amt


def latest_holding_corrections(conn):
    """Return latest forced correction per code. Latest id wins when dates tie."""
    try:
        rows = conn.execute("""
            SELECT hc.* FROM holding_corrections hc
            JOIN (
                SELECT code, MAX(date || '|' || printf('%012d', id)) AS marker
                FROM holding_corrections
                GROUP BY code
            ) x ON x.code = hc.code AND x.marker = (hc.date || '|' || printf('%012d', hc.id))
        """).fetchall()
        return {str(r["code"]).strip(): dict(r) for r in rows}
    except sqlite3.OperationalError:
        return {}


def recalc_holdings(conn):
    """Recalculate holdings from transactions, then apply latest forced correction anchors."""
    conn.row_factory = sqlite3.Row
    old_holdings = {r["code"]: dict(r) for r in conn.execute("SELECT * FROM holdings").fetchall()}
    corrections = latest_holding_corrections(conn)
    txs = conn.execute("""
        SELECT * FROM transactions
        WHERE code IS NOT NULL AND TRIM(code) != ''
        ORDER BY date, id
    """).fetchall()
    state = {}

    def init_state(code, name='', category='', old=None):
        old = old or old_holdings.get(code, {})
        if code not in state:
            state[code] = {
                "name": old.get("name") or name or code,
                "category": old.get("category") or category or infer_category(code, name),
                "quantity": 0.0,
                "cost": 0.0,
                "net_invested": 0.0,
                "dividend": 0.0,
                "last_price": old.get("last_price") or 0.0,
                "expected_return": old.get("expected_return") if old.get("expected_return") is not None else 0.0,
                "anchor_date": None,
                "corrected": False,
            }
        return state[code]

    for code, c in corrections.items():
        old = old_holdings.get(code, {})
        name = c.get("name") or old.get("name") or code
        category = c.get("category") or old.get("category") or infer_category(code, name)
        s = init_state(code, name, category, old)
        qty = float(c.get("actual_quantity") or 0)
        avg = float(c.get("actual_avg_cost") or 0)
        div = float(c.get("actual_total_dividend") or 0)
        s.update({
            "name": name,
            "category": category,
            "quantity": qty,
            "cost": qty * avg,
            "net_invested": qty * avg - div,
            "dividend": div,
            "anchor_date": str(c.get("date") or ''),
            "corrected": True,
        })

    for t in txs:
        code = str(t["code"]).strip()
        if t["direction"] in ("申购待确认", "待确认申购"):
            continue
        old = old_holdings.get(code, {})
        correction = corrections.get(code)
        if correction and str(t["date"] or '') <= str(correction.get("date") or ''):
            continue
        s = init_state(code, t["name"] or code, t["category"] or '', old)
        if t["category"] and not s.get("corrected"):
            s["category"] = t["category"]
        if t["name"] and not s.get("corrected"):
            s["name"] = s["name"] or t["name"]
        if not s.get("last_price") and t["price"]:
            s["last_price"] = t["price"]
        qty = float(t["quantity"] or 0)
        amount = float(t["amount"] or 0)
        fee = float(t["fee"] or 0)
        cash_amount = normalized_transaction_cash(t["direction"], qty, t["price"], amount, fee)
        if t["direction"] == "买入":
            s["quantity"] += qty
            s["cost"] += cash_amount
            s["net_invested"] += cash_amount
        elif t["direction"] == "分红再投资":
            # One row represents dividend received + immediate purchase.
            # amount is dividend/reinvested principal; fee, if any, is an extra out-of-pocket cash cost.
            reinvest_cost = cash_amount
            dividend_amount = amount
            s["quantity"] += qty
            s["cost"] += reinvest_cost
            s["net_invested"] += reinvest_cost - dividend_amount
            s["dividend"] += dividend_amount
        elif t["direction"] == "卖出":
            if s["quantity"] > 0 and qty > 0:
                s["cost"] -= (s["cost"] / s["quantity"]) * qty
            s["net_invested"] -= cash_amount
            s["quantity"] = max(0.0, s["quantity"] - qty)
            if s["quantity"] == 0:
                s["cost"] = 0.0
                s["net_invested"] = 0.0
        elif t["direction"] == "分红":
            s["dividend"] += cash_amount
            s["net_invested"] -= cash_amount

    active_codes = set(state.keys())
    for code in old_holdings.keys():
        if code not in active_codes:
            conn.execute("DELETE FROM holdings WHERE code = ?", (code,))

    now = datetime.now()
    for code, s in state.items():
        old = old_holdings.get(code, {})
        if code == "513530" and not s.get("corrected"):
            name, category = "港股通红利ETF", "港股ETF"
        elif code == "518880" and not s.get("corrected"):
            name, category = "黄金ETF华安", "黄金"
        elif code == "508056" and not s.get("corrected"):
            name, category = "中金普洛斯REIT", "REITs"
        else:
            name = s["name"] or old.get("name") or code
            category = s["category"] or old.get("category") or infer_category(code, name)
        avg_cost = s["cost"] / s["quantity"] if s["quantity"] > 0 else 0.0
        diluted_cost = s["net_invested"] / s["quantity"] if s["quantity"] > 0 else 0.0
        conn.execute("""
            INSERT INTO holdings (code, name, quantity, avg_cost, diluted_cost, total_dividend, last_price, updated_at, category, expected_return)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                name=excluded.name, quantity=excluded.quantity, avg_cost=excluded.avg_cost,
                diluted_cost=excluded.diluted_cost, total_dividend=excluded.total_dividend,
                last_price=excluded.last_price, updated_at=excluded.updated_at,
                category=excluded.category, expected_return=excluded.expected_return
        """, (code, name, s["quantity"], avg_cost, diluted_cost, s["dividend"], old.get("last_price") or s["last_price"], now, category, s["expected_return"]))


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
