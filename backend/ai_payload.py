"""Whitelist payload builder and output validator for AI features.

Never copy an input dict. Portfolio daily % is not a parameter, so it cannot leak.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ALLOWED_KEYS = {
    "brief": {
        "as_of", "day_pnl_amount_rounded", "counts", "movers", "benchmark",
        "discipline_breach_count", "plans", "reasons", "moves", "reason_coverage",
    },
    "alert_note": {
        "trigger", "portfolio_direction", "peers", "benchmark", "reasons", "moves",
    },
    "nl_rule": {"utterance", "available_codes"},
    # N1 一句话记账：只有原话、候选标的清单与"今天"三样，账本数值一个都不进。
    "nl_entry": {"utterance", "available_codes", "today"},
    "profile_digest": {
        "code", "asset_kind", "report_period", "period_kind", "as_of", "metrics",
        "profile", "dividends", "dividend_summary", "information_complete",
    },
    # N2 周报：只给区间汇总（金额取整到千位）+ 同期信息，**不给组合区间涨跌幅**。
    "weekly": {
        "window_start", "window_end", "net_gain_rounded", "external_flow_rounded",
        "discipline_breach_count", "plans", "deposits_due", "reasons", "moves", "reason_coverage",
    },
    # N4 公告要点分类：只给标题/类型/日期 + 三个标签，正文、数量、金额都不进。
    "notice_class": {"code", "name", "items", "labels"},
}

_AMOUNT_ROUND_UNIT = 1000

MOVER_KEEP = ("code", "name", "change_pct")
PLAN_KEEP = ("title", "label", "kind", "code", "level")
REASON_KEEP = ("code", "kind", "title", "content", "source", "url", "published_at", "date", "name", "notice_type")
MOVE_KEEP = ("code", "kind", "title", "board", "event_time", "date", "name")
COUNTS_KEEP = ("up", "down", "flat", "holdings", "count")
BENCHMARK_KEEP = ("name", "change_pct")
TRIGGER_KEEP = ("code", "name", "change_pct", "rule")
PEER_KEEP = ("code", "name", "change_pct")
COVERAGE_KEEP = ("matched", "window_days", "note")

SPECULATION_TERMS = (
    "可能",
    "或将",
    "预计",
    "猜测",
    "大概率",
    "市场情绪",
    "疑似",
    "传闻",
    "应该是",
    "或受",
)
TRADE_ADVICE_TERMS = (
    "利好", "利空", "建议买入", "建议卖出", "加仓", "减仓",
    "目标价", "估值修复", "有望上涨", "或将下跌", "买入", "卖出", "评级",
)


def trade_advice_prompt_clause() -> str:
    """Forbidden-word sentence shared by the profile digest system prompt."""
    return "禁止出现这些词：" + "、".join(TRADE_ADVICE_TERMS) + "。也禁止预测、涨跌判断或任何投资建议。"
CAUSAL_TERMS = ("因为", "由于", "导致", "原因在于", "拖累")
FLAT_CLAIM_TERMS = ("全部持平", "全部平盘", "都是平盘", "全员平盘", "持仓全部持平")
_NUM_RE = re.compile(
    r"([+\-−－]?\d+(?:\.\d+)?)\s*([万亿])?\s*([%％])?"
)
_CITE_RE = re.compile(r"\[([^\]]+)\]")
_SENTENCE_RE = re.compile(r"[。！？!?\n]+")


def round_amount(v: float) -> int:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(x):
        return 0
    return int(round(x / float(_AMOUNT_ROUND_UNIT)) * _AMOUNT_ROUND_UNIT)


def _round_or_null(v: Any) -> Optional[int]:
    """金额取整到千位；**None 原样保留**。

    缺基准快照时 `period_gain` 是 None，写成 0 就等于告诉模型"这周没盈亏"（明明算不出来）——
    抬头那边已经写"算不出"，payload 必须同口径。
    """
    if v is None:
        return None
    return round_amount(v)

def _pick_dict(raw: Any, keys: Sequence[str]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {k: raw[k] for k in keys if k in raw and raw[k] is not None}


def _pick_list(raw: Any, keys: Sequence[str]) -> List[Dict[str, Any]]:
    if not isinstance(raw, (list, tuple)):
        return []
    return [_pick_dict(item, keys) for item in raw if isinstance(item, dict)]


def _movers(raw: Any) -> List[Dict[str, Any]]:
    items = list(raw or []) if isinstance(raw, (list, tuple)) else []

    def contrib(row: Any) -> float:
        if not isinstance(row, dict):
            return 0.0
        for key in ("contribution", "contrib", "impact"):
            try:
                return abs(float(row.get(key) or 0))
            except (TypeError, ValueError):
                continue
        return 0.0

    ranked = [row for row in items if isinstance(row, dict)]
    ranked.sort(key=contrib, reverse=True)
    out = []
    for row in ranked:
        cleaned = {}
        for key in MOVER_KEEP:
            if key in row and row[key] is not None:
                cleaned[key] = row[key]
        out.append(cleaned)
    return out


def _codes(raw: Any) -> List[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def build_payload(feature: str, **sources) -> Dict[str, Any]:
    """Build a new dict from explicit fields. Does not copy any input dict."""
    if feature not in ALLOWED_KEYS:
        raise ValueError("unknown AI feature: %s" % feature)

    if feature == "brief":
        amount = sources.get("day_pnl_amount_rounded")
        if amount is None:
            amount = sources.get("day_pnl_amount", 0)
        return {
            "as_of": str(sources.get("as_of") or ""),
            "day_pnl_amount_rounded": round_amount(amount or 0),
            "counts": _pick_dict(sources.get("counts") or {}, COUNTS_KEEP),
            "movers": _movers(sources.get("movers")),
            "benchmark": _pick_dict(sources.get("benchmark") or {}, BENCHMARK_KEEP),
            "discipline_breach_count": int(sources.get("discipline_breach_count") or 0),
            "plans": _pick_list(sources.get("plans"), PLAN_KEEP),
            "reasons": _pick_list(sources.get("reasons"), REASON_KEEP),
            "moves": _pick_list(sources.get("moves"), MOVE_KEEP),
            "reason_coverage": _pick_dict(sources.get("reason_coverage") or {}, COVERAGE_KEEP),
        }

    if feature == "alert_note":
        return {
            "trigger": _pick_dict(sources.get("trigger") or {}, TRIGGER_KEEP),
            "portfolio_direction": str(sources.get("portfolio_direction") or ""),
            "peers": _pick_list(sources.get("peers"), PEER_KEEP),
            "benchmark": _pick_dict(sources.get("benchmark") or {}, BENCHMARK_KEEP),
            "reasons": _pick_list(sources.get("reasons"), REASON_KEEP),
            "moves": _pick_list(sources.get("moves"), MOVE_KEEP),
        }

    if feature == "profile_digest":
        return {
            "code": str(sources.get("code") or ""),
            "asset_kind": str(sources.get("asset_kind") or ""),
            "report_period": str(sources.get("report_period") or ""),
            "period_kind": str(sources.get("period_kind") or "as_of"),
            "as_of": str(sources.get("as_of") or ""),
            "metrics": _pick_list(sources.get("metrics"), ("section", "label", "value", "status", "note")),
            "profile": _pick_dict(sources.get("profile") or {}, ("name", "short_name", "industry", "main_biz", "market", "listed")),
            "dividends": _pick_list(sources.get("dividends"), ("report", "desc", "yield_pct", "ex_date")),
            "dividend_summary": _pick_dict(sources.get("dividend_summary") or {}, ("per10_12m", "per_hand", "count", "newest")),
            "information_complete": bool(sources.get("information_complete")),
        }


    if feature == "weekly":
        due = sources.get("deposits_due") or {}
        return {
            "window_start": str(sources.get("window_start") or "")[:10],
            "window_end": str(sources.get("window_end") or "")[:10],
            # 区间口径（period_*），不是全期的 total_gain / net_contribution ——
            # 用错字段会把"开户以来总收益"当成"这周赚了多少"（见 ai_weekly 模块注释）。
            "net_gain_rounded": _round_or_null(sources.get("net_gain")),
            "external_flow_rounded": _round_or_null(sources.get("external_flow")),
            "discipline_breach_count": int(sources.get("discipline_breach_count") or 0),
            "plans": _pick_list(sources.get("plans"), PLAN_KEEP),
            # 只给各桶的**条数**，不给金额/银行名（存款金额与组合金额一样不外发）
            "deposits_due": {
                key: len(due.get(key) or []) for key in ("overdue", "d0", "d7", "d30")
            },
            "reasons": _pick_list(sources.get("reasons"), REASON_KEEP),
            "moves": _pick_list(sources.get("moves"), MOVE_KEEP),
            "reason_coverage": _pick_dict(sources.get("reason_coverage") or {}, COVERAGE_KEEP),
        }

    if feature == "notice_class":
        return {
            "code": str(sources.get("code") or ""),
            "name": str(sources.get("name") or ""),
            "items": _pick_list(sources.get("items"), ("kind", "notice_type", "title", "date")),
            # 标签集合由代码写死，不给模型自由发挥的余地（三值里必须有"无法判断"）
            "labels": ["相关", "无关", "无法判断"],
        }


    if feature == "nl_entry":
        return {
            "utterance": str(sources.get("utterance") or "").strip(),
            "available_codes": _codes(sources.get("available_codes")),
            "today": str(sources.get("today") or "")[:10],
        }
    return {
        "utterance": str(sources.get("utterance") or ""),
        "available_codes": _codes(sources.get("available_codes")),
    }


def _walk_numbers(obj: Any, out: List[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        if math.isfinite(float(obj)):
            out.append(float(obj))
        return
    if isinstance(obj, dict):
        for value in obj.values():
            _walk_numbers(value, out)
        return
    if isinstance(obj, (list, tuple)):
        for value in obj:
            _walk_numbers(value, out)


def _cite_titles(payload: Dict[str, Any]) -> set:
    titles = set()
    for key in ("reasons", "moves"):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
                if title:
                    titles.add(title)
    return titles


def _extract_numbers(text: str) -> List[Tuple[float, bool]]:
    """Return (value, is_percent) pairs from model output, skipping citations."""
    stripped = _CITE_RE.sub(" ", text or "")
    found: List[Tuple[float, bool]] = []
    for match in _NUM_RE.finditer(stripped):
        raw, unit, pct = match.group(1), match.group(2), match.group(3)
        token = (raw or "").replace("−", "-").replace("－", "-")
        try:
            value = float(token)
        except (TypeError, ValueError):
            continue
        if unit == "万":
            value *= 10000.0
        elif unit == "亿":
            value *= 100000000.0
        is_pct = bool(pct)
        # Skip 4-digit years. Do not skip 6-digit amounts.
        if not is_pct and unit is None:
            abs_v = abs(value)
            if abs_v >= 1900 and abs_v <= 2100 and float(value).is_integer():
                continue
        found.append((value, is_pct))
    return found


def _number_ok(value: float, is_pct: bool, payload_nums: Iterable[float]) -> bool:
    nums = [n for n in payload_nums if n != 0]
    if is_pct:
        for item in nums:
            if abs(value - item) <= 0.1:
                return True
        return False
    for item in nums:
        if abs(value - item) <= _AMOUNT_ROUND_UNIT:
            return True
        if abs(value - abs(item)) <= _AMOUNT_ROUND_UNIT:
            return True
    return False


def _counts_lack_quotes(payload: Dict[str, Any]) -> bool:
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    try:
        holdings = int(counts.get("holdings") or 0)
        scored = int(counts.get("up") or 0) + int(counts.get("down") or 0) + int(counts.get("flat") or 0)
    except (TypeError, ValueError):
        return False
    return holdings > 0 and scored == 0


def validate_output(
    feature: str,
    text: str,
    payload: Dict[str, Any],
    *,
    strict: Optional[bool] = None,
    shadow: bool = False,
) -> Dict[str, Any]:
    """Return {ok, reason, text, warnings}.

    Shadow / non-strict: record warnings but do not block the original text.
    """
    if strict is None:
        strict = not shadow
    warnings: List[str] = []
    reasons: List[str] = []
    body = text or ""
    payload = payload or {}

    titles = _cite_titles(payload)
    for cite in _CITE_RE.findall(body):
        if cite.strip() not in titles:
            msg = "来源不可溯: [%s]" % cite.strip()
            warnings.append(msg)
            reasons.append("untraceable_source")

    payload_nums: List[float] = []
    _walk_numbers(payload, payload_nums)
    for value, is_pct in _extract_numbers(body):
        if not _number_ok(value, is_pct, payload_nums):
            msg = "数字不可溯: %s%s" % (value, "%" if is_pct else "")
            warnings.append(msg)
            reasons.append("untraceable_number")

    for sentence in _SENTENCE_RE.split(body) + [body]:
        chunk = (sentence or "").strip()
        if not chunk:
            continue
        if _CITE_RE.search(chunk):
            continue
        hit = [term for term in SPECULATION_TERMS if term in chunk]
        if hit:
            msg = "推测措辞: %s" % "、".join(hit)
            warnings.append(msg)
            reasons.append("speculation")
        causal = [term for term in CAUSAL_TERMS if term in chunk]
        if causal:
            msg = "因果措辞: %s" % "、".join(causal)
            warnings.append(msg)
            reasons.append("causal_claim")

    if feature in ("profile_digest", "weekly"):
        # 投资建议词表原来只挂在档案摘要上：周报同样是"叙述性结论"，也不能出现
        # 利好 / 目标价 / 建议买入 这类词 —— 此前只靠 prompt，strict 拦不住。
        hits = [term for term in TRADE_ADVICE_TERMS if term in body]
        if hits:
            warnings.append("投资建议词: %s" % "、".join(hits))
            reasons.append("trade_advice")

    if _counts_lack_quotes(payload):
        hit = [term for term in FLAT_CLAIM_TERMS if term in body]
        if hit:
            warnings.append("缺行情时不得断言平盘: %s" % "、".join(hit))
            reasons.append("unsupported_flat")

    warnings = list(dict.fromkeys(warnings))
    reasons = list(dict.fromkeys(reasons))

    if reasons and strict:
        return {
            "ok": False,
            "reason": reasons[0],
            "text": None,
            "warnings": warnings,
        }
    return {
        "ok": True,
        "reason": None,
        "text": body,
        "warnings": warnings,
    }
