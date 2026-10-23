"""Portfolio discipline rules + rebalance checklist over real holdings.

Read-only by default. Optional drafts are stored separately and only become
real transactions when the user explicitly confirms.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from .csv_utils import create_safety_backup
    from .database import LOCAL_TZ, local_today_iso
    from .cash import DEFAULT_ACCOUNT
    from .holdings import (
        current_holding_quantity,
        infer_category,
        recalc_holdings,
        validate_holding_history,
        validate_transaction_payload,
    )
    from .portfolio_totals import compute_portfolio_totals
except ImportError:
    from csv_utils import create_safety_backup
    from database import LOCAL_TZ, local_today_iso
    from cash import DEFAULT_ACCOUNT
    from holdings import (
        current_holding_quantity,
        infer_category,
        recalc_holdings,
        validate_holding_history,
        validate_transaction_payload,
    )
    from portfolio_totals import compute_portfolio_totals

logger = logging.getLogger(__name__)

POLICY_KEY = "discipline_policy"
DRAFT_REMARK_PREFIX = "[纪律草稿]"

# 通用默认：只放结构尺子，不放任何具体标的代码。
# 个人化的代码（优先加仓、个股上限、禁开名单、分批计划）都由用户在「调整参数」里填；
# 老库升级时由 schema v21 迁移把此前写死的个人默认固化进库，行为不变。
DEFAULT_POLICY: Dict[str, Any] = {
    "equity_min_pct": 35.0,
    "equity_max_pct": 55.0,
    "defensive_min_pct": 40.0,
    "single_holding_max_pct": 20.0,
    # 个股上限：[{code, name, max_pct}]，超出即提示并给减仓建议
    "named_limits": [],
    "targets": {
        "equity_pct": 45.0,
        "fixed_income_pct": 30.0,
        "deposit_pct": 25.0,
    },
    "rebalance_band_pct": 3.0,
    # 权益偏低时买什么。留空 = 只提示偏低，不生成买入建议
    "preferred_buy_code": "",
    "preferred_buy_name": "",
    "preferred_buy_category": "A股ETF",
    "preferred_buy_account": "",  # 空 = DEFAULT_ACCOUNT
    "no_new_codes": [],  # 不建议新开仓的代码
    # 计入「固收」大类的品类（其余非存款进权益）。可在参数里改。
    "fixed_income_categories": ["债基", "证券现金", "基金申购在途"],
    # 额外算进「防守」的权益品类（不改大类饼图，只抬高防守占比）
    "defensive_extra_categories": [],
    # 一键套用预设 id：defensive | balanced | building | custom/None
    "preset_id": "balanced",
    # 个人计划（与再平衡建议并列，偏人话提醒）
    "plans": {
        # 分批建仓：目标总额 > 0 才启用；代码留空则沿用优先加仓代码
        "batch_buy_code": "",
        "batch_buy_name": "",
        "batch_buy_target_amount": 0.0,
    },
    # 风格桶 / 削弱动作 / 黄金 体检：倾斜"个人资产配置"，默认中性（空清单）。
    # 通用阈值保留；具体代码/标的目标由各用户自己在「调整参数」里配置，
    # 旧库升级时由 schema v12 迁移固化原有行为，不丢。
    "focus": {
        # 高股息同风格桶：这些代码同涨同跌，合计占「权益」超过上限时提示
        "dividend_bucket_codes": [],
        "dividend_bucket_equity_max_pct": 50.0,  # 占权益上限 %
        # 削弱动作：仍持有/超目标 → 提示 "只做了一半"
        "reduce_tasks": [],
        # 黄金占「总资产」目标区间
        "gold_codes": [],
        "gold_target_min_pct": 3.0,
        "gold_target_max_pct": 5.0,
    },
}

# 旧版字段 → 通用字段。读库和写库都过一遍 normalize_legacy_policy，
# 所以老库、老备份、老前端发来的 payload 都能正确落到新结构上。
_LEGACY_PLAN_KEYS = {
    "a500_batch_code": "batch_buy_code",
    "a500_batch_name": "batch_buy_name",
    "a500_batch_target_amount": "batch_buy_target_amount",
}


def normalize_legacy_policy(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把旧版 policy 结构改写成通用结构（幂等，不修改入参）。

    - plans.a500_batch_*  → plans.batch_buy_*（旧键覆盖新键：只有老客户端才会发旧键，它的值就是用户本意）
    - plans.gree_code/gree_name/gree_soft_max_pct（单只股票的软上限）
      → 并入 named_limits；同代码已在 named_limits 里时以 named_limits 为准。
      旧版 UI 本来就把这两个值同步成一样，所以并入后提示口径不变。
    """
    data = dict(raw or {})
    plans = data.get("plans")
    if not isinstance(plans, dict):
        return data
    plans = dict(plans)
    for old, new in _LEGACY_PLAN_KEYS.items():
        if old in plans:
            plans[new] = plans.pop(old)

    soft_code = str(plans.pop("gree_code", "") or "").strip()
    soft_name = str(plans.pop("gree_name", "") or "").strip()
    soft_raw = plans.pop("gree_soft_max_pct", None)
    try:
        soft_pct = float(soft_raw) if soft_raw is not None else 0.0
    except (TypeError, ValueError):
        soft_pct = 0.0
    if soft_code and math.isfinite(soft_pct) and soft_pct > 0:
        limits = [x for x in (data.get("named_limits") or []) if isinstance(x, dict)]
        if not any(str(x.get("code") or "").strip() == soft_code for x in limits):
            limits.append({"code": soft_code, "name": soft_name or soft_code, "max_pct": soft_pct})
            data["named_limits"] = limits

    data["plans"] = plans
    return data


