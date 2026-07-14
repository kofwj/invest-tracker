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


def build_performance_story(conn):
    """人话绩效故事：谁赚钱、谁拖累、整户结论。数字全部来自现有汇总/贡献，不猜。"""
    summary = build_performance_summary(conn)
    contrib = build_performance_contribution(conn)
    timeline = build_performance_timeline(conn)

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

    if has_flows:
        if total_gain > 0:
            headline = f"整户相对净投入赚了 {_money_cn(total_gain).lstrip('+')}（{_pct_cn(summary.get('total_gain_pct'))}）"
        elif total_gain < 0:
            headline = f"整户相对净投入亏了 {_money_cn(abs(total_gain)).lstrip('+')}（{_pct_cn(summary.get('total_gain_pct'))}）"
        else:
            headline = "整户相对净投入基本持平"
    else:
        if lifetime > 0:
            headline = f"当前仓全周期合计赚 {_money_cn(lifetime).lstrip('+')}（外部流水未录全，整户总账仅供参考）"
        elif lifetime < 0:
            headline = f"当前仓全周期合计亏 {_money_cn(abs(lifetime)).lstrip('+')}（外部流水未录全，整户总账仅供参考）"
        else:
            headline = "当前仓全周期盈亏接近 0；外部流水未录全时，整户总账先当参考"

    bullets = []
    bullets.append(f"现在总资产约 {_money_cn(assets).lstrip('+')}。")
    if has_flows:
        bullets.append(
            f"累计净投入 {_money_cn(summary.get('net_contribution')).lstrip('+')}；"
            f"累计总收益 {_money_cn(total_gain)}。"
        )
    else:
        bullets.append("组合外部「投入/取出」流水还没录齐：净投入、累计总收益、年化请先当参考。")

    bullets.append(
        f"当前还拿着的仓：浮盈+分红 {_money_cn(float_plus_div)}；"
        f"接近券商累计的全周期 {_money_cn(lifetime)}。"
    )
    bullets.append(f"今年至今（YTD）{_money_cn(ytd)}（{_pct_cn(ytd_pct)}）。")
    if xirr is not None and summary.get("xirr_status") == "ok":
        bullets.append(f"资金加权年化（XIRR）约 {_pct_cn(xirr)}。")
    elif has_flows:
        bullets.append(f"年化暂时算不出：{summary.get('xirr_message') or '现金流不足'}。")

    by_contrib = sorted(contrib, key=lambda r: float(r.get("total_contribution") or 0), reverse=True)
    winners = [r for r in by_contrib if float(r.get("total_contribution") or 0) > 0][:3]
    losers = [r for r in sorted(by_contrib, key=lambda r: float(r.get("total_contribution") or 0)) if float(r.get("total_contribution") or 0) < 0][:3]

    def _row_line(r, key="total_contribution"):
        name = (r.get("name") or r.get("code") or "—").strip()
        code = (r.get("code") or "").strip()
        label = f"{name}（{code}）" if code and name != code else name
        return {
            "code": code,
            "name": name,
            "label": label,
            "amount": round(float(r.get(key) or 0), 2),
            "text": f"{label} {_money_cn(r.get(key))}",
        }

    winner_items = [_row_line(r) for r in winners]
    loser_items = [_row_line(r) for r in losers]

    if winner_items:
        bullets.append("当前仓赚钱靠前：" + "；".join(i["text"] for i in winner_items) + "。")
    if loser_items:
        bullets.append("当前仓拖累靠前：" + "；".join(i["text"] for i in loser_items) + "。")
    if not winner_items and not loser_items:
        bullets.append("当前没有可拆的持仓贡献（可能空仓或尚未同步价格）。")

    # 大类贡献（权益/固收等，按 category 粗分）
    cat_map = {}
    for r in contrib:
        cat = (r.get("category") or "其他").strip() or "其他"
        if any(k in cat for k in ("债", "固收", "货币", "现金", "REIT", "REITs")):
            bucket = "固收相关"
        elif any(k in cat for k in ("存款",)):
            bucket = "存款"
        else:
            bucket = "权益相关"
        cat_map[bucket] = cat_map.get(bucket, 0.0) + float(r.get("total_contribution") or 0)
    category_contrib = [
        {"name": k, "amount": round(v, 2), "text": f"{k} {_money_cn(v)}"}
        for k, v in sorted(cat_map.items(), key=lambda x: x[1], reverse=True)
    ]
    if category_contrib:
        bullets.append("大类贡献（当前仓）：" + "；".join(c["text"] for c in category_contrib) + "。")

    month_change = None
    lookback_change = None
    if len(timeline) >= 2:
        last = timeline[-1]
        prev = timeline[-2]
        da = float(last.get("total_assets") or 0) - float(prev.get("total_assets") or 0)
        dd = str(last.get("date") or "")
        pd = str(prev.get("date") or "")
        month_change = {
            "from_date": pd,
            "to_date": dd,
            "assets_change": round(da, 2),
            "text": f"最近两个快照日（{pd} → {dd}）总资产变化 {_money_cn(da)}。",
        }
        bullets.append(month_change["text"])

        # 近约 30 个快照点（或全部若不足）
        window = timeline[-31:] if len(timeline) > 31 else timeline
        if len(window) >= 2:
            w0, w1 = window[0], window[-1]
            wa = float(w1.get("total_assets") or 0) - float(w0.get("total_assets") or 0)
            lookback_change = {
                "from_date": str(w0.get("date") or ""),
                "to_date": str(w1.get("date") or ""),
                "points": len(window),
                "assets_change": round(wa, 2),
                "text": (
                    f"近 {len(window)} 个快照日（{w0.get('date')} → {w1.get('date')}）"
                    f"总资产变化 {_money_cn(wa)}。"
                ),
            }
            bullets.append(lookback_change["text"])

    caveats = [
        "整户总账、当前仓浮盈+分红、全周期盈亏三套口径本来就不会完全相等。",
        "对账优先看「全周期」；日常加减仓看持仓明细；整户结果看本页总账。",
    ]
    if not has_flows:
        caveats.insert(0, "录齐底部「组合资金流水」后，净投入/总收益/年化才完整。")

    tone = "neutral"
    primary = total_gain if has_flows else lifetime
    if primary > 0:
        tone = "positive"
    elif primary < 0:
        tone = "negative"

    return {
        "as_of_date": summary.get("as_of_date"),
        "tone": tone,
        "headline": headline,
        "bullets": bullets,
        "winners": winner_items,
        "losers": loser_items,
        "category_contrib": category_contrib,
        "month_change": month_change,
        "lookback_change": lookback_change,
        "caveats": caveats,
        "metrics": {
            "total_assets": summary.get("total_assets"),
            "total_gain": summary.get("total_gain") if has_flows else None,
            "lifetime_profit": summary.get("lifetime_profit"),
            "ytd_gain": summary.get("ytd_gain"),
            "xirr": summary.get("xirr"),
            "has_external_flows": has_flows,
        },
    }
