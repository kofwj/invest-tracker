from datetime import datetime

try:
    from .database import LOCAL_TZ
    from .portfolio_totals import compute_portfolio_totals, holding_lifetime_profit
except ImportError:
    from database import LOCAL_TZ
    from portfolio_totals import compute_portfolio_totals, holding_lifetime_profit


def _local_today():
    return datetime.now(LOCAL_TZ).date()


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
    for _ in range(max_iter):
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
    totals = compute_portfolio_totals(conn)
    return (
        totals["total_assets"],
        totals["total_market_value"],
        totals["securities_cash"],
        totals["bank_balance"],
        totals["pending_purchase"],
    )


def build_performance_summary(conn):
    totals = compute_portfolio_totals(conn)
    total_assets = totals["total_assets"]
    pending = totals["pending_purchase"]
    holdings = totals["holdings"]

    flows = conn.execute("SELECT * FROM portfolio_cash_flows ORDER BY date, id").fetchall()
    flows = [dict(f) for f in flows]

    total_in = sum(f["amount"] for f in flows if f["flow_type"] == "投入")
    total_out = sum(f["amount"] for f in flows if f["flow_type"] == "取出")
    net_contribution = total_in - total_out
    total_gain = total_assets - net_contribution
    total_gain_pct = (total_gain / net_contribution * 100) if net_contribution > 0 else 0

    from datetime import date as dt_date

    xirr_flows = []
    for f in flows:
        raw = str(f["date"])
        d = dt_date.fromisoformat(raw[:10])
        if f["flow_type"] == "投入":
            xirr_flows.append((d, -f["amount"]))
        elif f["flow_type"] == "取出":
            xirr_flows.append((d, f["amount"]))
    today = _local_today()
    if total_assets > 0:
        xirr_flows.append((today, total_assets))
    xirr_flows.sort(key=lambda x: x[0])

    xirr_val, xirr_status, xirr_msg = calculate_xirr(xirr_flows)

    # 未实现浮盈（不含分红）；分红单独列；全周期用摊薄成本
    unrealized = 0.0
    total_dividend = 0.0
    for h in holdings:
        qty = float(h["quantity"] or 0)
        last = float(h["last_price"] or 0)
        avg = float(h["avg_cost"] or 0)
        unrealized += (last - avg) * qty
        total_dividend += float(h["total_dividend"] or 0)
    lifetime_profit = totals["lifetime_profit"]

    ytd_start = today.replace(month=1, day=1)
    ytd_snap = conn.execute(
        "SELECT * FROM daily_snapshots WHERE date >= ? ORDER BY date ASC LIMIT 1",
        (ytd_start.isoformat(),),
    ).fetchone()
    ytd_start_assets = dict(ytd_snap)["total_assets"] if ytd_snap else total_assets
    ytd_flows = [f for f in flows if f["date"] >= ytd_start.isoformat()]
    ytd_net = sum(f["amount"] for f in ytd_flows if f["flow_type"] == "投入") - sum(
        f["amount"] for f in ytd_flows if f["flow_type"] == "取出"
    )
    ytd_gain = total_assets - ytd_start_assets - ytd_net if ytd_start_assets else 0
    ytd_gain_pct = (ytd_gain / ytd_start_assets * 100) if ytd_start_assets else 0

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
        "lifetime_profit": round(lifetime_profit, 2),
        "pending_purchase": round(pending, 2),
        "ytd_gain": round(ytd_gain, 2),
        "ytd_gain_pct": round(ytd_gain_pct, 4),
        "flow_count": len(flows),
        "total_in": round(total_in, 2),
        "total_out": round(total_out, 2),
    }


def build_performance_timeline(conn, start_date=None, end_date=None):
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
        result.append(
            {
                "date": snap_date,
                "total_assets": snap.get("total_assets", 0),
                "net_contribution": round(net, 2),
                "total_gain": round(snap.get("total_assets", 0) - net, 2),
            }
        )

    return result


def build_performance_contribution(conn):
    holdings = conn.execute("SELECT * FROM holdings WHERE quantity > 0").fetchall()

    rows = []
    for h in holdings:
        qty = float(h["quantity"] or 0)
        last = float(h["last_price"] or 0)
        avg = float(h["avg_cost"] or 0)
        market_value = qty * last
        unrealized = (last - avg) * qty
        dividend = float(h["total_dividend"] or 0)
        total_contribution = unrealized + dividend
        diluted = h["diluted_cost"] if h["diluted_cost"] is not None else avg
        lifetime_profit = holding_lifetime_profit(h)
        rows.append(
            {
                "code": h["code"],
                "name": h["name"],
                "category": h["category"] if "category" in h.keys() else "",
                "quantity": qty,
                "market_value": round(market_value, 2),
                "avg_cost": round(avg, 4),
                "diluted_cost": round(float(diluted or 0), 4),
                "last_price": round(last, 4),
                "unrealized_profit": round(unrealized, 2),
                "dividend_income": round(dividend, 2),
                "total_contribution": round(total_contribution, 2),
                "lifetime_profit": round(lifetime_profit, 2),
            }
        )

    rows.sort(key=lambda r: r["total_contribution"], reverse=True)
    return rows