# 一键套用：只改结构尺子，不改优先加仓代码/禁开名单/个股上限等个人设置。
# targets 三项合计必须 = 100。
POLICY_PRESETS: Dict[str, Dict[str, Any]] = {
    "defensive": {
        "id": "defensive",
        "label": "防守",
        "summary": "权益少、现金固收多",
        "detail": "观望期用；单票更严。",
        "policy": {
            "equity_min_pct": 25.0,
            "equity_max_pct": 42.0,
            "defensive_min_pct": 50.0,
            "single_holding_max_pct": 15.0,
            "rebalance_band_pct": 3.0,
            "targets": {
                "equity_pct": 35.0,
                "fixed_income_pct": 35.0,
                "deposit_pct": 30.0,
            },
        },
    },
    "balanced": {
        "id": "balanced",
        "label": "均衡",
        "summary": "默认尺子",
        "detail": "日常体检最省心。",
        "policy": {
            "equity_min_pct": 35.0,
            "equity_max_pct": 55.0,
            "defensive_min_pct": 40.0,
            "single_holding_max_pct": 20.0,
            "rebalance_band_pct": 3.0,
            "targets": {
                "equity_pct": 45.0,
                "fixed_income_pct": 30.0,
                "deposit_pct": 25.0,
            },
        },
    },
    "building": {
        "id": "building",
        "label": "加仓中",
        "summary": "权益目标抬高",
        "detail": "存款分批转股，不是梭哈。",
        "policy": {
            "equity_min_pct": 40.0,
            "equity_max_pct": 60.0,
            "defensive_min_pct": 35.0,
            "single_holding_max_pct": 20.0,
            "rebalance_band_pct": 3.0,
            "targets": {
                "equity_pct": 50.0,
                "fixed_income_pct": 25.0,
                "deposit_pct": 25.0,
            },
        },
    },
}


def list_policy_presets(conn=None) -> Dict[str, Any]:
    """Return preset catalog + which one matches current policy (if any)."""
    current = get_policy(conn) if conn is not None else json.loads(json.dumps(DEFAULT_POLICY))
    active = _match_preset_id(current)
    items = []
    for key in ("defensive", "balanced", "building"):
        p = POLICY_PRESETS[key]
        pol = p["policy"]
        t = pol["targets"]
        items.append(
            {
                "id": p["id"],
                "label": p["label"],
                "summary": p["summary"],
                "detail": p["detail"],
                "active": active == key,
                "targets": {
                    "equity_pct": t["equity_pct"],
                    "fixed_income_pct": t["fixed_income_pct"],
                    "deposit_pct": t["deposit_pct"],
                },
                "equity_band": [pol["equity_min_pct"], pol["equity_max_pct"]],
                "defensive_min_pct": pol["defensive_min_pct"],
                "single_holding_max_pct": pol["single_holding_max_pct"],
                "rebalance_band_pct": pol["rebalance_band_pct"],
            }
        )
    return {"presets": items, "active_id": active, "current_preset_id": current.get("preset_id")}


