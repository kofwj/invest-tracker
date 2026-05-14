from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import date as dt_date, datetime
import sqlite3
import pandas as pd
import akshare as ak
import os
import logging
import requests
import urllib.request
import json as pyjson
import math
import csv
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Investment Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "/Users/jian/invest-tracker/data/invest.db"

class TransactionBase(BaseModel):
    date: dt_date
    code: str
    name: str
    category: Optional[str] = None
    account: Optional[str] = None
    direction: str
    quantity: float
    price: float
    amount: float
    fee: float = 0.0
    remark: Optional[str] = None

class HoldingSchema(BaseModel):
    code: str
    name: str
    category: Optional[str] = None
    quantity: float
    avg_cost: float
    diluted_cost: float
    total_dividend: float
    last_price: float
    updated_at: datetime
    expected_return: Optional[float] = 0.0
    trailing_return_1y: Optional[float] = None
    trailing_return_1y_source: Optional[str] = None
    trailing_return_1y_updated_at: Optional[datetime] = None

class HoldingCorrectionBase(BaseModel):
    date: dt_date
    code: str
    name: Optional[str] = None
    category: Optional[str] = None
    actual_quantity: float
    actual_avg_cost: float
    actual_total_dividend: Optional[float] = 0.0
    remark: Optional[str] = None

class HoldingCorrectionUpdate(BaseModel):
    date: Optional[dt_date] = None
    name: Optional[str] = None
    category: Optional[str] = None
    actual_quantity: Optional[float] = None
    actual_avg_cost: Optional[float] = None
    actual_total_dividend: Optional[float] = None
    remark: Optional[str] = None

class DepositSchema(BaseModel):
    id: Optional[int] = None
    bank_name: str
    amount: float
    interest_rate: Optional[float] = None
    due_date: Optional[str] = None
    remark: Optional[str] = None

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




TRANSACTION_CSV_COLUMNS = ["date", "account", "code", "name", "category", "direction", "quantity", "price", "amount", "fee", "remark"]
DEPOSIT_CSV_COLUMNS = ["bank_name", "amount", "interest_rate", "due_date", "remark"]

TRANSACTION_CSV_HEADERS_CN = ["日期", "证券账户", "代码", "名称", "分类", "方向", "数量", "价格", "金额", "手续费", "备注"]
DEPOSIT_CSV_HEADERS_CN = ["银行", "金额", "年利率", "到期日", "备注"]

TRANSACTION_HEADER_ALIASES = {
    "date": "date", "日期": "date",
    "account": "account", "证券账户": "account", "账户": "account",
    "code": "code", "代码": "code",
    "name": "name", "名称": "name",
    "category": "category", "分类": "category",
    "direction": "direction", "方向": "direction",
    "quantity": "quantity", "数量": "quantity", "份额": "quantity",
    "price": "price", "价格": "price", "单价": "price", "净值": "price",
    "amount": "amount", "金额": "amount", "总金额": "amount",
    "fee": "fee", "手续费": "fee", "费用": "fee",
    "remark": "remark", "备注": "remark",
}

DEPOSIT_HEADER_ALIASES = {
    "bank_name": "bank_name", "银行": "bank_name", "银行名称": "bank_name",
    "amount": "amount", "金额": "amount", "本金": "amount",
    "interest_rate": "interest_rate", "年利率": "interest_rate", "利率": "interest_rate",
    "due_date": "due_date", "到期日": "due_date", "到期时间": "due_date",
    "remark": "remark", "备注": "remark",
}


def csv_response(filename: str, headers, rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    writer.writerows(rows)
    content = "\ufeff" + out.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def parse_float(value, default=0.0):
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "").replace("¥", "").strip())
    except Exception:
        raise ValueError(f"不是有效数字：{value}")


def normalize_date_string(value, required=True):
    v = str(value or "").strip()
    if not v:
        if required:
            raise ValueError("日期不能为空")
        return ""
    try:
        return dt_date.fromisoformat(v).isoformat()
    except Exception:
        raise ValueError(f"日期格式应为 YYYY-MM-DD：{v}")


def normalize_csv_row(raw_row, aliases):
    row = {}
    for key, value in (raw_row or {}).items():
        normalized_key = aliases.get(str(key or "").strip())
        if normalized_key:
            row[normalized_key] = str(value or "").strip()
    return row


def read_upload_csv(content: bytes):
    text = content.decode("utf-8-sig", errors="ignore")
    sample = text[:2048]
    dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return list(reader)


def create_import_backup(label: str):
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(DB_PATH)), "backups"), exist_ok=True)
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(DB_PATH)), "backups")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"invest_{ts}_{label}.db.bak")
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(backup_path)
    with dst:
        src.backup(dst)
    src.close()
    ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
    dst.close()
    if ok != "ok":
        raise HTTPException(status_code=500, detail=f"导入前备份完整性检查失败：{ok}")
    return backup_path


@app.get("/holdings", response_model=List[HoldingSchema])
def list_holdings():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        ensure_holding_return_columns(conn)
        conn.commit()
        rows = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Holdings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/deposits", response_model=List[DepositSchema])
def list_deposits():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM deposits").fetchall()
    conn.close()
    return [dict(row) for row in rows]

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
    """Return cash/cost amount with fee counted exactly once.

    Historical transaction rows are mixed: some `amount` values are gross成交额
    (quantity*price), while others already include buy fee or are sell net proceeds.
    Use quantity/price/fee to infer the row semantics and avoid double-counting fees.
    """
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
    """Recalculate holdings from transactions, then apply latest forced correction anchors.

    For each code: current holding = latest correction point + transactions after correction date.
    This keeps auditability: history is untouched; broker-verified correction becomes the new anchor.
    """
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
                # ordinary_cost: remaining confirmed holding cost after average-cost sell-out.
                # net_invested: broker-style remaining cash basis = cumulative buy cash - sell proceeds - dividends.
                # diluted_cost is derived from net_invested / remaining quantity, so large sell proceeds/dividends can make it negative.
                "cost": 0.0,
                "net_invested": 0.0,
                "dividend": 0.0,
                "last_price": old.get("last_price") or 0.0,
                "expected_return": old.get("expected_return") if old.get("expected_return") is not None else 0.0,
                "anchor_date": None,
                "corrected": False,
            }
        return state[code]

    # Apply latest correction anchors first. Transactions on/before correction date are ignored later.
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
            # 申购在途只有金额、无确认份额/净值：计入dashboard总资产，但不进入正式持仓份额/成本/盈亏。
            continue
        old = old_holdings.get(code, {})
        correction = corrections.get(code)
        if correction and str(t["date"] or '') <= str(correction.get("date") or ''):
            # Latest correction is an end-of-day anchor; previous/same-day txs are already reflected in broker value.
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
        # Broker-style diluted cost: remaining cash basis after ALL cash recovered from sells and dividends.
        # Example: ABC can become negative after sell proceeds + dividends exceed total historical buys.
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




