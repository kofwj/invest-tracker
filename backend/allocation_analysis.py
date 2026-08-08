"""Portfolio allocation story: policy-aligned diagnosis over real holdings.

Numbers come from discipline report + contribution + deposits. No guesses,
no auto-trading. Homogeneity tags are coarse name/category heuristics.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    from .database import LOCAL_TZ, local_today_iso
    from .discipline import _holding_rows, build_discipline_report, get_policy
except ImportError:
    from database import LOCAL_TZ, local_today_iso
    from discipline import _holding_rows, build_discipline_report, get_policy

# Fine-category concentration warn threshold (single module constant; not policy yet).
CATEGORY_CONCENTRATION_WARN_PCT = 35.0

EQUITY_SHOCKS = (-5.0, -10.0, -20.0)


def _money_cn(value: float, signed: bool = False) -> str:
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        n = 0.0
    if signed:
        sign = "+" if n > 0 else ""
        return f"{sign}{n:,.0f} 元"
    return f"{n:,.0f} 元"


def _level_to_ui_type(level: str) -> str:
    if level == "warning":
        return "warning"
    if level == "info":
        return "info"
    return "success"


def _policy_slice(policy: Dict[str, Any]) -> Dict[str, Any]:
    targets = policy.get("targets") or {}
    return {
        "equity_min_pct": float(policy.get("equity_min_pct") or 35),
        "equity_max_pct": float(policy.get("equity_max_pct") or 55),
        "defensive_min_pct": float(policy.get("defensive_min_pct") or 40),
        "single_holding_max_pct": float(policy.get("single_holding_max_pct") or 20),
        "rebalance_band_pct": float(policy.get("rebalance_band_pct") or 3),
        "targets": {
            "equity_pct": float(targets.get("equity_pct") or 45),
            "fixed_income_pct": float(targets.get("fixed_income_pct") or 30),
            "deposit_pct": float(targets.get("deposit_pct") or 25),
        },
    }


def _build_health(
    snapshot: Dict[str, Any],
    policy: Dict[str, Any],
    max_category: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    eq = float(snapshot.get("equity_pct") or 0)
    defensive = float(snapshot.get("defensive_pct") or 0)
    pending = float(snapshot.get("pending_purchase") or 0)
    eq_min = float(policy.get("equity_min_pct") or 35)
    eq_max = float(policy.get("equity_max_pct") or 55)
    def_min = float(policy.get("defensive_min_pct") or 40)

    if eq > eq_max:
        eq_status, eq_level = "偏高", "warning"
    elif eq < eq_min:
        eq_status, eq_level = "偏低", "info"
    else:
        eq_status, eq_level = "适中", "ok"

    if defensive >= def_min:
        def_status, def_level = "充足", "ok"
    else:
        def_status, def_level = "偏少", "warning"

    cat_pct = float((max_category or {}).get("pct") or 0)
    cat_name = (max_category or {}).get("category") or "—"
    cat_mv = float((max_category or {}).get("market_value") or 0)
    if max_category and cat_pct > CATEGORY_CONCENTRATION_WARN_PCT:
        cat_status, cat_level = "集中", "warning"
        cat_text = (
            f"{cat_name} 占 {cat_pct:.1f}%（细类示意线 {CATEGORY_CONCENTRATION_WARN_PCT:.0f}%），"
            f"金额 {_money_cn(cat_mv)}。"
        )
    elif max_category:
        cat_status, cat_level = "分散", "ok"
        cat_text = f"{cat_name} 占 {cat_pct:.1f}%，金额 {_money_cn(cat_mv)}。"
    else:
        cat_status, cat_level = "无数据", "info"
        cat_text = "暂无资产分类数据。"

    if pending > 0:
        pend_status, pend_level = "待确认", "info"
        pend_text = f"当前申购在途 {_money_cn(pending)}，已计入固收/总资产，但不计入持仓盈亏。"
    else:
        pend_status, pend_level = "无", "ok"
        pend_text = "当前没有申购待确认资产。"

    return [
        {
            "code": "equity_band",
            "label": "权益波动暴露",
            "status": eq_status,
            "level": eq_level,
            "text": (
                f"权益占总资产 {eq:.1f}%（政策区间 {eq_min:.0f}%–{eq_max:.0f}%），"
                f"用于判断组合对股市波动的敏感度。"
            ),
        },
        {
            "code": "defensive_floor",
            "label": "防守缓冲",
            "status": def_status,
            "level": def_level,
            "text": (
                f"固收、证券现金、银行存款和申购在途等合计 {defensive:.1f}%"
                f"（建议 ≥ {def_min:.0f}%），是组合回撤缓冲。"
            ),
        },
        {
            "code": "category_concentration",
            "label": "单类集中度",
            "status": cat_status,
            "level": cat_level,
            "text": cat_text,
        },
        {
            "code": "pending_purchase",
            "label": "申购在途",
            "status": pend_status,
            "level": pend_level,
            "text": pend_text,
        },
    ]


def _build_concentration(
    holdings: List[Dict[str, Any]], total_assets: float
) -> Dict[str, Any]:
    ranked = sorted(holdings, key=lambda h: float(h.get("market_value") or 0), reverse=True)
    top3: List[Dict[str, Any]] = []
    top3_pct = 0.0
    for h in ranked[:3]:
        mv = float(h.get("market_value") or 0)
        pct = (mv / total_assets * 100.0) if total_assets > 0 else 0.0
        top3_pct += pct
        top3.append(
            {
                "code": str(h.get("code") or ""),
                "name": str(h.get("name") or h.get("code") or ""),
                "pct": round(pct, 2),
                "market_value": round(mv, 2),
            }
        )
    top1 = top3[0] if top3 else {"code": "", "name": "", "pct": 0.0, "market_value": 0.0}

    hhi = 0.0
    if total_assets > 0:
        for h in ranked:
            w = float(h.get("market_value") or 0) / total_assets
            hhi += w * w

    cat_map: Dict[str, float] = {}
    for h in ranked:
        cat = str(h.get("category") or "未分类")
        cat_map[cat] = cat_map.get(cat, 0.0) + float(h.get("market_value") or 0)
    max_category = None
    if cat_map:
        cat, mv = max(cat_map.items(), key=lambda x: x[1])
        max_category = {
            "category": cat,
            "pct": round((mv / total_assets * 100.0) if total_assets > 0 else 0.0, 2),
            "market_value": round(mv, 2),
        }

    return {
        "top1": top1,
        "top3_pct": round(top3_pct, 2),
        "top3": top3,
        "hhi": round(hhi, 4),
        "max_category": max_category or {"category": "", "pct": 0.0, "market_value": 0.0},
    }


def _issues_from_breaches_and_plans(
    breaches: List[Dict[str, Any]],
    plans: List[Dict[str, Any]],
    health: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    seen = set()

    def add_issue(item: Dict[str, Any], default_hint: str) -> None:
        level = str(item.get("level") or "info")
        if level == "ok":
            return
        code = str(item.get("code") or item.get("title") or "")
        key = (code, str(item.get("title") or ""), level)
        if key in seen:
            return
        seen.add(key)
        hint = default_hint
        if code in ("equity_high", "equity_low", "defensive_low"):
            hint = "去右栏看再平衡建议"
        elif code in ("holding_concentrated", "named_limit", "gree_soft"):
            hint = "去右栏看再平衡建议或调整参数"
        elif "a500" in code:
            hint = "看个人计划进度"
        issues.append(
            {
                "id": code or f"issue_{len(issues)}",
                "level": level if level in ("warning", "info") else "info",
                "title": str(item.get("title") or code or "提醒"),
                "text": str(item.get("text") or ""),
                "code_ref": item.get("code_ref") or item.get("symbol"),
                "action_hint": hint,
            }
        )

    for b in breaches or []:
        add_issue(b, "去右栏看纪律检查")
    for p in plans or []:
        add_issue(p, "看个人计划")

    # Extra health-only issues not already in breaches (category concentration).
    for h in health or []:
        if h.get("level") in ("warning", "info") and h.get("code") == "category_concentration":
            if h.get("level") == "warning":
                add_issue(
                    {
                        "code": "category_concentration",
                        "level": "warning",
                        "title": f"细类偏集中：{h.get('status')}",
                        "text": h.get("text"),
                    },
                    "看左栏细类占比",
                )
        if h.get("code") == "pending_purchase" and h.get("level") == "info":
            add_issue(
                {
                    "code": "pending_purchase",
                    "level": "info",
                    "title": "有申购在途",
                    "text": h.get("text"),
                },
                "去交易页核对待确认",
            )

    # Prefer warning first.
    issues.sort(key=lambda x: 0 if x.get("level") == "warning" else 1)
    return issues


def _build_headline(
    snapshot: Dict[str, Any],
    policy_slice: Dict[str, Any],
    issues: List[Dict[str, Any]],
    concentration: Dict[str, Any],
) -> Tuple[str, str, List[str]]:
    eq = float(snapshot.get("equity_pct") or 0)
    defensive = float(snapshot.get("defensive_pct") or 0)
    t_eq = float(policy_slice["targets"]["equity_pct"])
    band = float(policy_slice["rebalance_band_pct"])
    gap_eq = t_eq - eq  # positive = below target
    top1 = concentration.get("top1") or {}
    top1_name = top1.get("name") or ""
    top1_pct = float(top1.get("pct") or 0)

    warnings = [i for i in issues if i.get("level") == "warning"]
    infos = [i for i in issues if i.get("level") == "info"]

    if warnings:
        severity = "warning"
        w0 = warnings[0]
        headline = str(w0.get("title") or "有需要关注的配置问题")
        if w0.get("text"):
            # Prefer short composite when equity is the main issue.
            if abs(gap_eq) > band:
                direction = "偏高" if gap_eq < 0 else "偏低"
                headline = (
                    f"权益 {eq:.1f}%（目标 {t_eq:.0f}%±{band:.0f}），{direction}约 {abs(gap_eq):.1f} 个百分点"
                )
                if top1_name and top1_pct > 0:
                    headline += f"；前大持仓「{top1_name}」约 {top1_pct:.1f}%"
            else:
                headline = f"{w0.get('title')}：{w0.get('text')}"
                if len(headline) > 80:
                    headline = str(w0.get("title") or headline[:80])
    elif abs(gap_eq) > band or infos:
        severity = "info"
        direction = "偏高" if gap_eq < 0 else "偏低"
        if abs(gap_eq) > band:
            headline = (
                f"权益 {eq:.1f}%（目标 {t_eq:.0f}%±{band:.0f}），相对目标{direction}约 {abs(gap_eq):.1f} 个百分点"
            )
        else:
            headline = f"权益 {eq:.1f}% 大致在目标附近；另有 {len(infos)} 条提示"
    else:
        severity = "ok"
        headline = f"权益 {eq:.1f}%，在目标附近；防守 {defensive:.1f}%。"

    bullets: List[str] = []
    bullets.append(
        f"权益实际 {eq:.1f}% / 目标 {t_eq:.0f}%（带宽 ±{band:.0f}%）"
    )
    bullets.append(f"防守合计 {defensive:.1f}%（下限 {policy_slice['defensive_min_pct']:.0f}%）")
    if top1_name:
        bullets.append(
            f"最大持仓 {top1_name} 约 {top1_pct:.1f}%；前三大合计 {float(concentration.get('top3_pct') or 0):.1f}%"
        )
    pending = float(snapshot.get("pending_purchase") or 0)
    if pending > 0:
        bullets.append(f"申购在途 {_money_cn(pending)}")
    if warnings:
        bullets.append(f"需关注问题 {len(warnings)} 条（含纪律/计划）")
    return headline, severity, bullets[:5]


def _build_liquidity(conn, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    cash = float(snapshot.get("securities_cash") or 0)
    pending = float(snapshot.get("pending_purchase") or 0)
    today = local_today_iso()
    try:
        today_d = datetime.strptime(today, "%Y-%m-%d").date()
    except ValueError:
        today_d = datetime.now(LOCAL_TZ).date()
    limit = today_d + timedelta(days=30)

    due_amt = 0.0
    due_count = 0
    try:
        rows = conn.execute(
            "SELECT amount, due_date FROM deposits WHERE amount IS NOT NULL AND amount > 0"
        ).fetchall()
    except Exception:
        rows = []
    for r in rows:
        if isinstance(r, sqlite3.Row):
            amount = float(r["amount"] or 0)
            due = r["due_date"]
        else:
            amount = float(r[0] or 0)
            due = r[1]
        if not due:
            continue
        try:
            due_d = datetime.strptime(str(due)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        # 已到期或 30 天内到期计入可动用存款
        if due_d <= limit:
            due_amt += amount
            due_count += 1

    deployable = cash + due_amt
    text = (
        f"证券现金 {_money_cn(cash)}；30 天内（含已到期）存款约 {_money_cn(due_amt)}"
        f"（{due_count} 笔）；粗算可挪动约 {_money_cn(deployable)}。"
        f"未把长期未到期存款算进来"
        + (f"；另有申购在途 {_money_cn(pending)}" if pending > 0 else "")
        + "。"
    )
    return {
        "securities_cash": round(cash, 2),
        "pending_purchase": round(pending, 2),
        "deposit_due_30d_amount": round(due_amt, 2),
        "deposit_due_30d_count": due_count,
        "deployable_30d": round(deployable, 2),
        "text": text,
    }


def _build_scenarios(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    equity_mv = float(snapshot.get("equity_mv") or 0)
    total = float(snapshot.get("total_assets") or 0)
    out = []
    for shock in EQUITY_SHOCKS:
        pnl = equity_mv * (shock / 100.0)
        out.append(
            {
                "id": f"equity_down_{abs(int(shock))}",
                "label": f"权益粗估跌 {abs(int(shock))}%",
                "equity_shock_pct": shock,
                "estimated_pnl": round(pnl, 2),
                "estimated_total_assets": round(total + pnl, 2),
                "assumption": "仅权益市值按比例变动，固收/存款/现金不变；非预测",
            }
        )
    return out


# 卫星仓目标占比（占总资产）：510880 上证红利 ~6%，159201 自由现金流 ~4%
SATELLITE_TARGETS = [
    {"code": "510880", "target_pct": 6.0, "label": "510880 上证红利"},
    {"code": "159201", "target_pct": 4.0, "label": "159201 自由现金流"},
]


def build_satellite_progress(holdings: List[Dict[str, Any]], total_assets: float) -> Dict[str, Any]:
    """510880 / 159201 卫星仓建仓进度：当前占比 vs 目标，差多少、还需几手（按现价）。"""
    by_code = {str(h.get("code") or "").replace("f", ""): h for h in holdings}
    rows = []
    for t in SATELLITE_TARGETS:
        code = t["code"]
        h = by_code.get(code)
        cur_mv = float((h or {}).get("market_value") or 0)
        cur_pct = (cur_mv / total_assets * 100.0) if total_assets > 0 else 0.0
        target_mv = total_assets * t["target_pct"] / 100.0
        need_amount = target_mv - cur_mv
        price = float((h or {}).get("last_price") or 0)
        need_lots = 0
        if price > 0 and need_amount > 0:
            # A 股 ETF 一手 = 100 份
            need_lots = math.ceil(need_amount / (price * 100))
        rows.append(
            {
                "code": code,
                "label": t["label"],
                "target_pct": t["target_pct"],
                "market_value": round(cur_mv, 2),
                "pct": round(cur_pct, 2),
                "target_mv": round(target_mv, 2),
                "need_amount": round(need_amount, 2),
                "held": bool(h),
                "quantity": float((h or {}).get("quantity") or 0),
                "last_price": round(price, 4),
                "need_lots": need_lots,
            }
        )
    total_need = sum(float(r["need_amount"]) for r in rows)
    achieved_pct = sum(float(r["pct"]) for r in rows)
    target_pct = sum(float(r["target_pct"]) for r in rows)
    overall = round(achieved_pct / target_pct * 100.0, 1) if target_pct > 0 else 0.0
    return {
        "rows": rows,
        "target_total_pct": target_pct,
        "achieved_total_pct": round(achieved_pct, 2),
        "total_need_amount": round(total_need, 2),
        "overall_progress_pct": overall,
    }


def _build_focus_checks(
    holdings: List[Dict[str, Any]],
    snapshot: Dict[str, Any],
    policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """风格桶 / 削弱动作 / 黄金 三项实时体检（读 focus 配置，不硬编码）。

    返回 (health_items, issue_items)，都挂在现有「配置健康检查 + 问题清单」下。
    """
    focus = policy.get("focus") or {}
    total_assets = float(snapshot.get("total_assets") or 0)
    equity_mv = float(snapshot.get("equity_mv") or 0)
    by_code = {str(h.get("code") or "").replace("f", ""): h for h in holdings}

    def _mv_by_codes(codes):
        s = 0.0
        for c in codes or []:
            h = by_code.get(str(c))
            if h:
                s += float(h.get("market_value") or 0)
        return s

    health: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []

    # ---- 1) 高股息同风格桶：合计占权益 ---- 
    div_codes = focus.get("dividend_bucket_codes") or []
    div_max_eq = float(focus.get("dividend_bucket_equity_max_pct") or 50)
    if div_codes and equity_mv > 0:
        bucket_mv = _mv_by_codes(div_codes)
        bucket_eq_pct = bucket_mv / equity_mv * 100
        over = bucket_eq_pct > div_max_eq
        listed = [str(by_code.get(str(c), {}).get("name") or c) for c in div_codes if by_code.get(str(c))]
        health.append({
            "code": "dividend_bucket",
            "label": "高股息风格桶",
            "status": "偏重" if over else "适中",
            "level": "warning" if over else "ok",
            "text": (
                f"农行/石化/港股红利等 {len(listed)} 只合计 {bucket_mv / total_assets * 100:.1f}% 总资产、"
                f"{bucket_eq_pct:.1f}% 权益（上限 {div_max_eq:.0f}%）；同涨同跌，等于一个仓位押多遍。"
            ),
        })
        if over:
            issues.append({
                "id": "dividend_bucket",
                "level": "warning",
                "title": "高股息风格桶偏重",
                "text": health[-1]["text"],
                "action_hint": "去右栏看再平衡建议或调整参数",
            })

    # ---- 2) 削弱动作进度：该清/该减的还挂着 ----
    for task in focus.get("reduce_tasks") or []:
        code = str(task.get("code") or "")
        kind = task.get("kind")
        label = task.get("label") or code
        h = by_code.get(code)
        if not h:
            continue
        mv = float(h.get("market_value") or 0)
        pct = (mv / total_assets * 100.0) if total_assets > 0 else 0.0
        if kind == "clear":
            health.append({
                "code": f"reduce_{code}",
                "label": label,
                "status": "未清完",
                "level": "info",
                "text": f"{label}还在，占 {pct:.1f}%（{_money_cn(mv)}），动作只做了一半。",
            })
            issues.append({
                "id": f"reduce_{code}",
                "level": "info",
                "title": f"{label} 还没清完",
                "text": health[-1]["text"],
                "action_hint": "看个人计划/再平衡建议",
            })
        elif kind == "reduce":
            target_pct = float(task.get("target_pct") or 0)
            over = target_pct > 0 and pct > target_pct
            health.append({
                "code": f"reduce_{code}",
                "label": label,
                "status": "超目标" if over else "正常",
                "level": "warning" if over else "ok",
                "text": f"{label}占 {pct:.1f}%（目标降到 {target_pct:.0f}% 内），当前 {_money_cn(mv)}。",
            })
            if over:
                issues.append({
                    "id": f"reduce_{code}",
                    "level": "warning",
                    "title": f"{label} 超目标",
                    "text": health[-1]["text"],
                    "action_hint": "去右栏看再平衡建议",
                })

    # ---- 3) 黄金：占总资产低于下限则偏薄 ----
    gold_codes = focus.get("gold_codes") or []
    g_min = float(focus.get("gold_target_min_pct") or 0)
    g_max = float(focus.get("gold_target_max_pct") or g_min)
    if gold_codes and total_assets > 0:
        gold_mv = _mv_by_codes(gold_codes)
        gold_pct = gold_mv / total_assets * 100
        low = gold_pct < g_min
        high = gold_pct > g_max
        health.append({
            "code": "gold",
            "label": "黄金对冲",
            "status": ("偏高" if high else "偏低" if low else "适中"),
            "level": ("info" if (low or high) else "ok"),
            "text": (
                f"黄金 {gold_mv / 10000:.1f} 万，占 {gold_pct:.1f}%"
                f"（目标 {g_min:.0f}–{g_max:.0f}%），"
                + ("偏薄，可随缘小步补。" if low else "偏多。" if high else "在区间内。")
            ),
        })
        if low:
            issues.append({
                "id": "gold",
                "level": "info",
                "title": "黄金偏薄",
                "text": health[-1]["text"],
                "action_hint": "随缘小步补，不抢主线",
            })

    return health, issues


def build_allocation_story(conn) -> Dict[str, Any]:
    """Human-readable allocation diagnosis; all figures from tools, not guesses."""
    report = build_discipline_report(conn)
    policy = report.get("policy") or get_policy(conn)
    policy_slice = _policy_slice(policy)
    snapshot = dict(report.get("snapshot") or {})
    # Ensure defensive_pct key exists for consumers
    if "defensive_pct" not in snapshot:
        snapshot["defensive_pct"] = 0.0

    total_assets = float(snapshot.get("total_assets") or 0)
    gaps_pct_raw = report.get("gaps_pct") or {}
    # Normalize keys to equity_pct / fixed_income_pct / deposit_pct
    gap_equity = float(gaps_pct_raw.get("equity", gaps_pct_raw.get("equity_pct", 0)) or 0)
    gap_fi = float(
        gaps_pct_raw.get("fixed_income", gaps_pct_raw.get("fixed_income_pct", 0)) or 0
    )
    gap_dep = float(gaps_pct_raw.get("deposit", gaps_pct_raw.get("deposit_pct", 0)) or 0)

    gaps = {
        "equity_pct": round(gap_equity, 2),
        "fixed_income_pct": round(gap_fi, 2),
        "deposit_pct": round(gap_dep, 2),
        "equity_amount": round(total_assets * gap_equity / 100.0, 2) if total_assets else 0.0,
        "fixed_income_amount": round(total_assets * gap_fi / 100.0, 2) if total_assets else 0.0,
        "deposit_amount": round(total_assets * gap_dep / 100.0, 2) if total_assets else 0.0,
    }

    holdings = _holding_rows(conn, policy)
    concentration = _build_concentration(holdings, total_assets)
    health = _build_health(snapshot, policy, concentration.get("max_category"))
    issues = _issues_from_breaches_and_plans(
        report.get("breaches") or [],
        report.get("plans") or [],
        health,
    )
    # 风格桶 / 削弱动作 / 黄金 三项实时体检，注入既有的健康检查 + 问题清单
    focus_health, focus_issues = _build_focus_checks(holdings, snapshot, policy)
    health = health + focus_health
    issues = issues + focus_issues
    headline, severity, bullets = _build_headline(
        snapshot, policy_slice, issues, concentration
    )

    # Attach UI type for frontend convenience on health
    health_ui = []
    for h in health:
        item = dict(h)
        item["type"] = _level_to_ui_type(str(h.get("level") or "ok"))
        health_ui.append(item)

    liquidity = _build_liquidity(conn, snapshot)
    scenarios = _build_scenarios(snapshot)

    generated = report.get("generated_at") or datetime.now(LOCAL_TZ).replace(
        tzinfo=None
    ).isoformat(sep=" ", timespec="seconds")

    return {
        "headline": headline,
        "severity": severity,
        "bullets": bullets,
        "policy": policy_slice,
        "snapshot": snapshot,
        "gaps": gaps,
        "health": health_ui,
        "concentration": concentration,
        "issues": issues,
        # 同质化/收益依赖已不在前端展示，保留空占位以兼容旧调用
        "homogeneity": {"groups": [], "note": ""},
        "profit_dependency": None,
        "liquidity": liquidity,
        "scenarios": scenarios,
        "expected_return": {
            "portfolio_pct": None,
            "note": "预计年化仍由前端按持仓加权；此处不重复计算以免双口径",
        },
        "discipline_summary": report.get("summary") or "",
        "open_draft_count": int(report.get("open_draft_count") or 0),
        "satellite": build_satellite_progress(holdings, total_assets),
        "generated_at": generated,
    }