def _match_preset_id(policy: Dict[str, Any]) -> Optional[str]:
    """Exact match on structure knobs; else honor stored preset_id if still equal."""
    stored = str(policy.get("preset_id") or "").strip() or None
    for key, preset in POLICY_PRESETS.items():
        pol = preset["policy"]
        t = pol["targets"]
        ct = policy.get("targets") or {}
        if (
            abs(float(policy.get("equity_min_pct") or 0) - float(pol["equity_min_pct"])) < 0.05
            and abs(float(policy.get("equity_max_pct") or 0) - float(pol["equity_max_pct"])) < 0.05
            and abs(float(policy.get("defensive_min_pct") or 0) - float(pol["defensive_min_pct"])) < 0.05
            and abs(float(policy.get("single_holding_max_pct") or 0) - float(pol["single_holding_max_pct"])) < 0.05
            and abs(float(policy.get("rebalance_band_pct") or 0) - float(pol["rebalance_band_pct"])) < 0.05
            and abs(float(ct.get("equity_pct") or 0) - float(t["equity_pct"])) < 0.05
            and abs(float(ct.get("fixed_income_pct") or 0) - float(t["fixed_income_pct"])) < 0.05
            and abs(float(ct.get("deposit_pct") or 0) - float(t["deposit_pct"])) < 0.05
        ):
            return key
    if stored in POLICY_PRESETS:
        return None  # labeled but knobs drifted → treat as custom
    return None


def apply_policy_preset(conn, preset_id: str) -> Dict[str, Any]:
    """Apply structure knobs from a preset; keep personal codes/limits/plans codes."""
    key = str(preset_id or "").strip()
    if key not in POLICY_PRESETS:
        raise ValueError(f"未知预设：{preset_id}（可选 defensive / balanced / building）")
    preset = POLICY_PRESETS[key]
    payload = dict(preset["policy"])
    payload["preset_id"] = key
    policy = set_policy(conn, payload)
    return {"preset_id": key, "label": preset["label"], "policy": policy}


def _sql_literal(value: str) -> str:
    """DDL 的 DEFAULT 子句不能绑参数，只能内联；按 SQL 规则转义单引号。"""
    return "'" + str(value).replace("'", "''") + "'"


def ensure_discipline_tables(conn) -> None:
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS discipline_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            category TEXT,
            account TEXT DEFAULT {_sql_literal(DEFAULT_ACCOUNT)},
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
        return _deep_merge(DEFAULT_POLICY, normalize_legacy_policy(data))
    except Exception:
        return json.loads(json.dumps(DEFAULT_POLICY))


