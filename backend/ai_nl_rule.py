"""A5 自然语言建预警规则（`nl_rule`）：一句话 → 规则草稿。

**只产草稿，从不落库**：写库必须由用户点确认 → 既有 `POST /market/alert-rules`
（复用 `market.create_alert_rule` 的全部校验）。与项目「草稿确认后才入账」同构。

阈值符号以 `market._normalize_rule_fields` 为准，别照抄文档：
  price                    阈值**不能为负**（就是价格水平，如 60.0）；方向由 condition 表达
  change_pct/portfolio_pnl **带符号**（below → −2.0，above → +2.0）
所以"跌到 60 块"是 price + below + **+60.0**，不是 −60。

影子模式**不影响本例**（与 A4 有意的差异）：草稿本来就必须人工确认，所以照常返回草稿、
照常写审计，不做任何"只记不生效"的处理。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from .ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from .ai_entry import _json_object, available_assets
    from .ai_payload import ALLOWED_KEYS, build_payload
    from .market import (
        ALLOWED_CONDITIONS,
        ALLOWED_RULE_TYPES,
        ALLOWED_TARGET_TYPES,
        DEFAULT_INDICES,
        PORTFOLIO_RULE_CODE,
    )
except ImportError:
    from ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from ai_entry import _json_object, available_assets
    from ai_payload import ALLOWED_KEYS, build_payload
    from market import (
        ALLOWED_CONDITIONS,
        ALLOWED_RULE_TYPES,
        ALLOWED_TARGET_TYPES,
        DEFAULT_INDICES,
        PORTFOLIO_RULE_CODE,
    )

NL_RULE_MAX_TOKENS = 200
# 交互式等人：与 N1 一句话记账同口径（细则未定，取 30s）。
NL_RULE_TIMEOUT_S = 30
NL_RULE_MAX_UTTERANCE = 200
RULE_AVAILABLE_LIMIT = 200
PRICE_ABS_MAX = 10000.0
PCT_ABS_MIN = 0.5
PCT_ABS_MAX = 20.0
PORTFOLIO_LABEL = "组合当日盈亏"

HINT = "解析结果仅作草稿，确认后才写入规则"
SYSTEM_PROMPT = """你是预警规则助手。只输出一个 JSON 对象，不要解释、不要 markdown 围栏。
字段：target_type / code / name / rule_type / condition / threshold
取值约束：
- target_type：holding（持仓）/ index（指数）/ portfolio（整个组合）
- rule_type：price（价格）/ change_pct（涨跌幅 %）/ portfolio_pnl（组合当日盈亏 %）
- condition：above（涨到/高于）/ below（跌到/低于）
- code 只能从 available_codes 里选；target_type=portfolio 时用 PORTFOLIO
- threshold：price 给**正的价格**；change_pct / portfolio_pnl 给**百分比数值**，符号交给 condition
硬规则：
1. 不许编造代码或名称；选不出就输出 {"target_type": null}。
2. 拿不准的字段就输出 null，不要猜。
3. 名称有歧义时（例如 000001 既是上证指数又可能是平安银行）输出 {"target_type": null}，不要猜。
4. 只输出 JSON，不要输出任何其它文字。

