"""Portfolio discipline rules + rebalance checklist over real holdings.

Read-only by default. Optional drafts are stored separately and only become
real transactions when the user explicitly confirms.
"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from .csv_utils import create_safety_backup
    from .database import LOCAL_TZ, local_today_iso
    from .holdings import (
        current_holding_quantity,
        infer_category,
        recalc_holdings,
        validate_transaction_payload,
    )
    from .portfolio_totals import compute_portfolio_totals
except ImportError:
    from csv_utils import create_safety_backup
    from database import LOCAL_TZ, local_today_iso
    from holdings import (
        current_holding_quantity,
        infer_category,
        recalc_holdings,
        validate_transaction_payload,
    )
    from portfolio_totals import compute_portfolio_totals

POLICY_KEY = "discipline_policy"
DRAFT_REMARK_PREFIX = "[纪律草稿]"

# Defaults aligned with app's existing allocation health checks + user habits.
DEFAULT_POLICY: Dict[str, Any] = {
    "equity_min_pct": 35.0,
    "equity_max_pct": 55.0,
    "defensive_min_pct": 40.0,
    "single_holding_max_pct": 20.0,
    "named_limits": [
        {"code": "000651", "name": "格力电器", "max_pct": 15.0},
    ],
    "targets": {
        "equity_pct": 45.0,
        "fixed_income_pct": 30.0,
        "deposit_pct": 25.0,
    },
    "rebalance_band_pct": 3.0,
    "preferred_buy_code": "159352",
    "preferred_buy_name": "中证A500ETF",
    "preferred_buy_category": "A股ETF",
    "preferred_buy_account": "华泰证券",
    "no_new_codes": ["000651", "601288", "600028"],  # 格力/农行/石化 默认不建议新开仓
    # 计入「固收」大类的品类（其余非存款进权益）。可在参数里改。
    "fixed_income_categories": ["债基", "证券现金", "基金申购在途"],
    # 额外算进「防守」的权益品类（不改大类饼图，只抬高防守占比）
    "defensive_extra_categories": [],
    # 个人计划（与再平衡建议并列，偏人话提醒）
    "plans": {
        "a500_batch_target_amount": 200000.0,  # 计划分批买入 A500 总额
        "a500_batch_code": "159352",
        "a500_batch_name": "中证A500ETF",
        "gree_code": "000651",
        "gree_name": "格力电器",
        "gree_soft_max_pct": 15.0,  # 超此占比提示减仓
    },
}


def ensure_discipline_tables(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS discipline_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            category TEXT,
            account TEXT DEFAULT '华泰证券',
            side TEXT NOT NULL,
            quantity REAL DEFAULT 0,
            price REAL DEFAULT 0,
            amount REAL NOT NULL,
            fee REAL DEFAULT 0,
            reason TEXT,
            status TEXT DEFAULT 'draft',
            created_at DATETIME,
            confirmed_at DATETIME,
            transaction_id INTEGER
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_discipline_drafts_status_code_side "
        "ON discipline_drafts(status, code, side)"
    )


def _row_to_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(row)


def _get_setting(conn, key: str, default: str = "") -> str:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    except Exception:
        return default
    if not row:
        return default
    val = row["value"] if isinstance(row, sqlite3.Row) else row[0]
    return "" if val is None else str(val)


def _set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _finite(value: Any, name: str) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是数字") from exc
    if not math.isfinite(n):
        raise ValueError(f"{name} 无效")
    return n


def get_policy(conn) -> Dict[str, Any]:
    raw = _get_setting(conn, POLICY_KEY, "")
    if not raw:
        return json.loads(json.dumps(DEFAULT_POLICY))
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return json.loads(json.dumps(DEFAULT_POLICY))
        return _deep_merge(DEFAULT_POLICY, data)
    except Exception:
        return json.loads(json.dumps(DEFAULT_POLICY))


def set_policy(conn, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("policy 必须是对象")
    merged = _deep_merge(get_policy(conn), payload)

    for key in (
        "equity_min_pct",
        "equity_max_pct",
        "defensive_min_pct",
        "single_holding_max_pct",
        "rebalance_band_pct",
    ):
        if key in merged:
            merged[key] = _finite(merged[key], key)
            if merged[key] < 0 or merged[key] > 100:
                raise ValueError(f"{key} 需在 0–100 之间")

    if float(merged["equity_min_pct"]) > float(merged["equity_max_pct"]):
        raise ValueError("权益下限不能高于上限")

    targets = dict(merged.get("targets") or {})
    for key in ("equity_pct", "fixed_income_pct", "deposit_pct"):
        if key in targets:
            targets[key] = _finite(targets[key], f"targets.{key}")
            if targets[key] < 0 or targets[key] > 100:
                raise ValueError(f"目标 {key} 需在 0–100 之间")
    t_sum = (
        float(targets.get("equity_pct") or 0)
        + float(targets.get("fixed_income_pct") or 0)
        + float(targets.get("deposit_pct") or 0)
    )
    if abs(t_sum - 100.0) > 0.51:
        raise ValueError(f"目标权益+固收+存款应约等于 100%（当前 {t_sum:.1f}%）")
    merged["targets"] = targets

    if "preferred_buy_code" in merged:
        merged["preferred_buy_code"] = str(merged.get("preferred_buy_code") or "").strip()
    if not merged.get("preferred_buy_code"):
        raise ValueError("优先加仓代码不能为空")

    for list_key in ("named_limits", "no_new_codes", "fixed_income_categories", "defensive_extra_categories"):
        if list_key in merged and merged[list_key] is None:
            merged[list_key] = []

    plans = dict(merged.get("plans") or {})
    if "a500_batch_target_amount" in plans:
        plans["a500_batch_target_amount"] = max(0.0, _finite(plans["a500_batch_target_amount"], "plans.a500_batch_target_amount"))
    if "gree_soft_max_pct" in plans:
        g = _finite(plans["gree_soft_max_pct"], "plans.gree_soft_max_pct")
        if g < 0 or g > 100:
            raise ValueError("格力软上限需在 0–100 之间")
        plans["gree_soft_max_pct"] = g
    for k in ("a500_batch_code", "a500_batch_name", "gree_code", "gree_name"):
        if k in plans and plans[k] is not None:
            plans[k] = str(plans[k]).strip()
    merged["plans"] = plans

    _set_setting(conn, POLICY_KEY, json.dumps(merged, ensure_ascii=False))
    return merged


def _macro_group(category: str, policy: Optional[Dict[str, Any]] = None) -> str:
    cat = str(category or "")
    policy = policy or DEFAULT_POLICY
    fixed = set(policy.get("fixed_income_categories") or ["债基", "证券现金", "基金申购在途"])
    if cat in fixed:
        return "固收"
    if cat in ("银行存款",):
        return "存款"
    return "权益"


def _is_defensive_holding(h: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    if h.get("macro") in ("固收", "存款"):
        return True
    extra = set(policy.get("defensive_extra_categories") or [])
    return str(h.get("category") or "") in extra


def _latest_account_for_code(conn, code: str, default: str = "华泰证券") -> str:
    code = str(code or "").strip()
    if not code:
        return default
    try:
        row = conn.execute(
            """
            SELECT account FROM transactions
            WHERE code = ? AND account IS NOT NULL AND TRIM(account) != ''
            ORDER BY date DESC, id DESC LIMIT 1
            """,
            (code,),
        ).fetchone()
    except Exception:
        return default
    if not row:
        return default
    acct = row["account"] if isinstance(row, sqlite3.Row) else row[0]
    return str(acct or default).strip() or default


def _holding_rows(conn, policy: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    policy = policy or DEFAULT_POLICY
    pref_acct = str(policy.get("preferred_buy_account") or "华泰证券")
    rows = conn.execute(
        """
        SELECT code, name, category, quantity, last_price, avg_cost, diluted_cost, total_dividend
        FROM holdings WHERE quantity > 0
        """
    ).fetchall()
    out = []
    for r in rows:
        h = _row_to_dict(r)
        qty = float(h.get("quantity") or 0)
        price = float(h.get("last_price") or 0)
        mv = qty * price
        h["market_value"] = mv
        h["macro"] = _macro_group(h.get("category") or "", policy)
        h["account"] = _latest_account_for_code(conn, h.get("code") or "", pref_acct)
        out.append(h)
    return out


def build_discipline_report(conn) -> Dict[str, Any]:
    """Evaluate real portfolio against policy; return breaches + rebalance actions."""
    ensure_discipline_tables(conn)
    policy = get_policy(conn)
    totals = compute_portfolio_totals(conn)
    total_assets = float(totals.get("total_assets") or 0)
    market_value = float(totals.get("total_market_value") or 0)
    bank = float(totals.get("bank_balance") or 0)
    cash = float(totals.get("securities_cash") or 0)
    pending = float(totals.get("pending_purchase") or 0)
    holdings = _holding_rows(conn, policy)

    equity_mv = sum(h["market_value"] for h in holdings if h["macro"] == "权益")
    fixed_holdings = sum(h["market_value"] for h in holdings if h["macro"] == "固收")
    fixed_mv = fixed_holdings + cash + pending
    deposit_mv = bank
    defensive_extra_mv = sum(
        h["market_value"]
        for h in holdings
        if h["macro"] == "权益" and _is_defensive_holding(h, policy)
    )

    def pct(part: float) -> float:
        return (part / total_assets * 100.0) if total_assets > 0 else 0.0

    equity_pct = pct(equity_mv)
    fixed_pct = pct(fixed_mv)
    deposit_pct = pct(deposit_mv)
    defensive_pct = pct(fixed_mv + deposit_mv + defensive_extra_mv)

    breaches: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []

    eq_min = float(policy.get("equity_min_pct") or 35)
    eq_max = float(policy.get("equity_max_pct") or 55)
    def_min = float(policy.get("defensive_min_pct") or 40)
    single_max = float(policy.get("single_holding_max_pct") or 20)

    if equity_pct > eq_max:
        breaches.append(
            {
                "level": "warning",
                "code": "equity_high",
                "title": "权益偏高",
                "text": f"权益约 {equity_pct:.1f}%（上限 {eq_max:.0f}%），回撤时波动会更大。",
            }
        )
    elif equity_pct < eq_min:
        breaches.append(
            {
                "level": "info",
                "code": "equity_low",
                "title": "权益偏低",
                "text": f"权益约 {equity_pct:.1f}%（下限 {eq_min:.0f}%），更稳但长期弹性可能不足。",
            }
        )
    else:
        breaches.append(
            {
                "level": "ok",
                "code": "equity_ok",
                "title": "权益适中",
                "text": f"权益约 {equity_pct:.1f}%，在 {eq_min:.0f}%–{eq_max:.0f}% 区间内。",
            }
        )

    if defensive_pct < def_min:
        breaches.append(
            {
                "level": "warning",
                "code": "defensive_low",
                "title": "防守偏少",
                "text": f"固收+存款约 {defensive_pct:.1f}%（建议 ≥ {def_min:.0f}%）。",
            }
        )
    else:
        breaches.append(
            {
                "level": "ok",
                "code": "defensive_ok",
                "title": "防守充足",
                "text": f"固收+存款约 {defensive_pct:.1f}%。",
            }
        )

    for h in sorted(holdings, key=lambda x: x["market_value"], reverse=True):
        share = pct(h["market_value"])
        if share > single_max + 1e-9:
            breaches.append(
                {
                    "level": "warning",
                    "code": "holding_concentrated",
                    "title": f"{h.get('name') or h.get('code')} 过重",
                    "text": f"约占总额 {share:.1f}%（单票上限 {single_max:.0f}%），市值约 {h['market_value']:.0f}。",
                    "code_ref": h.get("code"),
                }
            )

    for lim in policy.get("named_limits") or []:
        code = str(lim.get("code") or "").strip()
        max_p = float(lim.get("max_pct") or 0)
        if not code or max_p <= 0:
            continue
        h = next((x for x in holdings if str(x.get("code")) == code), None)
        if not h:
            continue
        share = pct(h["market_value"])
        if share > max_p + 1e-9:
            breaches.append(
                {
                    "level": "warning",
                    "code": "named_limit",
                    "title": f"{h.get('name') or code} 超个人上限",
                    "text": f"约占 {share:.1f}%（你设的上限 {max_p:.0f}%）。建议减到上限附近。",
                    "code_ref": code,
                }
            )
            target_mv = total_assets * max_p / 100.0
            sell_mv = max(h["market_value"] - target_mv, 0)
            price = float(h.get("last_price") or 0)
            qty = (sell_mv / price) if price > 0 else 0
            if sell_mv >= 100:
                actions.append(
                    {
                        "side": "sell",
                        "priority": 1,
                        "code": code,
                        "name": h.get("name") or code,
                        "category": h.get("category") or "",
                        "account": h.get("account") or policy.get("preferred_buy_account") or "华泰证券",
                        "amount": round(sell_mv, 2),
                        "quantity": round(qty, 4) if qty else 0,
                        "price": price,
                        "reason": f"降至个人上限 {max_p:.0f}%（当前 {share:.1f}%）"
                        + ("；无现价，确认前请补数量" if price <= 0 else ""),
                        "source": "named_limit",
                        "needs_manual_qty": price <= 0,
                    }
                )

    named_codes = {str(x.get("code") or "") for x in (policy.get("named_limits") or [])}
    for h in sorted(holdings, key=lambda x: x["market_value"], reverse=True):
        code = str(h.get("code") or "")
        if code in named_codes:
            continue
        share = pct(h["market_value"])
        if share <= single_max:
            continue
        target_mv = total_assets * single_max / 100.0
        sell_mv = max(h["market_value"] - target_mv, 0)
        price = float(h.get("last_price") or 0)
        qty = (sell_mv / price) if price > 0 else 0
        if sell_mv >= 100:
            actions.append(
                {
                    "side": "sell",
                    "priority": 2,
                    "code": code,
                    "name": h.get("name") or code,
                    "category": h.get("category") or "",
                    "account": h.get("account") or "华泰证券",
                    "amount": round(sell_mv, 2),
                    "quantity": round(qty, 4) if qty else 0,
                    "price": price,
                    "reason": f"单票占比 {share:.1f}% > {single_max:.0f}%"
                    + ("；无现价，确认前请补数量" if price <= 0 else ""),
                    "source": "single_max",
                    "needs_manual_qty": price <= 0,
                }
            )

    targets = policy.get("targets") or {}
    band = float(policy.get("rebalance_band_pct") or 3)
    t_eq = float(targets.get("equity_pct") or 45)
    t_fi = float(targets.get("fixed_income_pct") or 30)
    t_dep = float(targets.get("deposit_pct") or 25)

    gaps = {
        "equity": t_eq - equity_pct,
        "fixed_income": t_fi - fixed_pct,
        "deposit": t_dep - deposit_pct,
    }

    pref_code = str(policy.get("preferred_buy_code") or "159352").strip()
    pref_name = str(policy.get("preferred_buy_name") or pref_code)
    pref_cat = str(policy.get("preferred_buy_category") or "A股ETF")
    pref_acct = str(policy.get("preferred_buy_account") or "华泰证券")
    no_new = {str(c).strip() for c in (policy.get("no_new_codes") or [])}

    if gaps["equity"] > band and total_assets > 0:
        need_mv = total_assets * gaps["equity"] / 100.0
        from_cash = min(max(cash, 0), need_mv)
        from_deposit = max(need_mv - from_cash, 0)
        buy_amt = from_cash + min(from_deposit, max(bank, 0))
        pref_h = next((x for x in holdings if str(x.get("code")) == pref_code), None)
        price = float(pref_h["last_price"]) if pref_h and pref_h.get("last_price") else 0
        qty = (buy_amt / price) if price > 0 else 0
        if buy_amt >= 100:
            fund_note = []
            if from_cash >= 1:
                fund_note.append(f"证券现金约可用 {from_cash:.0f}")
            if from_deposit >= 1:
                fund_note.append(f"存款侧约可挪 {min(from_deposit, bank):.0f}")
            actions.append(
                {
                    "side": "buy",
                    "priority": 3,
                    "code": pref_code,
                    "name": pref_name,
                    "category": pref_cat,
                    "account": pref_acct,
                    "amount": round(buy_amt, 2),
                    "quantity": round(qty, 4) if qty else 0,
                    "price": price,
                    "reason": (
                        f"权益 {equity_pct:.1f}% 低于目标 {t_eq:.0f}%（带宽 {band:.0f}%）；"
                        + "；".join(fund_note)
                    ),
                    "source": "rebalance_equity_up",
                    "use_pending_direction": True,
                }
            )

    if gaps["equity"] < -band and total_assets > 0:
        reduce_mv = total_assets * abs(gaps["equity"]) / 100.0
        already = {a["code"] for a in actions if a.get("side") == "sell"}
        equity_holdings = [h for h in holdings if h["macro"] == "权益" and h["code"] not in already]
        equity_holdings.sort(key=lambda x: x["market_value"], reverse=True)
        remaining = reduce_mv
        for h in equity_holdings:
            if remaining < 100:
                break
            price = float(h.get("last_price") or 0)
            sell_mv = min(remaining, h["market_value"] * 0.5)
            if sell_mv < 100:
                continue
            qty = (sell_mv / price) if price > 0 else 0
            actions.append(
                {
                    "side": "sell",
                    "priority": 4,
                    "code": h.get("code"),
                    "name": h.get("name") or h.get("code"),
                    "category": h.get("category") or "",
                    "account": h.get("account") or pref_acct,
                    "amount": round(sell_mv, 2),
                    "quantity": round(qty, 4) if qty else 0,
                    "price": price,
                    "reason": f"权益 {equity_pct:.1f}% 高于目标 {t_eq:.0f}%，建议减一部分"
                    + ("；无现价，确认前请补数量" if price <= 0 else ""),
                    "source": "rebalance_equity_down",
                    "needs_manual_qty": price <= 0,
                }
            )
            remaining -= sell_mv

    if gaps["deposit"] < -band and gaps["equity"] > 0 and total_assets > 0:
        move = min(bank, total_assets * abs(gaps["deposit"]) / 100.0)
        if move >= 1000 and not any(a.get("source") == "rebalance_equity_up" for a in actions):
            actions.append(
                {
                    "side": "buy",
                    "priority": 5,
                    "code": pref_code,
                    "name": pref_name,
                    "category": pref_cat,
                    "account": pref_acct,
                    "amount": round(move, 2),
                    "quantity": 0,
                    "price": 0,
                    "reason": f"存款占比 {deposit_pct:.1f}% 高于目标 {t_dep:.0f}%，可分批挪向 {pref_name}",
                    "source": "rebalance_deposit_to_equity",
                    "use_pending_direction": True,
                }
            )

    filtered_actions = []
    for a in actions:
        if a.get("side") == "buy" and a.get("code") in no_new and a.get("code") != pref_code:
            continue
        filtered_actions.append(a)

    filtered_actions.sort(key=lambda x: (int(x.get("priority") or 99), -float(x.get("amount") or 0)))

    # --- personal plans (A500 batch / Gree soft cap) ---
    plans = policy.get("plans") or {}
    plan_items: List[Dict[str, Any]] = []
    a500_code = str(plans.get("a500_batch_code") or pref_code or "159352").strip()
    a500_name = str(plans.get("a500_batch_name") or pref_name or a500_code)
    a500_target = float(plans.get("a500_batch_target_amount") or 0)
    a500_h = next((x for x in holdings if str(x.get("code")) == a500_code), None)
    a500_mv = float(a500_h["market_value"]) if a500_h else 0.0
    a500_gap = max(a500_target - a500_mv, 0.0) if a500_target > 0 else 0.0
    if a500_target > 0:
        if a500_gap >= 100:
            plan_items.append(
                {
                    "code": "a500_batch",
                    "level": "info",
                    "title": f"{a500_name} 分批计划",
                    "text": (
                        f"目标约 {a500_target:.0f} 元，当前市值约 {a500_mv:.0f}，"
                        f"还差约 {a500_gap:.0f}。可优先用证券现金/存款分批申购，不必一次买完。"
                    ),
                    "remaining_amount": round(a500_gap, 2),
                    "current_amount": round(a500_mv, 2),
                    "target_amount": round(a500_target, 2),
                    "symbol": a500_code,
                }
            )
        else:
            plan_items.append(
                {
                    "code": "a500_batch_done",
                    "level": "ok",
                    "title": f"{a500_name} 分批计划",
                    "text": f"目标约 {a500_target:.0f} 元，当前市值约 {a500_mv:.0f}，计划基本到位。",
                    "remaining_amount": 0,
                    "current_amount": round(a500_mv, 2),
                    "target_amount": round(a500_target, 2),
                    "symbol": a500_code,
                }
            )

    gree_code = str(plans.get("gree_code") or "000651").strip()
    gree_name = str(plans.get("gree_name") or "格力电器")
    gree_soft = float(plans.get("gree_soft_max_pct") or 15)
    gree_h = next((x for x in holdings if str(x.get("code")) == gree_code), None)
    if gree_h and total_assets > 0 and gree_soft > 0:
        gree_share = pct(gree_h["market_value"])
        if gree_share > gree_soft + 1e-9:
            target_mv = total_assets * gree_soft / 100.0
            sell_mv = max(gree_h["market_value"] - target_mv, 0)
            plan_items.append(
                {
                    "code": "gree_reduce",
                    "level": "warning",
                    "title": f"{gree_name} 减仓提醒",
                    "text": (
                        f"约占总额 {gree_share:.1f}%（软上限 {gree_soft:.0f}%），"
                        f"建议减约 {sell_mv:.0f} 元到上限附近；是否动手看你自己节奏。"
                    ),
                    "remaining_amount": round(sell_mv, 2),
                    "current_pct": round(gree_share, 2),
                    "target_pct": gree_soft,
                    "symbol": gree_code,
                }
            )
        else:
            plan_items.append(
                {
                    "code": "gree_ok",
                    "level": "ok",
                    "title": f"{gree_name} 占比",
                    "text": f"约占 {gree_share:.1f}%，在软上限 {gree_soft:.0f}% 以内。",
                    "current_pct": round(gree_share, 2),
                    "target_pct": gree_soft,
                    "symbol": gree_code,
                }
            )

    warn_n = sum(1 for b in breaches if b.get("level") == "warning")
    plan_warn = sum(1 for p in plan_items if p.get("level") == "warning")
    if warn_n or plan_warn:
        summary = (
            f"有 {warn_n} 条纪律提醒"
            + (f"、{plan_warn} 条个人计划提醒" if plan_warn else "")
            + f"；再平衡建议 {len(filtered_actions)} 条（仅建议，不自动下单）。"
        )
    elif filtered_actions:
        summary = f"纪律总体还行；按目标比例有 {len(filtered_actions)} 条再平衡建议。"
    else:
        summary = "纪律与目标比例都大致合适，暂无必须动作。"

    open_drafts = conn.execute(
        "SELECT COUNT(*) AS c FROM discipline_drafts WHERE status = 'draft'"
    ).fetchone()
    open_draft_count = int(open_drafts["c"] if isinstance(open_drafts, sqlite3.Row) else open_drafts[0])

    help_notes = [
        "本页默认只读：点「建议→草稿」不会改账，只有「确认入账」才写真实交易。",
        "买入金额类确认后一般记为「申购待确认」，份额确认后再改成买入。",
        "券商下单仍需你自己操作；这里只帮你记建议和账本草稿。",
        "改参数会影响纪律提醒和再平衡建议，保存后立即生效。",
        f"默认优先加仓 {pref_name}（{pref_code}）；格力等可设个人上限。",
    ]

    return {
        "policy": policy,
        "snapshot": {
            "total_assets": round(total_assets, 2),
            "market_value": round(market_value, 2),
            "equity_mv": round(equity_mv, 2),
            "fixed_mv": round(fixed_mv, 2),
            "deposit_mv": round(deposit_mv, 2),
            "securities_cash": round(cash, 2),
            "pending_purchase": round(pending, 2),
            "equity_pct": round(equity_pct, 2),
            "fixed_income_pct": round(fixed_pct, 2),
            "deposit_pct": round(deposit_pct, 2),
            "defensive_pct": round(defensive_pct, 2),
        },
        "targets": {
            "equity_pct": t_eq,
            "fixed_income_pct": t_fi,
            "deposit_pct": t_dep,
            "band_pct": band,
        },
        "gaps_pct": {k: round(v, 2) for k, v in gaps.items()},
        "breaches": breaches,
        "actions": filtered_actions,
        "plans": plan_items,
        "help_notes": help_notes,
        "summary": summary,
        "open_draft_count": open_draft_count,
        "generated_at": datetime.now(LOCAL_TZ).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds"),
    }


def list_drafts(conn, status: Optional[str] = "draft") -> List[Dict[str, Any]]:
    ensure_discipline_tables(conn)
    if status:
        rows = conn.execute(
            "SELECT * FROM discipline_drafts WHERE status = ? ORDER BY id DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM discipline_drafts ORDER BY id DESC LIMIT 200"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _find_open_draft(conn, code: str, side: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """
        SELECT * FROM discipline_drafts
        WHERE status = 'draft' AND code = ? AND side = ?
        ORDER BY id DESC LIMIT 1
        """,
        (code, side),
    ).fetchone()
    return _row_to_dict(row) if row else None


def create_drafts_from_actions(
    conn,
    actions: Optional[List[Dict[str, Any]]] = None,
    *,
    use_report_actions: bool = True,
    replace_existing: bool = True,
) -> Dict[str, Any]:
    """Persist suggested actions as drafts. Does not write real transactions.

    Same code+side open draft is updated (or skipped) to avoid double-confirm risk.
    """
    ensure_discipline_tables(conn)
    if actions is None and use_report_actions:
        report = build_discipline_report(conn)
        actions = report.get("actions") or []
    actions = actions or []
    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    today = local_today_iso()
    created = []
    updated = []
    skipped = []

    for a in actions:
        side = str(a.get("side") or "").lower()
        if side not in ("buy", "sell"):
            continue
        code = str(a.get("code") or "").strip()
        amount = float(a.get("amount") or 0)
        if not code or amount <= 0:
            continue

        existing = _find_open_draft(conn, code, side)
        qty = float(a.get("quantity") or 0)
        price = float(a.get("price") or 0)
        name = a.get("name") or code
        category = a.get("category") or ""
        account = a.get("account") or "华泰证券"
        reason = a.get("reason") or ""

        if existing and not replace_existing:
            skipped.append({"id": existing.get("id"), "code": code, "side": side, "reason": "已有未确认草稿"})
            continue

        if existing and replace_existing:
            conn.execute(
                """
                UPDATE discipline_drafts
                SET date=?, name=?, category=?, account=?, quantity=?, price=?, amount=?, fee=0,
                    reason=?, created_at=?
                WHERE id=?
                """,
                (today, name, category, account, qty, price, amount, reason, now, existing["id"]),
            )
            row = conn.execute(
                "SELECT * FROM discipline_drafts WHERE id = ?", (existing["id"],)
            ).fetchone()
            updated.append(_row_to_dict(row))
            continue

        cur = conn.execute(
            """
            INSERT INTO discipline_drafts
                (date, code, name, category, account, side, quantity, price, amount, fee, reason, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'draft', ?)
            """,
            (today, code, name, category, account, side, qty, price, amount, reason, now),
        )
        did = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM discipline_drafts WHERE id = ?", (did,)).fetchone()
        created.append(_row_to_dict(row))

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "count": len(created) + len(updated),
        "created_count": len(created),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
    }


def delete_draft(conn, draft_id: int) -> bool:
    ensure_discipline_tables(conn)
    cur = conn.execute(
        "DELETE FROM discipline_drafts WHERE id = ? AND status = 'draft'",
        (draft_id,),
    )
    return cur.rowcount > 0


def update_draft(conn, draft_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Edit an open draft (quantity/price/amount/reason/...). Confirmed drafts are frozen."""
    ensure_discipline_tables(conn)
    row = conn.execute("SELECT * FROM discipline_drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        raise KeyError("草稿不存在")
    d = _row_to_dict(row)
    if d.get("status") != "draft":
        raise ValueError("已确认草稿不能修改")

    fields = {}
    if "quantity" in payload and payload["quantity"] is not None:
        fields["quantity"] = max(0.0, float(payload["quantity"]))
    if "price" in payload and payload["price"] is not None:
        fields["price"] = max(0.0, float(payload["price"]))
    if "amount" in payload and payload["amount"] is not None:
        fields["amount"] = float(payload["amount"])
        if fields["amount"] <= 0:
            raise ValueError("金额必须大于 0")
    if "fee" in payload and payload["fee"] is not None:
        fields["fee"] = max(0.0, float(payload["fee"]))
    if "reason" in payload and payload["reason"] is not None:
        fields["reason"] = str(payload["reason"])
    if "account" in payload and payload["account"] is not None:
        fields["account"] = str(payload["account"] or "华泰证券").strip() or "华泰证券"
    if "name" in payload and payload["name"] is not None:
        fields["name"] = str(payload["name"] or d.get("code") or "")
    if "category" in payload and payload["category"] is not None:
        fields["category"] = str(payload["category"] or "")
    if "date" in payload and payload["date"] is not None:
        fields["date"] = str(payload["date"])[:10]
    if "side" in payload and payload["side"] is not None:
        side = str(payload["side"]).lower().strip()
        if side not in ("buy", "sell"):
            raise ValueError("side 必须是 buy 或 sell")
        fields["side"] = side

    # If qty+price set and amount omitted, keep amount in sync for sells/buys with shares
    qty = float(fields.get("quantity", d.get("quantity") or 0) or 0)
    price = float(fields.get("price", d.get("price") or 0) or 0)
    if "amount" not in fields and qty > 0 and price > 0:
        fields["amount"] = round(qty * price, 2)
    if "amount" in fields and float(fields["amount"]) <= 0:
        raise ValueError("金额必须大于 0")
    if not fields:
        raise ValueError("没有可更新的字段")

    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [draft_id]
    conn.execute(f"UPDATE discipline_drafts SET {sets} WHERE id = ? AND status = 'draft'", vals)
    updated = conn.execute("SELECT * FROM discipline_drafts WHERE id = ?", (draft_id,)).fetchone()
    return _row_to_dict(updated)


def confirm_draft(conn, draft_id: int, *, make_backup: bool = True) -> Dict[str, Any]:
    """Turn one draft into a real transaction (user-confirmed only)."""
    ensure_discipline_tables(conn)
    row = conn.execute("SELECT * FROM discipline_drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        raise KeyError("草稿不存在")
    d = _row_to_dict(row)
    if d.get("status") != "draft":
        raise ValueError("草稿已处理，不能重复确认")

    side = str(d.get("side") or "").lower()
    code = str(d.get("code") or "").strip()
    name = str(d.get("name") or code)
    category = str(d.get("category") or "") or infer_category(code, name)
    account = str(d.get("account") or "华泰证券")
    amount = float(d.get("amount") or 0)
    qty = float(d.get("quantity") or 0)
    price = float(d.get("price") or 0)
    date = str(d.get("date") or local_today_iso())[:10]
    reason = str(d.get("reason") or "")
    remark = f"{DRAFT_REMARK_PREFIX} {reason}".strip()

    if side == "buy":
        # amount-based fund buy → 申购待确认 (safe, no phantom shares)
        if qty <= 0 or price <= 0:
            direction = "申购待确认"
            qty = 0.0
            price = 0.0
            if amount <= 0:
                raise ValueError("买入金额必须大于 0")
        else:
            direction = "买入"
            amount = qty * price
    elif side == "sell":
        direction = "卖出"
        if qty <= 0 and price > 0 and amount > 0:
            qty = amount / price
        if qty <= 0:
            raise ValueError("卖出需要数量：当前无可用现价估算，请先同步最新价或手改草稿数量后再确认")
        if price <= 0:
            price = amount / qty if qty else 0
        # re-check live holding and cap to available
        available = current_holding_quantity(conn, code)
        if qty > available + 1e-6:
            if available <= 1e-6:
                raise ValueError(f"卖出失败：{code} 当前无持仓")
            qty = available
        amount = qty * price if price > 0 else amount
    else:
        raise ValueError("side 必须是 buy 或 sell")

    payload = {
        "date": date,
        "code": code,
        "name": name,
        "category": category,
        "account": account,
        "direction": direction,
        "quantity": qty,
        "price": price,
        "amount": amount,
        "fee": float(d.get("fee") or 0),
        "remark": remark,
    }
    validate_transaction_payload(
        conn,
        direction=direction,
        code=code,
        quantity=qty,
        price=price,
        amount=amount,
        fee=float(d.get("fee") or 0),
        strict_oversell=True,
    )

    backup_path = None
    if make_backup:
        try:
            backup_path = create_safety_backup("before_confirm_discipline_draft")
        except Exception:
            backup_path = None

    cur = conn.execute(
        """
        INSERT INTO transactions
            (date, code, name, category, account, direction, quantity, price, amount, fee, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["date"],
            payload["code"],
            payload["name"],
            payload["category"],
            payload["account"],
            payload["direction"],
            payload["quantity"],
            payload["price"],
            payload["amount"],
            payload["fee"],
            payload["remark"],
        ),
    )
    tx_id = int(cur.lastrowid)
    recalc_holdings(conn, code)
    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    conn.execute(
        """
        UPDATE discipline_drafts
        SET status = 'confirmed', confirmed_at = ?, transaction_id = ?
        WHERE id = ?
        """,
        (now, tx_id, draft_id),
    )
    return {
        "draft_id": draft_id,
        "transaction_id": tx_id,
        "direction": direction,
        "payload": payload,
        "backup": backup_path,
    }


def confirm_drafts(conn, draft_ids: List[int]) -> Dict[str, Any]:
    results = []
    errors = []
    backup_path = None
    try:
        backup_path = create_safety_backup("before_confirm_discipline_drafts")
    except Exception:
        backup_path = None
    for did in draft_ids:
        try:
            # single shared backup already taken
            results.append(confirm_draft(conn, int(did), make_backup=False))
        except Exception as exc:
            errors.append({"draft_id": did, "error": str(exc)})
    return {
        "confirmed": results,
        "errors": errors,
        "count": len(results),
        "backup": backup_path,
    }
