"""Portfolio allocation story: policy-aligned diagnosis over real holdings.

Numbers come from discipline report + contribution + deposits. No guesses,
no auto-trading. Homogeneity tags are coarse name/category heuristics.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    from .database import LOCAL_TZ, local_today_iso
    from .discipline import _holding_rows, build_discipline_report, get_policy
    from .performance import build_performance_contribution
except ImportError:
    from database import LOCAL_TZ, local_today_iso
    from discipline import _holding_rows, build_discipline_report, get_policy
    from performance import build_performance_contribution

# Fine-category concentration warn threshold (single module constant; not policy yet).
CATEGORY_CONCENTRATION_WARN_PCT = 35.0

# Homogeneity: coarse tags (not official industry classification).
HOMOGENEITY_TAGS: List[Tuple[str, List[str], List[str]]] = [
    ("红利/高股息", ["港股ETF", "A股ETF", "A股权益"], [r"红利", r"高股息", r"股息"]),
    ("银行", ["A股权益", "A股ETF"], [r"银行", r"农行", r"工行", r"建行", r"中行"]),
    ("石油/能源", ["A股权益", "A股ETF"], [r"石化", r"石油", r"油气"]),
    ("黄金", ["黄金"], [r"黄金"]),
    ("REITs", ["REITs"], [r"REIT", r"REITs"]),
    ("债/货币", ["债基"], [r"债", r"货币", r"丰享"]),
]

HOMOGENEITY_EQUITY_WARN_PCT = 50.0
PROFIT_DEPENDENCY_WARN_SHARE = 0.70
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


def _build_homogeneity(
    holdings: List[Dict[str, Any]], total_assets: float, equity_mv: float
) -> Dict[str, Any]:
    groups: List[Dict[str, Any]] = []
    for tag, cat_subs, name_res in HOMOGENEITY_TAGS:
        matched = []
        for h in holdings:
            cat = str(h.get("category") or "")
            name = str(h.get("name") or "")
            cat_ok = (not cat_subs) or any(s in cat for s in cat_subs) or cat in cat_subs
            # Allow match by name regex even if category slightly off, when name hits.
            name_ok = any(re.search(rx, name, re.I) for rx in name_res)
            if name_ok or (cat_ok and any(re.search(rx, name, re.I) for rx in name_res)):
                # Prefer explicit name hit; also include pure category membership for 黄金/REITs/债基.
                if name_ok or cat in cat_subs or any(s == cat for s in cat_subs):
                    matched.append(h)
                elif cat_ok and tag in ("黄金", "REITs", "债/货币"):
                    matched.append(h)
        # Deduplicate by code
        by_code = {}
        for h in matched:
            by_code[str(h.get("code") or id(h))] = h
        matched = list(by_code.values())
        if not matched:
            continue
        mv = sum(float(h.get("market_value") or 0) for h in matched)
        pct_total = (mv / total_assets * 100.0) if total_assets > 0 else 0.0
        pct_eq = (mv / equity_mv * 100.0) if equity_mv > 0 else 0.0
        level = "ok"
        if len(matched) >= 2 and pct_eq >= HOMOGENEITY_EQUITY_WARN_PCT:
            level = "warning"
        elif len(matched) >= 2 and pct_eq >= 30:
            level = "info"
        groups.append(
            {
                "tag": tag,
                "codes": [str(h.get("code") or "") for h in matched],
                "names": [str(h.get("name") or h.get("code") or "") for h in matched],
                "pct_of_equity": round(pct_eq, 2),
                "pct_of_total": round(pct_total, 2),
                "level": level,
            }
        )
    groups.sort(key=lambda g: g["pct_of_total"], reverse=True)
    return {
        "groups": groups,
        "note": "标签粗分（名称/品类关键词），不是官方行业分类",
    }


def _build_profit_dependency(conn) -> Dict[str, Any]:
    rows = build_performance_contribution(conn) or []
    positive = [r for r in rows if float(r.get("total_contribution") or 0) > 0]
    positive.sort(key=lambda r: float(r.get("total_contribution") or 0), reverse=True)
    pos_sum = sum(float(r.get("total_contribution") or 0) for r in positive)
    abs_sum = sum(abs(float(r.get("total_contribution") or 0)) for r in rows) or 0.0

    top = positive[:2]
    top_names = [str(r.get("name") or r.get("code") or "") for r in top]
    top_pos = sum(float(r.get("total_contribution") or 0) for r in top)
    top_abs = sum(abs(float(r.get("total_contribution") or 0)) for r in top)
    share_pos = (top_pos / pos_sum) if pos_sum > 0 else 0.0
    share_abs = (top_abs / abs_sum) if abs_sum > 0 else 0.0

    level = "ok"
    if len(positive) >= 2 and share_pos >= PROFIT_DEPENDENCY_WARN_SHARE:
        level = "warning"
    elif len(positive) >= 1 and share_pos >= 0.5:
        level = "info"

    if not top_names:
        text = "当前仓没有明显正贡献，谈不上收益集中。"
    elif level == "warning":
        text = (
            f"正贡献主要靠「{'、'.join(top_names)}」，约占全部正贡献的 {share_pos * 100:.0f}%，"
            f"赚钱过于集中。"
        )
    else:
        text = (
            f"前两大正贡献「{'、'.join(top_names)}」约占正贡献 {share_pos * 100:.0f}%"
            f"（口径：当前仓浮盈+分红）。"
        )

    return {
        "top_names": top_names,
        "top_share_of_positive": round(share_pos, 4),
        "top_share_of_abs": round(share_abs, 4),
        "level": level,
        "text": text,
    }


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
    headline, severity, bullets = _build_headline(
        snapshot, policy_slice, issues, concentration
    )

    equity_mv = float(snapshot.get("equity_mv") or 0)
    homogeneity = _build_homogeneity(holdings, total_assets, equity_mv)
    profit_dependency = _build_profit_dependency(conn)
    liquidity = _build_liquidity(conn, snapshot)
    scenarios = _build_scenarios(snapshot)

    # Attach UI type for frontend convenience on health
    health_ui = []
    for h in health:
        item = dict(h)
        item["type"] = _level_to_ui_type(str(h.get("level") or "ok"))
        health_ui.append(item)

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
        "homogeneity": homogeneity,
        "profit_dependency": profit_dependency,
        "liquidity": liquidity,
        "scenarios": scenarios,
        "expected_return": {
            "portfolio_pct": None,
            "note": "预计年化仍由前端按持仓加权；此处不重复计算以免双口径",
        },
        "discipline_summary": report.get("summary") or "",
        "open_draft_count": int(report.get("open_draft_count") or 0),
        "generated_at": generated,
    }
