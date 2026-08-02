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


def build_performance_summary(conn, start_date=None, end_date=None):
    totals = compute_portfolio_totals(conn)
    total_assets = totals["total_assets"]
    pending = totals["pending_purchase"]
    holdings = totals["holdings"]

    today = _local_today()

    # 全周期流水
    all_flows = conn.execute(
        "SELECT * FROM portfolio_cash_flows WHERE date <= ? ORDER BY date, id",
        (today.isoformat(),),
    ).fetchall()
    all_flows = [dict(f) for f in all_flows]

    total_in = sum(f["amount"] for f in all_flows if f["flow_type"] == "投入")
    total_out = sum(f["amount"] for f in all_flows if f["flow_type"] == "取出")
    net_contribution = total_in - total_out
    total_gain = total_assets - net_contribution
    total_gain_pct = (total_gain / net_contribution * 100) if net_contribution > 0 else 0

    from datetime import date as dt_date

    # XIRR 始终用全周期
    xirr_flows = []
    for f in all_flows:
        raw = str(f["date"])
        d = dt_date.fromisoformat(raw[:10])
        if f["flow_type"] == "投入":
            xirr_flows.append((d, -f["amount"]))
        elif f["flow_type"] == "取出":
            xirr_flows.append((d, f["amount"]))
    if total_assets > 0:
        xirr_flows.append((today, total_assets))
    xirr_flows.sort(key=lambda x: x[0])
    xirr_val, xirr_status, xirr_msg = calculate_xirr(xirr_flows)

    # 当前持仓浮盈 + 分红（不受范围影响）
    unrealized = 0.0
    total_dividend = 0.0
    for h in holdings:
        qty = float(h["quantity"] or 0)
        last = float(h["last_price"] or 0)
        avg = float(h["avg_cost"] or 0)
        unrealized += (last - avg) * qty
        total_dividend += float(h["total_dividend"] or 0)
    lifetime_profit = totals["lifetime_profit"]

    # YTD 固定今年
    ytd_start = today.replace(month=1, day=1)
    ytd_snap = conn.execute(
        "SELECT * FROM daily_snapshots WHERE date BETWEEN ? AND ? ORDER BY date ASC LIMIT 1",
        (ytd_start.isoformat(), today.isoformat()),
    ).fetchone()
    ytd_start_assets = dict(ytd_snap)["total_assets"] if ytd_snap else total_assets
    ytd_flows = [f for f in all_flows if f["date"] >= ytd_start.isoformat()]
    ytd_net = sum(f["amount"] for f in ytd_flows if f["flow_type"] == "投入") - sum(
        f["amount"] for f in ytd_flows if f["flow_type"] == "取出"
    )
    ytd_gain = total_assets - ytd_start_assets - ytd_net if ytd_start_assets else 0
    ytd_gain_pct = (ytd_gain / ytd_start_assets * 100) if ytd_start_assets else 0

    # ===== 期间收益（受时间筛选影响） =====
    period_net = net_contribution
    period_gain = total_gain
    period_gain_pct = total_gain_pct
    period_start_assets = None
    period_start_date = start_date

    if start_date:
        p_flows = [f for f in all_flows if f["date"] >= start_date]
        p_in = sum(f["amount"] for f in p_flows if f["flow_type"] == "投入")
        p_out = sum(f["amount"] for f in p_flows if f["flow_type"] == "取出")
        period_net = p_in - p_out

        snap = conn.execute(
            "SELECT total_assets FROM daily_snapshots WHERE date >= ? ORDER BY date ASC LIMIT 1",
            (start_date,),
        ).fetchone()
        period_start_assets = float(snap["total_assets"]) if snap else total_assets

        period_gain = total_assets - period_start_assets - period_net if period_start_assets else total_assets - period_net
        period_gain_pct = (period_gain / period_start_assets * 100) if period_start_assets and period_start_assets > 0 else 0

    # ===== 专业扩展指标计算 =====
    snap_assets_full = []
    try:
        snap_rows = conn.execute("SELECT date, total_assets FROM daily_snapshots ORDER BY date ASC").fetchall()
        snap_assets_full = [float(s["total_assets"] or 0) for s in snap_rows]
    except Exception:
        pass

    twr_val, twr_status = calculate_twr(snap_assets_full) if snap_assets_full else (None, "无快照")
    sharpe_val = None
    if snap_assets_full and len(snap_assets_full) >= 4:
        rets_for_sharpe = _simple_returns_from_assets(snap_assets_full)
        sharpe_val = calculate_sharpe(rets_for_sharpe)

    monthly = None
    try:
        tl_full = build_performance_timeline(conn)
        monthly = build_monthly_stats(tl_full)
    except Exception:
        pass

    underwater = None
    try:
        if 'tl_full' in locals() and tl_full:
            underwater = compute_underwater(tl_full)
    except Exception:
        pass

    float_plus_div = (unrealized + total_dividend) or 0
    div_contrib_pct = round((total_dividend / float_plus_div * 100), 1) if float_plus_div > 0 else 0

    xirr_flows_detail = [{"date": f["date"], "flow_type": f["flow_type"], "amount": round(float(f["amount"]), 2), "source": f.get("source") or ""} for f in all_flows]

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
        "flow_count": len(all_flows),
        "total_in": round(total_in, 2),
        "total_out": round(total_out, 2),

        # 新专业字段
        "twr": twr_val,
        "twr_status": twr_status,
        "sharpe": sharpe_val,
        "monthly_stats": monthly,
        "underwater": underwater,
        "dividend_contrib_pct": div_contrib_pct,
        "xirr_flows_detail": xirr_flows_detail,

        "period_start_date": period_start_date,
        "period_net_contribution": round(period_net, 2),
        "period_gain": round(period_gain, 2),
        "period_gain_pct": round(period_gain_pct, 4),
        "period_start_assets": round(period_start_assets, 2) if period_start_assets else None,
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
                "equity_mv": snap.get("equity_mv", 0) or 0,
                "bond_mv": snap.get("bond_mv", 0) or 0,
                "reit_mv": snap.get("reit_mv", 0) or 0,
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