示例输入：{"utterance": "格力跌到 60 块提醒我", "available_codes": ["000651 格力电器"]}
示例输出：{"target_type": "holding", "code": "000651", "name": "格力电器", "rule_type": "price", "condition": "below", "threshold": 60}
"""


def available_rule_targets(conn) -> Optional[List[str]]:
    """`["{code} {name}", ...]`：持仓 ∪ 关注 ∪ 交易历史 ∪ 指数清单 ∪ 组合。

    复用 A4/N1 那份取清单的逻辑（含"空 vs 读失败"的区分），再补上指数与组合 ——
    指数不在持仓表里，但它是合法规则目标。
    """
    base = available_assets(conn)
    if base is None:
        return None
    out = list(base)
    seen = {str(item).split()[0] for item in out if str(item).strip()}
    for item in DEFAULT_INDICES:
        code = str(item.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append("%s %s" % (code, str(item.get("name") or code)))
    if PORTFOLIO_RULE_CODE not in seen:
        out.append("%s %s" % (PORTFOLIO_RULE_CODE, PORTFOLIO_LABEL))
    return out[:RULE_AVAILABLE_LIMIT]


def _code_name_map(targets: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in targets:
        parts = str(item or "").strip().split(None, 1)
        if not parts or not parts[0]:
            continue
        out[parts[0]] = parts[1].strip() if len(parts) > 1 else parts[0]
    return out


def assemble_rule_payload(conn, utterance: str) -> Dict[str, Any]:
    targets = available_rule_targets(conn)
    if targets is None:
        raise RuntimeError("rule targets unavailable")
    payload = build_payload(
        "nl_rule",
        utterance=str(utterance or "")[:NL_RULE_MAX_UTTERANCE],
        available_codes=targets,
    )
    if set(payload) != ALLOWED_KEYS["nl_rule"]:
        raise AssertionError("nl_rule payload keys drifted: %s" % sorted(payload))
    return payload


def rule_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _number(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return value


def _review_draft(
    raw_text: str, *, allowed_names: Dict[str, str]
) -> Dict[str, Any]:
    """字段级复核：任一失败即拒绝，不产生半截草稿。

    返回 {"draft": dict|None, "reason": str, "detail": str, "warnings": [...]}。
    detail 是给用户看的人话，reason 是给程序看的枚举。
    """
    warnings: List[str] = []
    data = _json_object(raw_text)
    if data is None:
        return {"draft": None, "reason": "unparsable", "detail": "", "warnings": warnings}

    target_type = str(data.get("target_type") or "").strip().lower()
    rule_type = str(data.get("rule_type") or "").strip().lower()
    condition = str(data.get("condition") or "").strip().lower()
    code = str(data.get("code") or "").strip()
    name = str(data.get("name") or "").strip()

    if target_type not in ALLOWED_TARGET_TYPES:
        return {
            "draft": None,
            "reason": "invalid_rule",
            "detail": "没听出这条规则针对什么（持仓 / 指数 / 组合）",
            "warnings": warnings,
        }
    if condition not in ALLOWED_CONDITIONS:
        return {
            "draft": None,
            "reason": "invalid_rule",
            "detail": "没听出是「涨到」还是「跌到」",
            "warnings": warnings,
        }
    if rule_type not in ALLOWED_RULE_TYPES:
        return {
            "draft": None,
            "reason": "invalid_rule",
            "detail": "不支持的规则类型（只支持 价格 / 涨跌幅 / 组合盈亏）",
            "warnings": warnings,
        }

    # 组合规则：与 market._normalize_rule_fields 同一套归一（那边为了防"静默翻转后
    # threshold 还是价格"，对 UPDATE 是直接 400；这里是全新草稿，阈值同样会被我们归一，
    # 所以按细则 §3.5.4 做归一更友好）。
    if target_type == "portfolio" and rule_type != "portfolio_pnl":
        warnings.append("组合规则已按 portfolio_pnl 归一（模型给的是 %s）" % rule_type)
        rule_type = "portfolio_pnl"
    if rule_type == "portfolio_pnl":
        target_type = "portfolio"
        code = PORTFOLIO_RULE_CODE

    if target_type == "portfolio":
        name = allowed_names.get(PORTFOLIO_RULE_CODE) or PORTFOLIO_LABEL
    else:
        if not code or code not in allowed_names:
            # 库外标的：不许猜（与 N1 同口径）。
            return {
                "draft": None,
                "reason": "unknown_code",
                "detail": "原话里的标的不在持仓 / 关注 / 交易记录 / 指数清单里",
                "warnings": warnings,
            }
        name = allowed_names.get(code) or name or code
        model_name = str(data.get("name") or "").strip()
        if model_name and model_name != name:
            warnings.append("name 以库内为准，模型给的 %s 已忽略" % model_name[:40])

    threshold = _number(data.get("threshold"))
    if threshold is None:
        return {
            "draft": None,
            "reason": "invalid_rule",
            "detail": "阈值不是数字",
            "warnings": warnings,
        }

    if rule_type == "price":
        # 价格阈值不能为负（market 的硬约束）：方向由 condition 表达。
        value = abs(threshold)
        if not (0 < value < PRICE_ABS_MAX):
            return {
                "draft": None,
                "reason": "invalid_rule",
                "detail": "价格阈值要在 0 到 %d 之间" % int(PRICE_ABS_MAX),
                "warnings": warnings,
            }
    else:
        magnitude = abs(threshold)
        if not (PCT_ABS_MIN <= magnitude <= PCT_ABS_MAX):
            return {
                "draft": None,
                "reason": "invalid_rule",
                "detail": "涨跌幅 / 组合盈亏的阈值要在 %.1f%% 到 %.0f%% 之间" % (PCT_ABS_MIN, PCT_ABS_MAX),
                "warnings": warnings,
            }
        # 带符号：below 是"跌到 −2%"，above 是"涨到 +2%"。
        value = -magnitude if condition == "below" else magnitude

    return {
        "draft": {
            "target_type": target_type,
            "code": code,
            "name": name,
            "rule_type": rule_type,
            "condition": condition,
            "threshold": round(value, 4),
        },
        "reason": "",
        "detail": "",
        "warnings": warnings,
    }


def _failure_mode(reason: str) -> str:
    if reason in ("timeout", "budget", "disabled", "feature_disabled", "not_configured"):
        return reason
    return "blocked"


def _result(
    *,
    mode: str,
    draft: Optional[Dict[str, Any]] = None,
    warnings=None,
    model: str = "",
    reason: str = "",
    detail: str = "",
) -> Dict[str, Any]:
    return {
        "ok": draft is not None,
        "mode": mode,
        "draft": draft,
        "warnings": list(warnings or []),
        "model": model or "",
        "reason": reason or "",
        "detail": detail or "",
        "hint": HINT,
    }


def parse_rule_draft(conn, utterance: str) -> Dict[str, Any]:
    """一句话 → 预警规则草稿。永不抛；失败给 mode，不给半截草稿。"""
    text = str(utterance or "").strip()
    if not text:
        return _result(mode="unparsable", reason="empty_utterance", detail="请先说一句话")
    if len(text) > NL_RULE_MAX_UTTERANCE:
        return _result(mode="unparsable", reason="utterance_too_long", detail="原话过长")

    cfg = load_ai_config(conn)
    if not cfg.enabled:
        return _result(mode="disabled", model=cfg.model)
    if not bool(cfg.features.get("nl_rule")):
        # 用例关闭时不取数、不调模型。
        return _result(mode="feature_disabled", model=cfg.model)

    try:
        targets = available_rule_targets(conn)
    except Exception:
        logger.exception("parse_rule_draft: available targets raised")
        targets = None
    if targets is None:
        return _result(mode="assets_unavailable", reason="assets_unavailable", model=cfg.model)
    if not targets:
        return _result(mode="empty_universe", reason="empty_universe", model=cfg.model)

    try:
        conn.commit()
    except Exception:
        pass

    try:
        payload = assemble_rule_payload(conn, text)
    except Exception:
        logger.exception("parse_rule_draft: payload failed")
        return _result(mode="blocked", reason="payload_failed", model=cfg.model)

    result = call_ai(
        conn,
        cfg,
        "nl_rule",
        rule_messages(payload),
        max_tokens=NL_RULE_MAX_TOKENS,
        # 结构化输出要的是稳不是灵。
        temperature=0.0,
        timeout_seconds=NL_RULE_TIMEOUT_S,
    )
    if not result.get("ok"):
        reason = str(result.get("reason") or "blocked")
        return _result(mode=_failure_mode(reason), reason=reason, model=cfg.model)

    reviewed = _review_draft(str(result.get("text") or ""), allowed_names=_code_name_map(targets))
    try:
        stamp_ai_warnings(conn, result.get("audit_id"), reviewed.get("warnings") or [])
    except Exception:
        logger.exception("parse_rule_draft: stamp warnings failed")

    if reviewed.get("draft") is None:
        reason = str(reviewed.get("reason") or "unparsable")
        return _result(
            mode=reason,
            reason=reason,
            detail=str(reviewed.get("detail") or ""),
            warnings=reviewed.get("warnings"),
            model=cfg.model,
        )

    # 影子模式不作特殊处理：草稿本来就必须人工确认才落库（与 A4 有意的差异）。
    return _result(
        mode="ok",
        draft=reviewed.get("draft"),
        warnings=reviewed.get("warnings"),
        model=cfg.model,
    )