@app.get("/transactions/template")
def download_transactions_template():
    rows = [
        [dt_date.today().isoformat(), "华泰证券", "601288", "农业银行", "A股权益", "买入", "1000", "6.00", "6000.00", "5.00", "示例：请删除后填写真实交易"],
        [dt_date.today().isoformat(), "华泰证券", "f004388", "鹏华丰享", "债基", "申购待确认", "0", "0", "50000.00", "0.00", "场外基金份额未确认时使用"],
    ]
    return csv_response("transactions_template.csv", TRANSACTION_CSV_COLUMNS, rows)

@app.get("/transactions/export")
def export_transactions():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT date, COALESCE(account, '华泰证券') AS account, code, name, category, direction, quantity, price, amount, fee, remark
        FROM transactions
        ORDER BY date DESC, id DESC
    """).fetchall()
    conn.close()
    data = [[r[k] for k in TRANSACTION_CSV_COLUMNS] for r in rows]
    return csv_response(f"transactions_{dt_date.today().isoformat()}.csv", TRANSACTION_CSV_COLUMNS, data)

@app.post("/transactions/import")
async def import_transactions(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="目前仅支持 CSV 文件")
    raw_rows = read_upload_csv(await file.read())
    if not raw_rows:
        raise HTTPException(status_code=400, detail="CSV为空")
    backup_path = create_import_backup("before_import_transactions")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cols = [row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if "category" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN category TEXT")
    if "account" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN account TEXT")
    success = 0
    errors = []
    allowed_directions = {"买入", "卖出", "分红", "申购待确认", "待确认申购"}
    try:
        for idx, raw in enumerate(raw_rows, start=2):
            try:
                row = normalize_csv_row(raw, TRANSACTION_HEADER_ALIASES)
                date_str = normalize_date_string(row.get("date"))
                code = str(row.get("code") or "").strip()
                name = str(row.get("name") or "").strip()
                direction = str(row.get("direction") or "").strip()
                if not code:
                    raise ValueError("代码不能为空")
                if not name:
                    raise ValueError("名称不能为空")
                if direction not in allowed_directions:
                    raise ValueError("方向必须是：买入/卖出/分红/申购待确认")
                category = row.get("category") or infer_category(code, name)
                account = row.get("account") or "华泰证券"
                quantity = parse_float(row.get("quantity"), 0.0)
                price = parse_float(row.get("price"), 0.0)
                amount = parse_float(row.get("amount"), 0.0)
                fee = parse_float(row.get("fee"), 0.0)
                remark = row.get("remark") or ""
                if amount < 0:
                    raise ValueError("金额不能为负；买卖方向通过direction表示")
                conn.execute("""
                    INSERT INTO transactions (date, code, name, category, account, direction, quantity, price, amount, fee, remark)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (date_str, code, name, category, account, direction, quantity, price, amount, fee, remark))
                success += 1
            except Exception as e:
                errors.append({"row": idx, "error": str(e)})
        if success:
            recalc_holdings(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"status": "success", "imported": success, "failed": len(errors), "errors": errors[:50], "backup": backup_path}

@app.get("/deposits/template")
def download_deposits_template():
    rows = [["招商银行", "100000.00", "1.80", "2026-12-31", "示例：请删除后填写真实存款"]]
    return csv_response("deposits_template.csv", DEPOSIT_CSV_COLUMNS, rows)

@app.get("/deposits/export")
def export_deposits():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT bank_name, amount, interest_rate, due_date, remark
        FROM deposits
        ORDER BY COALESCE(due_date, '9999-12-31'), id
    """).fetchall()
    conn.close()
    data = [[r[k] for k in DEPOSIT_CSV_COLUMNS] for r in rows]
    return csv_response(f"deposits_{dt_date.today().isoformat()}.csv", DEPOSIT_CSV_COLUMNS, data)

@app.post("/deposits/import")
async def import_deposits(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="目前仅支持 CSV 文件")
    raw_rows = read_upload_csv(await file.read())
    if not raw_rows:
        raise HTTPException(status_code=400, detail="CSV为空")
    backup_path = create_import_backup("before_import_deposits")
    conn = sqlite3.connect(DB_PATH)
    success = 0
    errors = []
    try:
        for idx, raw in enumerate(raw_rows, start=2):
            try:
                row = normalize_csv_row(raw, DEPOSIT_HEADER_ALIASES)
                bank_name = str(row.get("bank_name") or "").strip()
                if not bank_name:
                    raise ValueError("银行名称不能为空")
                amount = parse_float(row.get("amount"), 0.0)
                if amount <= 0:
                    raise ValueError("金额必须大于0")
                interest_rate = parse_float(row.get("interest_rate"), 0.0) if row.get("interest_rate") != "" else None
                due_date = normalize_date_string(row.get("due_date"), required=False) or None
                remark = row.get("remark") or ""
                conn.execute("""
                    INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark)
                    VALUES (?, ?, ?, ?, ?)
                """, (bank_name, amount, interest_rate, due_date, remark))
                success += 1
            except Exception as e:
                errors.append({"row": idx, "error": str(e)})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"status": "success", "imported": success, "failed": len(errors), "errors": errors[:50], "backup": backup_path}


@app.post("/deposits")
def add_deposit(dep: DepositSchema):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark)
        VALUES (?, ?, ?, ?, ?)
    """, (dep.bank_name, dep.amount, dep.interest_rate, dep.due_date, dep.remark))
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "success", "id": new_id}