def _money_cn(value):
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        n = 0.0
    sign = "+" if n > 0 else ""
    return f"{sign}{n:,.0f} 元"


def _pct_cn(value):
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        n = 0.0
    sign = "+" if n > 0 else ""
    return f"{sign}{n:.2f}%"


def build_performance_story(conn, start_date=None, end_date=None):
    """人话绩效故事。支持时间范围时重点说「本期」。"""
    summary = build_performance_summary(conn, start_date, end_date)
    contrib = build_performance_contribution(conn)
    timeline = build_performance_timeline(conn, start_date, end_date)

    has_flows = int(summary.get("flow_count") or 0) > 0
    total_gain = float(summary.get("total_gain") or 0)
    lifetime = float(summary.get("lifetime_profit") or 0)
    float_plus_div = float(summary.get("current_unrealized_profit") or 0) + float(
        summary.get("total_dividend_income") or 0
    )
    ytd = float(summary.get("ytd_gain") or 0)
    ytd_pct = float(summary.get("ytd_gain_pct") or 0)
    xirr = summary.get("xirr")
    assets = float(summary.get("total_assets") or 0)

    use_period = bool(start_date)
    pg = float(summary.get("period_gain") or total_gain)
    pp = float(summary.get("period_gain_pct") or (summary.get("total_gain_pct") or 0))

    if use_period:
        if pg > 0:
            headline = f"这段时间相对净投入赚了 {_money_cn(pg).lstrip('+')}（{_pct_cn(pp)}）"
        elif pg < 0:
            headline = f"这段时间相对净投入亏了 {_money_cn(abs(pg)).lstrip('+')}（{_pct_cn(pp)}）"
        else:
            headline = "这段时间相对净投入基本持平"
    else:
        if has_flows:
            if total_gain > 0:
                headline = f"整户相对净投入赚了 {_money_cn(total_gain).lstrip('+')}（{_pct_cn(summary.get('total_gain_pct'))}）"
            elif total_gain < 0:
                headline = f"整户相对净投入亏了 {_money_cn(abs(total_gain)).lstrip('+')}（{_pct_cn(summary.get('total_gain_pct'))}）"
            else:
                headline = "整户相对净投入基本持平"
        else:
            if lifetime > 0:
                headline = f"当前仓全周期合计赚 {_money_cn(lifetime).lstrip('+')}（外部流水未录全）"
            elif lifetime < 0:
                headline = f"当前仓全周期合计亏 {_money_cn(abs(lifetime)).lstrip('+')}（外部流水未录全）"
            else:
                headline = "当前仓全周期盈亏接近 0"

    bullets = []
    bullets.append(f"现在总资产约 {_money_cn(assets).lstrip('+')}。")

    if use_period:
        bullets.append(f"本期净投入 {_money_cn(summary.get('period_net_contribution')).lstrip('+')}。")
        bullets.append(f"本期赚/亏 {_money_cn(pg)}。")
    else:
        if has_flows:
            bullets.append(f"累计净投入 {_money_cn(summary.get('net_contribution')).lstrip('+')}；累计总收益 {_money_cn(total_gain)}。")
        else:
            bullets.append("组合外部「投入/取出」流水还没录齐。")

    bullets.append(f"现在还拿着的仓浮盈+分红 {_money_cn(float_plus_div)}；接近券商累计的全周期 {_money_cn(lifetime)}。")
    bullets.append(f"今年至今（YTD）{_money_cn(ytd)}（{_pct_cn(ytd_pct)}）。")

    if xirr is not None and summary.get("xirr_status") == "ok":
        bullets.append(f"资金加权年化（XIRR）约 {_pct_cn(xirr)}。")
    elif has_flows:
        bullets.append(f"年化暂时算不出：{summary.get('xirr_message') or '现金流不足'}。")

    # 贡献（当前仓，不受范围影响）
    by_contrib = sorted(contrib, key=lambda r: float(r.get("total_contribution") or 0), reverse=True)
    winners = [r for r in by_contrib if float(r.get("total_contribution") or 0) > 0][:3]
    losers = [r for r in sorted(contrib, key=lambda r: float(r.get("total_contribution") or 0)) if float(r.get("total_contribution") or 0) < 0][:3]

    def _row_line(r, key="total_contribution"):
        name = (r.get("name") or r.get("code") or "—").strip()
        code = (r.get("code") or "").strip()
        label = f"{name}（{code}）" if code and name != code else name
        return {"code": code, "name": name, "label": label, "amount": round(float(r.get(key) or 0), 2), "text": f"{label} {_money_cn(r.get(key))}"}

    winner_items = [_row_line(r) for r in winners]
    loser_items = [_row_line(r) for r in losers]

    bucket_order = ("债基", "REITs", "权益")
    cat_map = {k: 0.0 for k in bucket_order}
    for r in contrib:
        cat = (r.get("category") or "其他").strip() or "其他"
        upper = cat.upper()
        if "REIT" in upper: b = "REITs"
        elif any(k in cat for k in ("债", "固收", "货币", "现金")): b = "债基"
        else: b = "权益"
        cat_map[b] += float(r.get("total_contribution") or 0)
    category_contrib = [{"name": n, "amount": round(cat_map[n], 2), "text": f"{n} {_money_cn(cat_map[n])}"} for n in bucket_order]

    caveats = ["总收益 = 当前总资产 − 累计净投入。", "当前仓贡献只算现在还拿着的东西。"]
    if not has_flows:
        caveats.insert(0, "建议录「投入/取出」流水后数据更准。")

    tone = "positive" if (pg if use_period else total_gain) > 0 else ("negative" if (pg if use_period else total_gain) < 0 else "neutral")

    return {
        "as_of_date": summary.get("as_of_date"),
        "tone": tone,
        "headline": headline,
        "bullets": bullets,
        "winners": winner_items,
        "losers": loser_items,
        "category_contrib": category_contrib,
        "caveats": caveats,
        "metrics": {
            "total_assets": summary.get("total_assets"),
            "period_gain": summary.get("period_gain") if use_period else None,
            "total_gain": summary.get("total_gain") if has_flows else None,
            "lifetime_profit": summary.get("lifetime_profit"),
            "ytd_gain": summary.get("ytd_gain"),
            "xirr": summary.get("xirr"),
            "has_external_flows": has_flows,
        },
    }


