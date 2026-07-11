from database import LOCAL_TZ
import sqlite3
from datetime import datetime


ALLOWED_DIRECTIONS = {
    "买入",
    "卖出",
    "分红",
    "分红再投资",
    "申购待确认",
    "待确认申购",
}


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


def current_holding_quantity(conn, code: str, exclude_transaction_id=None) -> float:
    """Compute current holding quantity for a code from transactions + latest correction."""
    code = str(code or "").strip()
    if not code:
        return 0.0
    corrections = latest_holding_corrections(conn)
    correction = corrections.get(code)
    qty = 0.0
    if correction:
        qty = float(correction.get("actual_quantity") or 0)
        anchor = str(correction.get("date") or "")
    else:
        anchor = None

    query = """
        SELECT date, direction, quantity, id FROM transactions
        WHERE code = ? AND TRIM(code) != ''
        ORDER BY date, id
    """
    rows = conn.execute(query, (code,)).fetchall()
    for t in rows:
        if exclude_transaction_id is not None and int(t["id"] if isinstance(t, sqlite3.Row) else t[3]) == int(exclude_transaction_id):
            continue
        direction = t["direction"] if isinstance(t, sqlite3.Row) else t[1]
        date = str((t["date"] if isinstance(t, sqlite3.Row) else t[0]) or "")
        t_qty = float((t["quantity"] if isinstance(t, sqlite3.Row) else t[2]) or 0)
        if direction in ("申购待确认", "待确认申购"):
            continue
        if anchor is not None and date <= anchor:
            continue
        if direction in ("买入", "分红再投资"):
            qty += t_qty
        elif direction == "卖出":
            qty = max(0.0, qty - t_qty)
    return float(qty)


def validate_transaction_payload(
    conn,
    *,
    direction,
    code,
    quantity,
    price,
    amount,
    fee,
    exclude_transaction_id=None,
    strict_oversell=True,
):
    """Validate transaction fields. Raises ValueError on invalid input."""
    direction = str(direction or "").strip()
    code = str(code or "").strip()
    qty = float(quantity or 0)
    px = float(price or 0)
    amt = float(amount or 0)
    f = float(fee or 0)

    if direction not in ALLOWED_DIRECTIONS:
        raise ValueError("方向必须是：买入/卖出/分红/分红再投资/申购待确认")
    if not code:
        raise ValueError("代码不能为空")
    if qty < 0:
        raise ValueError("数量不能为负")
    if px < 0:
        raise ValueError("价格不能为负")
    if amt < 0:
        raise ValueError("金额不能为负；买卖方向通过direction表示")
    if f < 0:
        raise ValueError("手续费不能为负")

    if direction == "买入" and qty <= 0:
        raise ValueError("买入数量必须大于0")
    if direction in ("申购待确认", "待确认申购") and amt <= 0:
        raise ValueError("申购待确认金额必须大于0")
    if direction == "卖出":
        if qty <= 0:
            raise ValueError("卖出数量必须大于0")
        if strict_oversell and conn is not None:
            available = current_holding_quantity(conn, code, exclude_transaction_id=exclude_transaction_id)
            # allow tiny float noise
            if qty > available + 1e-6:
                raise ValueError(f"卖出数量 {qty} 超过当前持仓 {round(available, 6)}")
    if direction == "分红" and amt <= 0:
        raise ValueError("分红金额必须大于0")
    if direction == "分红再投资" and (qty <= 0 or amt <= 0):
        raise ValueError("分红再投资需要数量和金额都大于0")
    return True


def _normalize_code_set(codes):
    """Return None for full recalc, or a non-empty set of codes for partial recalc."""
    if codes is None:
        return None
    if isinstance(codes, (str, bytes)):
        codes = [codes]
    out = {str(c or "").strip() for c in codes if str(c or "").strip()}
    return out or None


def recalc_holdings(conn, codes=None):
    """Recalculate holdings from transactions, then apply latest forced correction anchors.

    codes:
      - None / empty: full rebuild (default, safest)
      - iterable of codes: only rebuild those symbols; other holdings rows stay untouched
    """
    conn.row_factory = sqlite3.Row
    code_filter = _normalize_code_set(codes)
    if code_filter is None:
        old_holdings = {r["code"]: dict(r) for r in conn.execute("SELECT * FROM holdings").fetchall()}
        txs = conn.execute("""
            SELECT * FROM transactions
            WHERE code IS NOT NULL AND TRIM(code) != ''
            ORDER BY date, id
        """).fetchall()
        corrections_all = latest_holding_corrections(conn)
    else:
        placeholders = ",".join("?" for _ in code_filter)
        code_list = list(code_filter)
        old_holdings = {
            r["code"]: dict(r)
            for r in conn.execute(
                f"SELECT * FROM holdings WHERE code IN ({placeholders})",
                code_list,
            ).fetchall()
        }
        # Ensure every requested code exists in old_holdings map even if never held.
        for c in code_filter:
            old_holdings.setdefault(c, {"code": c})
        txs = conn.execute(
            f"""
            SELECT * FROM transactions
            WHERE code IS NOT NULL AND TRIM(code) != '' AND code IN ({placeholders})
            ORDER BY date, id
            """,
            code_list,
        ).fetchall()
        corrections_all = latest_holding_corrections(conn)
        corrections_all = {k: v for k, v in corrections_all.items() if k in code_filter}

    corrections = corrections_all
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
            reinvest_cost = cash_amount
            dividend_amount = amount
            s["quantity"] += qty
            s["cost"] += reinvest_cost
            s["net_invested"] += reinvest_cost - dividend_amount
            s["dividend"] += dividend_amount
        elif t["direction"] == "卖出":
            # Cap sell quantity to available holding to avoid phantom cash / negative inventory.
            sell_qty = min(qty, s["quantity"]) if s["quantity"] > 0 else 0.0
            if sell_qty > 0 and qty > 0:
                # Scale cash impact proportionally when historical oversell exists.
                scale = sell_qty / qty if qty > sell_qty else 1.0
                applied_cash = cash_amount * scale
                s["cost"] -= (s["cost"] / s["quantity"]) * sell_qty
                s["net_invested"] -= applied_cash
                s["quantity"] = max(0.0, s["quantity"] - sell_qty)
            else:
                # No inventory: ignore sell impact on holdings (cash still follows ledger transactions).
                pass
            if s["quantity"] == 0:
                s["cost"] = 0.0
                s["net_invested"] = 0.0
        elif t["direction"] == "分红":
            s["dividend"] += cash_amount
            s["net_invested"] -= cash_amount

    active_codes = set(state.keys())
    if code_filter is None:
        # Full rebuild: remove holdings that no longer have state.
        for code in old_holdings.keys():
            if code not in active_codes:
                conn.execute("DELETE FROM holdings WHERE code = ?", (code,))
    else:
        # Partial: only delete requested codes that have no remaining state.
        for code in code_filter:
            if code not in active_codes:
                conn.execute("DELETE FROM holdings WHERE code = ?", (code,))

    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
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