class DepositUpdate(BaseModel):
    bank_name: Optional[str] = None
    amount: Optional[float] = None
    interest_rate: Optional[float] = None
    due_date: Optional[str] = None
    remark: Optional[str] = None

@app.put("/deposits/{deposit_id}")
def update_deposit(deposit_id: int, dep: DepositUpdate):
    conn = sqlite3.connect(DB_PATH)
    updates = []
    vals = []
    for field in ["bank_name", "amount", "interest_rate", "due_date", "remark"]:
        v = getattr(dep, field)
        if v is not None:
            updates.append(f"{field} = ?")
            vals.append(v)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    vals.append(deposit_id)
    conn.execute(f"UPDATE deposits SET {', '.join(updates)} WHERE id = ?", vals)
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Deposit not found")
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/deposits/{deposit_id}")
def delete_deposit(deposit_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM deposits WHERE id = ?", (deposit_id,))
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Deposit not found")
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/transactions")
def list_transactions(code: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    if code:
        rows = conn.execute("SELECT * FROM transactions WHERE code = ? ORDER BY date DESC", (code,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM transactions ORDER BY date DESC LIMIT 100").fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/transactions")
def add_transaction(trans: TransactionBase):
    conn = sqlite3.connect(DB_PATH)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if "category" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN category TEXT")
    if "account" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN account TEXT")
    conn.execute("""
        INSERT INTO transactions (date, code, name, category, account, direction, quantity, price, amount, fee, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (trans.date.isoformat(), trans.code, trans.name, trans.category, trans.account or "华泰证券", trans.direction, trans.quantity, trans.price, trans.amount, trans.fee, trans.remark))
    recalc_holdings(conn)
    conn.commit()
    conn.close()
    return {"status": "success"}

class TransactionUpdate(BaseModel):
    date: Optional[dt_date] = None
    code: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    account: Optional[str] = None
    direction: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    fee: Optional[float] = None
    remark: Optional[str] = None

@app.put("/transactions/{transaction_id}")
def update_transaction(transaction_id: int, trans: TransactionUpdate):
    conn = sqlite3.connect(DB_PATH)
    updates = []
    vals = []
    
    cols = [row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if "category" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN category TEXT")
    if "account" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN account TEXT")

    for field in ["date", "code", "name", "category", "account", "direction", "quantity", "price", "amount", "fee", "remark"]:
        v = getattr(trans, field)
        if v is not None:
            if field == "date":
                updates.append(f"{field} = ?")
                vals.append(v.isoformat())
            else:
                updates.append(f"{field} = ?")
                vals.append(v)
    
    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")
    
    vals.append(transaction_id)
    conn.execute(f"UPDATE transactions SET {', '.join(updates)} WHERE id = ?", vals)
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")
    recalc_holdings(conn)
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")
    recalc_holdings(conn)
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/holding-corrections")
def list_holding_corrections(code: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_settings_table()
    params = []
    query = "SELECT * FROM holding_corrections"
    if code:
        query += " WHERE code = ?"
        params.append(code)
    query += " ORDER BY date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/holding-corrections")
def add_holding_correction(data: HoldingCorrectionBase):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_settings_table()
    conn.execute("""
        INSERT INTO holding_corrections (date, code, name, category, actual_quantity, actual_avg_cost, actual_total_dividend, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (data.date.isoformat(), data.code.strip(), data.name, data.category, data.actual_quantity, data.actual_avg_cost, data.actual_total_dividend or 0, data.remark))
    recalc_holdings(conn)
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "success", "id": new_id}

@app.put("/holding-corrections/{correction_id}")
def update_holding_correction(correction_id: int, data: HoldingCorrectionUpdate):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_settings_table()
    updates = []
    vals = []
    for field in ["date", "name", "category", "actual_quantity", "actual_avg_cost", "actual_total_dividend", "remark"]:
        v = getattr(data, field)
        if v is not None:
            updates.append(f"{field} = ?")
            vals.append(v.isoformat() if field == "date" else v)
    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")
    vals.append(correction_id)
    conn.execute(f"UPDATE holding_corrections SET {', '.join(updates)} WHERE id = ?", vals)
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Correction not found")
    recalc_holdings(conn)
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/holding-corrections/{correction_id}")
def delete_holding_correction(correction_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_settings_table()
    conn.execute("DELETE FROM holding_corrections WHERE id = ?", (correction_id,))
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Correction not found")
    recalc_holdings(conn)
    conn.commit()
    conn.close()
    return {"status": "success"}

class HoldingUpdate(BaseModel):
    expected_return: Optional[float] = None

@app.put("/holdings/{code}")
def update_holding(code: str, holding: HoldingUpdate):
    if holding.expected_return is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE holdings SET expected_return = ? WHERE code = ?", 
                 (holding.expected_return, code))
    conn.commit()
    conn.close()
    return {"status": "success"}

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
    # 一次最多几十个足够，本项目持仓很少；分批避免URL过长
    for i in range(0, len(numeric_codes), 40):
        batch = numeric_codes[i:i + 40]
        secids = ",".join(eastmoney_sec_id(c) for c in batch)
        # push2 在当前网络下偶发 RemoteDisconnected；push2delay 更稳定，足够用于手动刷新持仓最新价
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


@app.get("/sync-trailing-returns")
def sync_trailing_returns():
    """同步当前持仓近一年标的收益率。该收益率是标的自身价格/净值回溯，不等于账户实际持有收益。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_holding_return_columns(conn)
    rows = conn.execute("SELECT code, name, last_price FROM holdings WHERE quantity > 0").fetchall()
    updated = 0
    failed = []
    details = []
    now = datetime.now()
    for row in rows:
        code = str(row["code"]).strip()
        pct, source = calculate_trailing_return_1y(code, row["last_price"])
        if pct is None:
            failed.append({"code": code, "name": row["name"], "reason": source})
        else:
            updated += 1
        conn.execute("""
            UPDATE holdings
            SET trailing_return_1y = ?, trailing_return_1y_source = ?, trailing_return_1y_updated_at = ?
            WHERE code = ?
        """, (pct, source, now, code))
        details.append({"code": code, "name": row["name"], "trailing_return_1y": pct, "source": source})
    conn.commit()
    conn.close()
    return {"status": "success", "checked": len(rows), "updated": updated, "failed": failed, "details": details}


@app.get("/sync-prices")
def sync_prices():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT code, name, last_price FROM holdings WHERE quantity > 0").fetchall()
    updated = 0
    unchanged = 0
    failed = []
    details = []
    now = datetime.now()

    codes = [row["code"] for row in rows]
    em_prices = {}
    try:
        em_prices = fetch_eastmoney_prices(codes)
    except Exception as e:
        logger.error(f"Eastmoney batch price sync failed: {e}")

    for row in rows:
        code = str(row["code"]).strip()
        lookup_code = code.lower().replace("f", "")
        old_price = float(row["last_price"] or 0)
        price = None
        source = ""
        try:
            if code.lower().startswith("f"):
                price = fetch_open_fund_nav(code)
                source = "天天基金净值"
            else:
                price = em_prices.get(lookup_code)
                source = "东方财富行情"

            if price is None or price <= 0:
                failed.append({"code": code, "name": row["name"], "reason": "未取到有效价格"})
                continue

            conn.execute("UPDATE holdings SET last_price = ?, updated_at = ? WHERE code = ?", (float(price), now, code))
            if abs(price - old_price) >= 1e-8:
                updated += 1
            else:
                unchanged += 1
            details.append({"code": code, "name": row["name"], "old_price": old_price, "new_price": float(price), "source": source})
        except Exception as e:
            logger.error(f"Error syncing {code}: {e}")
            failed.append({"code": code, "name": row["name"], "reason": str(e)})

    conn.commit()
    conn.close()
    return {"status": "success", "updated": updated, "unchanged": unchanged, "failed": failed, "details": details, "checked": len(rows)}

def transaction_cash_flow(conn):
    """交易对证券现金的自动影响：买入/申购待确认扣现金，卖出/分红加现金。

    Uses normalized_transaction_cash() because historical amount rows are mixed
    between gross and fee-inclusive/net amounts.
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT direction, quantity, price, amount, fee FROM transactions").fetchall()
    total = 0.0
    for r in rows:
        direction = r["direction"]
        cash = normalized_transaction_cash(direction, r["quantity"], r["price"], r["amount"], r["fee"])
        if direction in ("买入", "申购待确认", "待确认申购"):
            total -= cash
        elif direction in ("卖出", "分红"):
            total += cash
    return float(total)


def normalize_cash_flow_amount(flow_type, amount):
    """资金流水金额符号：转入为正，转出为负，校准/其他按传入差额。"""
    amt = float(amount or 0)
    if flow_type == '银证转入':
        return abs(amt)
    if flow_type == '银证转出':
        return -abs(amt)
    return amt


def cash_flow_adjustment(conn):
    """银证转入/转出/现金校准等非交易资金流水合计。"""
    try:
        row = conn.execute("SELECT SUM(COALESCE(amount, 0)) AS total FROM cash_flows").fetchone()
        return float((row['total'] if isinstance(row, sqlite3.Row) else row[0]) or 0)
    except sqlite3.OperationalError:
        return 0.0


def get_setting_float(conn, key, default=0.0):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        value = row["value"] if isinstance(row, sqlite3.Row) else row[0]
        return float(value)
    except Exception:
        return default


def set_setting(conn, key, value):
    conn.execute("""
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))


def ensure_cash_base(conn):
    """一次性把旧的 securities_cash 迁移为手动现金基准。

    历史买入/卖出/分红交易已经反映在旧现金余额里，所以迁移时保留旧现金口径；
    但“申购待确认”会作为 pending_purchase 另计入总资产，因此必须从证券现金中扣掉，
    避免出现“现金没少 + 在途又加一次”的重复计算。
    """
    base_row = conn.execute("SELECT value FROM settings WHERE key='securities_cash_base'").fetchone()
    if base_row:
        return
    displayed_cash = get_setting_float(conn, "securities_cash", 0.0)
    flow = transaction_cash_flow(conn)
    pending_row = conn.execute("""
        SELECT SUM(COALESCE(amount, 0) + COALESCE(fee, 0)) as total
        FROM transactions
        WHERE direction IN ('申购待确认', '待确认申购')
    """).fetchone()
    pending = float((pending_row["total"] if isinstance(pending_row, sqlite3.Row) else pending_row[0]) or 0)
    # 迁移后：calculated_cash = displayed_cash - pending
    set_setting(conn, "securities_cash_base", displayed_cash - pending - flow)


def calculated_securities_cash(conn):
    ensure_cash_base(conn)
    base = get_setting_float(conn, "securities_cash_base", 0.0)
    tx_flow = transaction_cash_flow(conn)
    manual_flow = cash_flow_adjustment(conn)
    return base + manual_flow + tx_flow, base, tx_flow


@app.get("/dashboard")
def get_dashboard():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_cash_base(conn)
    holdings = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
    deposits = conn.execute("SELECT SUM(amount) as total FROM deposits").fetchone()
    pending_row = conn.execute("""
        SELECT SUM(amount + COALESCE(fee, 0)) as total
        FROM transactions
        WHERE direction IN ('申购待确认', '待确认申购')
    """).fetchone()
    securities_cash, _, _ = calculated_securities_cash(conn)
    conn.commit()
    conn.close()
    
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
        "holdings_count": len(holdings)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# === 新增：证券现金管理 ===
import json

def ensure_settings_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cash_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        account TEXT DEFAULT '华泰证券',
        flow_type TEXT,
        amount REAL,
        balance_before REAL,
        balance_after REAL,
        remark TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE UNIQUE,
        total_assets REAL,
        total_market_value REAL,
        bank_balance REAL,
        securities_cash REAL,
        pending_purchase REAL DEFAULT 0,
        total_profit REAL,
        holdings_count INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS holding_corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        code TEXT NOT NULL,
        name TEXT,
        category TEXT,
        actual_quantity REAL NOT NULL,
        actual_avg_cost REAL NOT NULL,
        actual_total_dividend REAL DEFAULT 0,
        remark TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    ensure_snapshot_columns(conn)
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup():
    ensure_settings_table()
    # 初始化/迁移证券现金：securities_cash_base 为手动基准，交易现金流自动联动
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cols = [row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if "account" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN account TEXT")
        conn.execute("UPDATE transactions SET account = '华泰证券' WHERE account IS NULL OR TRIM(account) = ''")
    row = conn.execute("SELECT value FROM settings WHERE key='securities_cash'").fetchone()
    if not row:
        set_setting(conn, 'securities_cash', 0)
    ensure_cash_base(conn)
    # 组合级外部现金流表（用于 XIRR / 收益分析）
    conn.execute("""CREATE TABLE IF NOT EXISTS portfolio_cash_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        flow_type TEXT NOT NULL,
        amount REAL NOT NULL,
        source TEXT,
        remark TEXT,
        created_at DATETIME DEFAULT (datetime('now','localtime'))
    )""")
    conn.commit()
    conn.close()

class SecuritiesCashUpdate(BaseModel):
    amount: float

class CashFlowBase(BaseModel):
    date: dt_date
    account: Optional[str] = None
    flow_type: str
    amount: float
    remark: Optional[str] = None

class CashFlowUpdate(BaseModel):
    date: Optional[dt_date] = None
    account: Optional[str] = None
    flow_type: Optional[str] = None
    amount: Optional[float] = None
    remark: Optional[str] = None

DEFAULT_FEE_RULES = {
    "A股权益": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0005, "transfer_fee_rate": 0.00001, "min_commission": 0.0},
    "A股ETF": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "港股ETF": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "REITs": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "黄金": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "债基": {"commission_rate": 0.0, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "其他": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0}
}
DEFAULT_ACCOUNT = "华泰证券"

class FeeSettingsUpdate(BaseModel):
    accounts: Optional[List[str]] = None
    active_account: Optional[str] = None
    settings: dict

def normalize_fee_rule(rule=None, default=None):
    base = (default or {"commission_rate": 0.0, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0}).copy()
    if isinstance(rule, dict):
        for key in ["commission_rate", "stamp_tax_rate", "transfer_fee_rate", "min_commission"]:
            try:
                base[key] = float(rule.get(key, base.get(key, 0.0)) or 0.0)
            except Exception:
                pass
    return base

def normalize_category_settings(raw=None):
    merged = {k: v.copy() for k, v in DEFAULT_FEE_RULES.items()}
    if isinstance(raw, dict):
        for cat, rule in raw.items():
            merged[cat] = normalize_fee_rule(rule, merged.get(cat))
    return merged

def normalize_fee_settings(raw=None):
    # New format: {accounts: [], active_account: str, settings: {account: {category: rule}}}
    # Important: when `accounts` is explicitly provided, it is the source of truth.
    # Do not resurrect deleted accounts from stale `settings` keys.
    if isinstance(raw, dict) and isinstance(raw.get("settings"), dict):
        explicit_accounts = "accounts" in raw and raw.get("accounts") is not None
        accounts = [str(a).strip() for a in raw.get("accounts", []) if str(a).strip()]
        if not explicit_accounts:
            accounts = [str(a).strip() for a in raw.get("settings", {}).keys() if str(a).strip()]
        accounts = list(dict.fromkeys(accounts))
        if not accounts:
            accounts = [DEFAULT_ACCOUNT]

        settings_by_account = {}
        for acc in accounts:
            rules = raw.get("settings", {}).get(acc, {})
            settings_by_account[acc] = normalize_category_settings(rules)

        active = str(raw.get("active_account") or accounts[0] or DEFAULT_ACCOUNT).strip()
        if active not in accounts:
            active = accounts[0]
        return {"accounts": accounts, "active_account": active, "settings": settings_by_account}

    # Old flat format: {category: rule}; migrate to single default account
    flat = normalize_category_settings(raw if isinstance(raw, dict) else None)
    return {"accounts": [DEFAULT_ACCOUNT], "active_account": DEFAULT_ACCOUNT, "settings": {DEFAULT_ACCOUNT: flat}}

def get_fee_settings_from_conn(conn):
    row = conn.execute("SELECT value FROM settings WHERE key='fee_settings'").fetchone()
    raw = None
    if row:
        try:
            value = row["value"] if isinstance(row, sqlite3.Row) else row[0]
            raw = json.loads(value)
        except Exception:
            raw = None
    return normalize_fee_settings(raw)

@app.get("/fee-settings")
def get_fee_settings():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_settings_table()
    data = get_fee_settings_from_conn(conn)
    conn.close()
    return data

@app.put("/fee-settings")
def update_fee_settings(data: FeeSettingsUpdate):
    conn = sqlite3.connect(DB_PATH)
    ensure_settings_table()
    normalized = normalize_fee_settings({
        "accounts": data.accounts or [],
        "active_account": data.active_account,
        "settings": data.settings
    })
    set_setting(conn, 'fee_settings', json.dumps(normalized, ensure_ascii=False))
    conn.commit()
    conn.close()
    return {"status": "success", **normalized}

@app.post("/fee-settings/reset")
def reset_fee_settings():
    conn = sqlite3.connect(DB_PATH)
    ensure_settings_table()
    normalized = normalize_fee_settings({"accounts": [DEFAULT_ACCOUNT], "active_account": DEFAULT_ACCOUNT, "settings": {DEFAULT_ACCOUNT: DEFAULT_FEE_RULES}})
    set_setting(conn, 'fee_settings', json.dumps(normalized, ensure_ascii=False))
    conn.commit()
    conn.close()
    return {"status": "success", **normalized}

@app.get("/securities-cash")
def get_securities_cash():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    amount, base, flow = calculated_securities_cash(conn)
    manual_flow = cash_flow_adjustment(conn)
    conn.commit()
    conn.close()
    return {"amount": amount, "base_amount": base, "cash_flow_adjustment": manual_flow, "transaction_cash_flow": flow}

@app.put("/securities-cash")
def update_securities_cash(data: SecuritiesCashUpdate):
    """手动设置当前证券现金余额：不覆盖历史，按差额写入一条“现金校准”资金流水。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    current, base, tx_flow = calculated_securities_cash(conn)
    delta = float(data.amount or 0) - current
    if abs(delta) >= 0.005:
        conn.execute("""
            INSERT INTO cash_flows (date, account, flow_type, amount, balance_before, balance_after, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (dt_date.today().isoformat(), DEFAULT_ACCOUNT, '现金校准', delta, current, float(data.amount or 0), '现金设置页手动校准'))
    # 保留旧key为当前显示余额，兼容历史脚本/查询；实际计算以base+资金流水+交易现金流为准。
    set_setting(conn, 'securities_cash', data.amount)
    manual_flow = cash_flow_adjustment(conn)
    conn.commit()
    conn.close()
    return {"status": "success", "amount": data.amount, "base_amount": base, "cash_flow_adjustment": manual_flow, "transaction_cash_flow": tx_flow, "delta": delta}


@app.get("/cash-flows")
def list_cash_flows(start_date: Optional[str] = None, end_date: Optional[str] = None, account: Optional[str] = None, flow_type: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_settings_table()
    query = "SELECT * FROM cash_flows WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if account:
        query += " AND account = ?"
        params.append(account)
    if flow_type:
        query += " AND flow_type = ?"
        params.append(flow_type)
    query += " ORDER BY date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/cash-flows")
def add_cash_flow(flow_data: CashFlowBase):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_settings_table()
    before, _, _ = calculated_securities_cash(conn)
    amount = normalize_cash_flow_amount(flow_data.flow_type, flow_data.amount)
    after = before + amount
    conn.execute("""
        INSERT INTO cash_flows (date, account, flow_type, amount, balance_before, balance_after, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (flow_data.date.isoformat(), flow_data.account or DEFAULT_ACCOUNT, flow_data.flow_type, amount, before, after, flow_data.remark))
    set_setting(conn, 'securities_cash', after)
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "success", "id": new_id, "amount": amount, "balance_before": before, "balance_after": after}

@app.put("/cash-flows/{flow_id}")
def update_cash_flow(flow_id: int, flow_data: CashFlowUpdate):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_settings_table()
    old = conn.execute("SELECT * FROM cash_flows WHERE id = ?", (flow_id,)).fetchone()
    if not old:
        conn.close()
        raise HTTPException(status_code=404, detail="Cash flow not found")
    updates = []
    vals = []
    if flow_data.date is not None:
        updates.append("date = ?")
        vals.append(flow_data.date.isoformat())
    if flow_data.account is not None:
        updates.append("account = ?")
        vals.append(flow_data.account or DEFAULT_ACCOUNT)
    new_type = flow_data.flow_type if flow_data.flow_type is not None else old['flow_type']
    if flow_data.flow_type is not None:
        updates.append("flow_type = ?")
        vals.append(flow_data.flow_type)
    if flow_data.amount is not None:
        updates.append("amount = ?")
        vals.append(normalize_cash_flow_amount(new_type, flow_data.amount))
    if flow_data.remark is not None:
        updates.append("remark = ?")
        vals.append(flow_data.remark)
    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")
    vals.append(flow_id)
    conn.execute(f"UPDATE cash_flows SET {', '.join(updates)} WHERE id = ?", vals)
    amount, _, _ = calculated_securities_cash(conn)
    set_setting(conn, 'securities_cash', amount)
    conn.commit()
    conn.close()
    return {"status": "success", "amount": amount}

@app.delete("/cash-flows/{flow_id}")
def delete_cash_flow(flow_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_settings_table()
    conn.execute("DELETE FROM cash_flows WHERE id = ?", (flow_id,))
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Cash flow not found")
    amount, _, _ = calculated_securities_cash(conn)
    set_setting(conn, 'securities_cash', amount)
    conn.commit()
    conn.close()
    return {"status": "success", "amount": amount}

# === 新增：每日资产快照 ===
class SnapshotSchema(BaseModel):
    date: dt_date
    total_assets: float
    total_market_value: float
    bank_balance: float
    securities_cash: float
    pending_purchase: float = 0.0
    total_profit: float
    holdings_count: int

def ensure_snapshot_columns(conn):
    cols = [row[1] for row in conn.execute("PRAGMA table_info(daily_snapshots)").fetchall()]
    if "pending_purchase" not in cols:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN pending_purchase REAL DEFAULT 0")

@app.post("/snapshots")
def create_snapshot():
    """记录当前资产快照。同一天重复点击时更新当天记录，避免价格/现金变化后仍保留旧数据。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_snapshot_columns(conn)
    
    # 获取当前dashboard数据
    dash = get_dashboard()
    
    today = dt_date.today().isoformat()
    existing = conn.execute("SELECT id FROM daily_snapshots WHERE date = ?", (today,)).fetchone()
    if existing:
        conn.execute("""
            UPDATE daily_snapshots
            SET total_assets = ?, total_market_value = ?, bank_balance = ?, securities_cash = ?,
                pending_purchase = ?, total_profit = ?, holdings_count = ?, created_at = CURRENT_TIMESTAMP
            WHERE date = ?
        """, (
            dash['total_assets'],
            dash['total_market_value'],
            dash['bank_balance'],
            dash['securities_cash'],
            dash.get('pending_purchase', 0),
            dash['total_profit'],
            dash['holdings_count'],
            today
        ))
        snapshot_id = existing['id']
        action = "updated"
    else:
        conn.execute("""
            INSERT INTO daily_snapshots 
            (date, total_assets, total_market_value, bank_balance, securities_cash, pending_purchase, total_profit, holdings_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            today,
            dash['total_assets'],
            dash['total_market_value'],
            dash['bank_balance'],
            dash['securities_cash'],
            dash.get('pending_purchase', 0),
            dash['total_profit'],
            dash['holdings_count']
        ))
        snapshot_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        action = "created"
    conn.commit()
    conn.close()
    return {"status": "success", "action": action, "id": snapshot_id, "date": today, "snapshot": dash}

@app.get("/snapshots")
def list_snapshots(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """获取快照列表，支持日期范围查询"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_snapshot_columns(conn)
    
    query = "SELECT * FROM daily_snapshots"
    params = []
    
    if start_date and end_date:
        query += " WHERE date BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE date >= ?"
        params = [start_date]
    elif end_date:
        query += " WHERE date <= ?"
        params = [end_date]
    
    query += " ORDER BY date DESC"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/snapshots/summary")
def snapshots_summary(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """获取资产变化汇总（首尾对比）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_snapshot_columns(conn)
    
    query = "SELECT * FROM daily_snapshots"
    params = []
    
    if start_date and end_date:
        query += " WHERE date BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE date >= ?"
        params = [start_date]
    elif end_date:
        query += " WHERE date <= ?"
        params = [end_date]
    
    query += " ORDER BY date ASC"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    if len(rows) < 2:
        return {"message": "需要至少两个快照来计算变化", "count": len(rows)}
    
    first = dict(rows[0])
    last = dict(rows[-1])
    
    changes = {
        "period": f"{first['date']} 至 {last['date']}",
        "days": (dt_date.fromisoformat(last['date']) - dt_date.fromisoformat(first['date'])).days,
        "total_assets": {
            "start": first['total_assets'],
            "end": last['total_assets'],
            "change": last['total_assets'] - first['total_assets'],
            "change_pct": (last['total_assets'] / first['total_assets'] - 1) * 100 if first['total_assets'] else 0
        },
        "total_market_value": {
            "start": first['total_market_value'],
            "end": last['total_market_value'],
            "change": last['total_market_value'] - first['total_market_value']
        },
        "bank_balance": {
            "start": first['bank_balance'],
            "end": last['bank_balance'],
            "change": last['bank_balance'] - first['bank_balance']
        },
        "securities_cash": {
            "start": first['securities_cash'],
            "end": last['securities_cash'],
            "change": last['securities_cash'] - first['securities_cash']
        },
        "pending_purchase": {
            "start": first.get('pending_purchase', 0),
            "end": last.get('pending_purchase', 0),
            "change": (last.get('pending_purchase', 0) or 0) - (first.get('pending_purchase', 0) or 0)
        }
    }
    return changes

# === 收益分析 v1：组合外部现金流 + XIRR + 组合收益 ===

class PortfolioCashFlowBase(BaseModel):
    date: dt_date
    flow_type: str
    amount: float
    source: Optional[str] = None
    remark: Optional[str] = None

class PortfolioCashFlowUpdate(BaseModel):
    date: Optional[dt_date] = None
    flow_type: Optional[str] = None
    amount: Optional[float] = None
    source: Optional[str] = None
    remark: Optional[str] = None

def ensure_portfolio_cash_flows_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS portfolio_cash_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        flow_type TEXT NOT NULL,
        amount REAL NOT NULL,
        source TEXT,
        remark TEXT,
        created_at DATETIME DEFAULT (datetime('now','localtime'))
    )""")

@app.get("/portfolio-cash-flows")
def list_portfolio_cash_flows(start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_portfolio_cash_flows_table(conn)
    query = "SELECT * FROM portfolio_cash_flows"
    params = []
    if start_date and end_date:
        query += " WHERE date BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE date >= ?"
        params = [start_date]
    elif end_date:
        query += " WHERE date <= ?"
        params = [end_date]
    query += " ORDER BY date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/portfolio-cash-flows")
def add_portfolio_cash_flow(flow: PortfolioCashFlowBase):
    conn = sqlite3.connect(DB_PATH)
    ensure_portfolio_cash_flows_table(conn)
    conn.execute(
        "INSERT INTO portfolio_cash_flows (date, flow_type, amount, source, remark) VALUES (?,?,?,?,?)",
        (flow.date.isoformat(), flow.flow_type, flow.amount, flow.source, flow.remark)
    )
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.put("/portfolio-cash-flows/{flow_id}")
def update_portfolio_cash_flow(flow_id: int, flow: PortfolioCashFlowUpdate):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_portfolio_cash_flows_table(conn)
    existing = conn.execute("SELECT * FROM portfolio_cash_flows WHERE id=?", (flow_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Flow not found")
    d = flow.date.isoformat() if flow.date else existing["date"]
    t = flow.flow_type if flow.flow_type else existing["flow_type"]
    a = flow.amount if flow.amount is not None else existing["amount"]
    s = flow.source if flow.source is not None else existing["source"]
    r = flow.remark if flow.remark is not None else existing["remark"]
    conn.execute(
        "UPDATE portfolio_cash_flows SET date=?, flow_type=?, amount=?, source=?, remark=? WHERE id=?",
        (d, t, a, s, r, flow_id)
    )
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/portfolio-cash-flows/{flow_id}")
def delete_portfolio_cash_flow(flow_id: int):
    conn = sqlite3.connect(DB_PATH)
    ensure_portfolio_cash_flows_table(conn)
    conn.execute("DELETE FROM portfolio_cash_flows WHERE id=?", (flow_id,))
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Flow not found")
    conn.commit()
    conn.close()
    return {"status": "success"}


# --- XIRR 计算 ---

def _xnpv(rate, cashflows):
    if not cashflows:
        return None
    t0 = cashflows[0][0]
    return sum(cf / (1.0 + rate) ** ((d - t0).days / 365.25) for d, cf in cashflows)

def calculate_xirr(cashflows, guess=0.05, tol=1e-7, max_iter=1000):
    if len(cashflows) < 2:
        return None, "insufficient", "现金流不足2笔"
    has_neg = any(cf[1] < 0 for cf in cashflows)
    has_pos = any(cf[1] > 0 for cf in cashflows)
    if not has_neg or not has_pos:
        return None, "no_sign_change", "缺少正负现金流"
    rate = guess
    for i in range(max_iter):
        npv = _xnpv(rate, cashflows)
        if npv is None:
            return None, "error", "计算错误"
        t0 = cashflows[0][0]
        dnpv = sum(
            -cf * (d - t0).days / 365.25 / (1.0 + rate) ** ((d - t0).days / 365.25 + 1)
            for d, cf in cashflows
        )
        if abs(dnpv) < 1e-14:
            return None, "convergence", "导数过小，无法收敛"
        new_rate = rate - npv / dnpv
        if abs(new_rate - rate) < tol:
            return round(new_rate * 100, 4), "ok", "计算成功"
        rate = new_rate
        if abs(rate) > 10:
            return None, "divergence", "XIRR发散"
    return None, "max_iterations", "未收敛"


def get_total_assets_perf(conn):
    holdings = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
    deposits = conn.execute("SELECT SUM(amount) as total FROM deposits").fetchone()
    pending_row = conn.execute(
        "SELECT SUM(amount + COALESCE(fee, 0)) as total FROM transactions WHERE direction IN ('申购待确认', '待确认申购')"
    ).fetchone()
    ensure_cash_base(conn)
    base = get_setting_float(conn, "securities_cash_base", 0.0)
    tx_flow = transaction_cash_flow(conn)
    manual_flow = cash_flow_adjustment(conn)
    cash = base + manual_flow + tx_flow
    bank = (deposits["total"] or 0) if deposits else 0
    market = sum(dict(h)["quantity"] * dict(h)["last_price"] for h in holdings)
    pending = float(pending_row["total"] or 0) if pending_row else 0
    return market + cash + bank + pending, market, cash, bank, pending


@app.get("/performance/summary")
def performance_summary():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_portfolio_cash_flows_table(conn)

    total_assets, market_value, cash, bank, pending = get_total_assets_perf(conn)

    flows = conn.execute("SELECT * FROM portfolio_cash_flows ORDER BY date, id").fetchall()
    flows = [dict(f) for f in flows]

    total_in = sum(f["amount"] for f in flows if f["flow_type"] == "投入")
    total_out = sum(f["amount"] for f in flows if f["flow_type"] == "取出")
    net_contribution = total_in - total_out
    total_gain = total_assets - net_contribution
    total_gain_pct = (total_gain / net_contribution * 100) if net_contribution > 0 else 0

    # XIRR
    xirr_flows = []
    for f in flows:
        d = dt_date.fromisoformat(f["date"])
        if f["flow_type"] == "投入":
            xirr_flows.append((d, -f["amount"]))
        elif f["flow_type"] == "取出":
            xirr_flows.append((d, f["amount"]))
    today = dt_date.today()
    if total_assets > 0:
        xirr_flows.append((today, total_assets))
    xirr_flows.sort(key=lambda x: x[0])

    xirr_val, xirr_status, xirr_msg = calculate_xirr(xirr_flows)

    # Holdings P&L
    holdings = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
    unrealized = sum((dict(h)["last_price"] - dict(h)["avg_cost"]) * dict(h)["quantity"] for h in holdings)
    total_dividend = sum(dict(h)["total_dividend"] for h in holdings)

    # YTD
    ytd_start = dt_date(today.year, 1, 1)
    ytd_snap = conn.execute(
        "SELECT * FROM daily_snapshots WHERE date >= ? ORDER BY date ASC LIMIT 1",
        (ytd_start.isoformat(),)
    ).fetchone()
    ytd_start_assets = dict(ytd_snap)["total_assets"] if ytd_snap else total_assets
    ytd_flows = [f for f in flows if f["date"] >= ytd_start.isoformat()]
    ytd_net = sum(f["amount"] for f in ytd_flows if f["flow_type"] == "投入") - \
              sum(f["amount"] for f in ytd_flows if f["flow_type"] == "取出")
    ytd_gain = total_assets - ytd_start_assets - ytd_net if ytd_start_assets else 0
    ytd_gain_pct = (ytd_gain / ytd_start_assets * 100) if ytd_start_assets else 0

    conn.close()
    return {
        "as_of_date": today.isoformat(),
        "total_assets": round(total_assets, 2),
        "net_contribution": round(net_contribution, 2),
        "total_gain": round(total_gain, 2),
        "total_gain_pct": round(total_gain_pct, 4),
        "xirr": xirr_val,
        "xirr_status": xirr_status,
        "xirr_message": xirr_msg,
        "current_unrealized_profit": round(unrealized, 2),
        "total_dividend_income": round(total_dividend, 2),
        "pending_purchase": round(pending, 2),
        "ytd_gain": round(ytd_gain, 2),
        "ytd_gain_pct": round(ytd_gain_pct, 4),
        "flow_count": len(flows),
        "total_in": round(total_in, 2),
        "total_out": round(total_out, 2),
    }


@app.get("/performance/timeline")
def performance_timeline(start_date: Optional[str] = None, end_date: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_portfolio_cash_flows_table(conn)

    query = "SELECT * FROM daily_snapshots"
    params = []
    if start_date and end_date:
        query += " WHERE date BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE date >= ?"
        params = [start_date]
    query += " ORDER BY date ASC"
    snapshots = [dict(r) for r in conn.execute(query, params).fetchall()]

    all_flows = [dict(r) for r in conn.execute("SELECT * FROM portfolio_cash_flows ORDER BY date, id").fetchall()]
    conn.close()

    if not snapshots:
        return []

    result = []
    cumulative_in = 0.0
    cumulative_out = 0.0
    flow_idx = 0

    for snap in snapshots:
        snap_date = snap["date"]
        while flow_idx < len(all_flows) and all_flows[flow_idx]["date"] <= snap_date:
            f = all_flows[flow_idx]
            if f["flow_type"] == "投入":
                cumulative_in += f["amount"]
            elif f["flow_type"] == "取出":
                cumulative_out += f["amount"]
            flow_idx += 1
        net = cumulative_in - cumulative_out
        result.append({
            "date": snap_date,
            "total_assets": snap.get("total_assets", 0),
            "net_contribution": round(net, 2),
            "total_gain": round(snap.get("total_assets", 0) - net, 2),
        })

    return result


@app.get("/performance/contribution")
def performance_contribution():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    holdings = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()
    conn.close()

    rows = []
    for h in holdings:
        h = dict(h)
        market_value = h["quantity"] * h["last_price"]
        unrealized = (h["last_price"] - h["avg_cost"]) * h["quantity"]
        dividend = h["total_dividend"]
        total_contribution = unrealized + dividend
        rows.append({
            "code": h["code"],
            "name": h["name"],
            "category": h.get("category", ""),
            "quantity": h["quantity"],
            "market_value": round(market_value, 2),
            "avg_cost": round(h["avg_cost"], 4),
            "last_price": round(h["last_price"], 4),
            "unrealized_profit": round(unrealized, 2),
            "dividend_income": round(dividend, 2),
            "total_contribution": round(total_contribution, 2),
        })

    rows.sort(key=lambda r: r["total_contribution"], reverse=True)
    return rows