# ==================== 专业指标扩展（TWR、Sharpe、月度、现金流影响、underwater 等） ====================

def _simple_returns_from_assets(assets_list):
    """从连续总资产序列计算简单回报"""
    rets = []
    for i in range(1, len(assets_list)):
        prev = assets_list[i-1]
        curr = assets_list[i]
        if prev and prev > 0:
            rets.append((curr - prev) / prev)
    return rets


def calculate_twr(assets_series):
    """时间加权收益率（TWR）：几何链乘 (1+r) - 1。核心是剥离你现金流投得准不准。"""
    if not assets_series or len(assets_series) < 2:
        return None, "数据不足"
    rets = _simple_returns_from_assets([a for a in assets_series if a is not None])
    if not rets:
        return None, "无有效回报"
    growth = 1.0
    for r in rets:
        growth *= (1 + r)
    twr = growth - 1
    return round(twr * 100, 2), "ok"


def calculate_sharpe(returns, rf_annual=0.02, periods=252):
    """简单年化 Sharpe。rf 默认 2%（可按 1 年期国债调整）。数据少时 None。"""
    if not returns or len(returns) < 3:
        return None
    import math
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret)**2 for r in returns) / len(returns)
    std = math.sqrt(variance)
    if std == 0:
        return None
    ann_excess = (mean_ret * periods - rf_annual)
    ann_std = std * math.sqrt(periods)
    sharpe = ann_excess / ann_std if ann_std > 0 else None
    return round(sharpe, 2) if sharpe is not None else None