def set_policy(conn, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("policy 必须是对象")
    # 先合并再 normalize：老客户端只发 gree_* 不发 named_limits 时，软上限要追加到已存的上限里，
    # 而不是用「只含这一项」的列表把已存的整个覆盖掉。
    merged = normalize_legacy_policy(_deep_merge(get_policy(conn), payload))

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

    # 优先加仓代码允许留空：留空时权益偏低只提示、不生成买入建议
    for str_key in ("preferred_buy_code", "preferred_buy_name", "preferred_buy_category", "preferred_buy_account"):
        if str_key in merged:
            merged[str_key] = str(merged.get(str_key) or "").strip()

    for list_key in ("named_limits", "no_new_codes", "fixed_income_categories", "defensive_extra_categories"):
        if list_key in merged and merged[list_key] is None:
            merged[list_key] = []

    limits = []
    for lim in merged.get("named_limits") or []:
        if not isinstance(lim, dict):
            raise ValueError("个股上限每一项需包含 code / max_pct")
        code = str(lim.get("code") or "").strip()
        if not code:
            continue  # 空行（前端新增后没填）直接丢弃
        max_pct = _finite(lim.get("max_pct"), f"个股上限 {code}")
        if max_pct <= 0 or max_pct > 100:
            raise ValueError(f"个股上限 {code} 需在 0–100 之间")
        limits.append({"code": code, "name": str(lim.get("name") or "").strip() or code, "max_pct": max_pct})
    merged["named_limits"] = limits

    plans = dict(merged.get("plans") or {})
    if "batch_buy_target_amount" in plans:
        plans["batch_buy_target_amount"] = max(
            0.0, _finite(plans["batch_buy_target_amount"] or 0, "plans.batch_buy_target_amount")
        )
    for k in ("batch_buy_code", "batch_buy_name"):
        if k in plans:
            plans[k] = str(plans[k] or "").strip()
    merged["plans"] = plans

    # 结构尺子若与三套预设不一致，标记为 custom（一键套用会写 preset_id）
    matched = _match_preset_id(merged)
    if matched:
        merged["preset_id"] = matched
    else:
        # 保留显式 custom；空则标 custom
        pid = str(merged.get("preset_id") or "").strip()
        if pid not in POLICY_PRESETS:
            merged["preset_id"] = "custom"

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


def _latest_accounts_for_codes(
    conn, codes: List[str], default: str = DEFAULT_ACCOUNT
) -> Dict[str, str]:
    """一次查询取多个 code 的「最新账户」，避免每只持仓一条 SQL（N+1）。

    语义与旧版逐只查询完全一致：只看 account 非空的交易，按 date DESC, id DESC
    取第一行；查不到（或查询失败）时回落到 default。
    """
    wanted: List[str] = []
    seen = set()
    for c in codes or []:
        s = str(c or "").strip()
        if s and s not in seen:
            seen.add(s)
            wanted.append(s)
    if not wanted:
        return {}
    placeholders = ",".join("?" for _ in wanted)
    try:
        rows = conn.execute(
            f"""
            SELECT code, account FROM (
                SELECT code, account,
                       ROW_NUMBER() OVER (
                           PARTITION BY code ORDER BY date DESC, id DESC
                       ) AS rn
                FROM transactions
                WHERE code IN ({placeholders})
                  AND account IS NOT NULL AND TRIM(account) != ''
            ) WHERE rn = 1
            """,
            tuple(wanted),
        ).fetchall()
    except Exception:
        # 极老版本 SQLite（<3.25，无窗口函数）退回逐 code 查询：结果与旧实现完全一致
        return _latest_accounts_by_code_fallback(conn, wanted, default)
    out: Dict[str, str] = {}
    for r in rows:
        code = r["code"] if isinstance(r, sqlite3.Row) else r[0]
        acct = r["account"] if isinstance(r, sqlite3.Row) else r[1]
        key = str(code or "").strip()
        if not key:
            continue
        out[key] = str(acct or default).strip() or default
    return out


def _latest_account_for_code(conn, code: str, default: str = DEFAULT_ACCOUNT) -> str:
    """单 code 便捷入口；内部走批量查询，保持原有回退语义。"""
    key = str(code or "").strip()
    if not key:
        return default
    return _latest_accounts_for_codes(conn, [key], default).get(key, default)


def _latest_accounts_by_code_fallback(
    conn, codes: List[str], default: str = DEFAULT_ACCOUNT
) -> Dict[str, str]:
    """老 SQLite 兜底：逐 code 查最新账户（旧实现原样，仅作兼容路径）。"""
    out: Dict[str, str] = {}
    for code in codes:
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
            continue
        if not row:
            continue
        acct = row["account"] if isinstance(row, sqlite3.Row) else row[0]
        out[code] = str(acct or default).strip() or default
    return out


def _holding_rows(conn, policy: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    policy = policy or DEFAULT_POLICY
    pref_acct = str(policy.get("preferred_buy_account") or DEFAULT_ACCOUNT)
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
        out.append(h)
    # 全部持仓的最新账户一次查出来（原来每只持仓一条 SELECT ... WHERE code=?）
    accounts = _latest_accounts_for_codes(
        conn, [h.get("code") or "" for h in out], pref_acct
    )
    for h in out:
        h["account"] = accounts.get(str(h.get("code") or "").strip(), pref_acct)
    return out


def build_discipline_report(conn) -> Dict[str, Any]:
    """Evaluate real portfolio against policy; return breaches + rebalance actions."""
    report, _holdings = build_discipline_report_with_holdings(conn)
    return report


def build_discipline_report_with_holdings(conn) -> Tuple[
    Dict[str, Any], List[Dict[str, Any]]
]:
    """build_discipline_report 的实现 + 顺带返回持仓行（供 allocation_story 复用，避免再查一次）。"""
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
                        "account": h.get("account") or policy.get("preferred_buy_account") or DEFAULT_ACCOUNT,
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
                    "account": h.get("account") or DEFAULT_ACCOUNT,
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

    pref_code = str(policy.get("preferred_buy_code") or "").strip()
    pref_name = str(policy.get("preferred_buy_name") or pref_code)
    pref_cat = str(policy.get("preferred_buy_category") or "A股ETF")
    pref_acct = str(policy.get("preferred_buy_account") or DEFAULT_ACCOUNT)
    no_new = {str(c).strip() for c in (policy.get("no_new_codes") or [])}

    if gaps["equity"] > band and total_assets > 0 and pref_code:
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

    if gaps["deposit"] < -band and gaps["equity"] > 0 and total_assets > 0 and pref_code:
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

    # --- plans (batch buy plan / soft caps) ---
    plans = policy.get("plans") or {}
    plan_items: List[Dict[str, Any]] = []
    batch_code = str(plans.get("batch_buy_code") or plans.get("a500_batch_code") or pref_code or "").strip()
    batch_name = str(plans.get("batch_buy_name") or plans.get("a500_batch_name") or pref_name or batch_code)
    batch_target = float(plans.get("batch_buy_target_amount") or plans.get("a500_batch_target_amount") or 0)
    batch_h = next((x for x in holdings if str(x.get("code")) == batch_code), None) if batch_code else None
    batch_mv = float(batch_h["market_value"]) if batch_h else 0.0
    batch_gap = max(batch_target - batch_mv, 0.0) if batch_target > 0 else 0.0
    if batch_target > 0 and batch_code:
        progress_pct = min(max(batch_mv / batch_target * 100.0, 0.0), 999.0) if batch_target else 0.0
        cash_avail = float(totals.get("securities_cash") or 0)
        is_a500 = "a500" in batch_name.lower() or batch_code == "159352"
        plan_code_prefix = "a500_batch" if is_a500 else "batch_buy"
        if batch_gap >= 100:
            if batch_gap >= 80000:
                next_batch = min(max(batch_gap / 4.0, 20000.0), 50000.0)
            elif batch_gap >= 40000:
                next_batch = min(max(batch_gap / 3.0, 15000.0), 40000.0)
            else:
                next_batch = min(batch_gap, max(cash_avail, 10000.0) if cash_avail > 0 else batch_gap)
            next_batch = round(min(next_batch, batch_gap), 2)
            plan_items.append(
                {
                    "code": plan_code_prefix,
                    "level": "info",
                    "title": f"{batch_name} 分批计划",
                    "text": (
                        f"目标约 {batch_target:.0f} 元，当前市值约 {batch_mv:.0f}（完成 {progress_pct:.0f}%），"
                        f"还差约 {batch_gap:.0f}。建议下次大约 {next_batch:.0f} 元"
                        + (f"（证券现金约 {cash_avail:.0f}）" if cash_avail > 0 else "")
                        + "，分批即可不必一次买完。"
                    ),
                    "remaining_amount": round(batch_gap, 2),
                    "current_amount": round(batch_mv, 2),
                    "target_amount": round(batch_target, 2),
                    "progress_pct": round(progress_pct, 2),
                    "suggested_next_amount": next_batch,
                    "symbol": batch_code,
                }
            )
        else:
            plan_items.append(
                {
                    "code": f"{plan_code_prefix}_done",
                    "level": "ok",
                    "title": f"{batch_name} 分批计划",
                    "text": f"目标约 {batch_target:.0f} 元，当前市值约 {batch_mv:.0f}（完成 {progress_pct:.0f}%），计划基本到位。",
                    "remaining_amount": 0,
                    "current_amount": round(batch_mv, 2),
                    "target_amount": round(batch_target, 2),
                    "progress_pct": round(progress_pct, 2),
                    "suggested_next_amount": 0,
                    "symbol": batch_code,
                }
            )

    gree_code = str(plans.get("gree_code") or "").strip()
    gree_soft = float(plans.get("gree_soft_max_pct") or 0)
    if gree_code and gree_soft > 0:
        gree_name = str(plans.get("gree_name") or gree_code)
        gree_h = next((x for x in holdings if str(x.get("code")) == gree_code), None)
        if gree_h and total_assets > 0:
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

    pref_hint = f"默认优先加仓 {pref_name}（{pref_code}）；" if pref_code else "可配置优先加仓标的；"
    help_notes = [
        "本页默认只读：点「建议→草稿」不会改账，只有「确认入账」才写真实交易。",
        "买入金额类确认后一般记为「申购待确认」，份额确认后再改成买入。",
        "券商下单仍需你自己操作；这里只帮你记建议和账本草稿。",
        "改参数会影响纪律提醒和再平衡建议，保存后立即生效。",
        f"{pref_hint}个股可设个人上限。",
    ]

    report = {
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
    return report, holdings


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
        account = a.get("account") or DEFAULT_ACCOUNT
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
        fields["quantity"] = max(0.0, _finite(payload["quantity"], "数量"))
    if "price" in payload and payload["price"] is not None:
        fields["price"] = max(0.0, _finite(payload["price"], "价格"))
    if "amount" in payload and payload["amount"] is not None:
        fields["amount"] = _finite(payload["amount"], "金额")
        if fields["amount"] <= 0:
            raise ValueError("金额必须大于 0")
    if "fee" in payload and payload["fee"] is not None:
        fields["fee"] = max(0.0, _finite(payload["fee"], "手续费"))
    if "reason" in payload and payload["reason"] is not None:
        fields["reason"] = str(payload["reason"])
    if "account" in payload and payload["account"] is not None:
        fields["account"] = str(payload["account"] or DEFAULT_ACCOUNT).strip() or DEFAULT_ACCOUNT
    if "name" in payload and payload["name"] is not None:
        fields["name"] = str(payload["name"] or d.get("code") or "")
    if "category" in payload and payload["category"] is not None:
        fields["category"] = str(payload["category"] or "")
    if "date" in payload and payload["date"] is not None:
        raw_date = str(payload["date"]).strip()
        if not raw_date:
            raise ValueError("日期不能为空")
        try:
            fields["date"] = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
        except ValueError as exc:
            raise ValueError(f"日期格式无效：{raw_date}") from exc
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

    next_code = str(fields.get("code", d.get("code") or "")).strip()
    next_side = str(fields.get("side", d.get("side") or "")).lower().strip()
    if next_code and next_side in ("buy", "sell"):
        existing = _find_open_draft(conn, next_code, next_side)
        if existing and int(existing.get("id") or 0) != int(draft_id):
            raise ValueError(f"已有未确认的 {next_code}/{next_side} 草稿，不能重复")

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
    account = str(d.get("account") or DEFAULT_ACCOUNT)
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
        transaction_date=date,
    )

    backup_path = None
    if make_backup:
        try:
            backup_path = create_safety_backup("before_confirm_discipline_draft")
        except Exception as exc:
            logger.warning("confirm_draft backup failed draft_id=%s: %s", draft_id, exc)
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
    validate_holding_history(conn, code)
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
    except Exception as exc:
        logger.warning("confirm_drafts shared backup failed: %s", exc)
        backup_path = None
    for did in draft_ids:
        savepoint = f"discipline_confirm_{int(did)}"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            # single shared backup already taken
            results.append(confirm_draft(conn, int(did), make_backup=False))
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception as exc:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            errors.append({"draft_id": did, "error": str(exc)})
    return {
        "confirmed": results,
        "errors": errors,
        "count": len(results),
        "backup": backup_path,
    }