def build_monthly_stats(timeline_rows):
    """月度收益统计：最好/最差月、平均月回报、正收益月占比。"""
    if not timeline_rows or len(timeline_rows) < 2:
        return None
    from collections import defaultdict
    from datetime import datetime as dt
    monthly = defaultdict(list)
    for r in timeline_rows:
        d = dt.fromisoformat(str(r.get("date", ""))[:10])
        key = (d.year, d.month)
        monthly[key].append((d, float(r.get("total_assets") or 0)))

    month_ends = []
    for key in sorted(monthly.keys()):
        last = sorted(monthly[key], key=lambda x: x[0])[-1]
        month_ends.append(last[1])

    if len(month_ends) < 2:
        return None

    monthly_rets = []
    for i in range(1, len(month_ends)):
        p = month_ends[i-1]
        c = month_ends[i]
        if p > 0:
            monthly_rets.append((c - p) / p)

    if not monthly_rets:
        return None

    best = max(monthly_rets) * 100
    worst = min(monthly_rets) * 100
    avg = (sum(monthly_rets) / len(monthly_rets)) * 100
    positive = sum(1 for r in monthly_rets if r > 0)
    pos_pct = round(positive / len(monthly_rets) * 100, 1)

    return {
        "best_month": round(best, 2),
        "worst_month": round(worst, 2),
        "avg_monthly": round(avg, 2),
        "positive_pct": pos_pct,
        "months_count": len(monthly_rets),
    }


def compute_underwater(timeline_rows):
    """当前离所有时峰值的距离（underwater %），和峰值日期。"""
    if not timeline_rows:
        return None
    peak = -1.0
    peak_date = None
    for r in timeline_rows:
        v = float(r.get("total_assets") or 0)
        if v > peak:
            peak = v
            peak_date = r.get("date")
    current = float(timeline_rows[-1].get("total_assets") or 0) if timeline_rows else 0
    if peak <= 0:
        return None
    uw = (peak - current) / peak * 100
    return {
        "underwater_pct": round(max(uw, 0), 2),
        "peak": round(peak, 2),
        "peak_date": peak_date,
        "current": round(current, 2),
    }

