"""N6 profile digest: structured fundamentals -> guarded AI summary.

The feature is strictly read-only, never pushed, and cache keys include the
asset identity and report period so stock/fund data cannot cross-contaminate.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from .ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from .ai_payload import build_payload, trade_advice_prompt_clause, validate_output
    from .cash import set_setting
    from .company_extras import build_company_extras
    from .database import LOCAL_TZ, local_today_iso
    from .dividend_sync import dividend_asset_kind
    from .fundamentals import build_fundamental_check
except ImportError:
    from ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from ai_payload import build_payload, trade_advice_prompt_clause, validate_output
    from cash import set_setting
    from company_extras import build_company_extras
    from database import LOCAL_TZ, local_today_iso
    from dividend_sync import dividend_asset_kind
    from fundamentals import build_fundamental_check

PROFILE_TIMEOUT_S = 120
PROFILE_MAX_CHARS = 200
PROFILE_MAX_TOKENS = 220
PROFILE_CACHE_PREFIX = "ai_profile_digest_"
PROFILE_CACHE_TTL_DAYS = 7
PROFILE_FAILURE_CACHE_TTL_MINUTES = 10
PROFILE_CACHE_KEEP_DAYS = 30
INSUFFICIENT_TEXT = "数据不足，无法生成摘要"

SYSTEM_PROMPT = """你是公司档案摘要助手，只能使用用户给出的 JSON。
输出一段不超过 200 字的中文白话，概括赚钱能力、负债/现金质量和分红习惯。
{forbidden}
不得补充 JSON 之外的事实，不得自行计算。输出只要正文，不要标题和 Markdown。
如果 information_complete 为 false，必须以“信息不完整：”开头。
""".format(forbidden=trade_advice_prompt_clause())


def _now_local() -> datetime:
    if LOCAL_TZ is not None:
        return datetime.now(LOCAL_TZ).replace(tzinfo=None)
    return datetime.now()


def _get_setting(conn, key: str) -> Optional[str]:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    value = row["value"] if hasattr(row, "keys") else row[0]
    return None if value is None else str(value)


def normalize_asset_kind(code: str, asset_kind: Optional[str] = None) -> str:
    raw = str(asset_kind or "").strip().lower()
    aliases = {
        "stock": "a_share_equity",
        "equity": "a_share_equity",
        "a_share": "a_share_equity",
        "a_share_equity": "a_share_equity",
        "fund": "listed_fund",
        "etf": "listed_fund",
        "listed_fund": "listed_fund",
    }
    if raw:
        return aliases.get(raw, raw.replace(" ", "_")[:40])
    try:
        inferred = dividend_asset_kind(str(code or ""))
    except Exception:
        inferred = None
    return inferred or "unknown"


def normalize_report_period(raw: Any) -> Optional[str]:
    text = str(raw or "").strip()
    if not text or text.lower() in {"none", "null", "nat", "nan", "-"}:
        return None
    text = text.replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = "%s-%s-%s" % (text[:4], text[4:6], text[6:8])
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        candidate = text[:10]
        try:
            datetime.strptime(candidate, "%Y-%m-%d")
            return candidate
        except ValueError:
            return None
    if len(text) == 7 and text[4] == "-" and text[5:].isdigit():
        return text
    if len(text) == 6 and text.isdigit():
        return "%s-%s" % (text[:4], text[4:])
    return None


def profile_cache_key(code: str, report_period: str, asset_kind: Optional[str] = None) -> str:
    identity = normalize_asset_kind(code, asset_kind)
    safe_code = str(code or "").strip().replace("/", "_")
    safe_period = str(report_period or "").strip().replace("/", "_")
    return "%s%s_%s_%s" % (PROFILE_CACHE_PREFIX, identity, safe_code, safe_period)


def _parse_created_at(raw: Any) -> Optional[datetime]:
    text = str(raw or "")[:19]
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _cache_ttl(record: Dict[str, Any]) -> timedelta:
    mode = str(record.get("mode") or "")
    if mode == "ok":
        return timedelta(days=PROFILE_CACHE_TTL_DAYS)
    if mode in {"timeout", "blocked"}:
        return timedelta(minutes=PROFILE_FAILURE_CACHE_TTL_MINUTES)
    return timedelta(0)


def read_profile_cache(
    conn,
    code: str,
    report_period: str,
    *,
    asset_kind: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    key = profile_cache_key(code, report_period, asset_kind)
    raw = _get_setting(conn, key)
    if not raw:
        return None
    try:
        record = json.loads(raw)
    except Exception:
        return None
    if not isinstance(record, dict):
        return None
    if str(record.get("code") or "") != str(code or ""):
        return None
    if str(record.get("report_period") or "") != str(report_period or ""):
        return None
    if normalize_asset_kind(code, record.get("asset_kind")) != normalize_asset_kind(code, asset_kind):
        return None
    created = _parse_created_at(record.get("created_at"))
    now = now or _now_local()
    if created is None or now - created > _cache_ttl(record):
        return None
    return record


def purge_profile_cache(conn, *, as_of: Optional[str] = None) -> None:
    today = str(as_of or local_today_iso())[:10]
    try:
        cut = datetime.strptime(today, "%Y-%m-%d") - timedelta(days=PROFILE_CACHE_KEEP_DAYS)
    except ValueError:
        return
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE ? ESCAPE '\\'",
            (PROFILE_CACHE_PREFIX.replace("_", "\\_") + "%",),
        ).fetchall()
    except Exception:
        return
    for row in rows:
        key = row["key"] if hasattr(row, "keys") else row[0]
        raw = row["value"] if hasattr(row, "keys") else row[1]
        try:
            data = json.loads(raw or "{}")
            created = _parse_created_at(data.get("created_at"))
        except Exception:
            created = None
        if created is not None and created < cut:
            try:
                conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            except Exception:
                logger.exception("purge_profile_cache: delete failed")


def write_profile_cache(conn, record: Dict[str, Any]) -> None:
    payload = {
        "code": str(record.get("code") or ""),
        "asset_kind": normalize_asset_kind(record.get("code"), record.get("asset_kind")),
        "report_period": str(record.get("report_period") or ""),
        "period_kind": str(record.get("period_kind") or "as_of"),
        "as_of": str(record.get("as_of") or ""),
        "text": str(record.get("text") or ""),
        "mode": str(record.get("mode") or "blocked"),
        "warnings": list(record.get("warnings") or []),
        "model": str(record.get("model") or ""),
        "created_at": str(record.get("created_at") or _now_local().strftime("%Y-%m-%d %H:%M:%S")),
    }
    key = profile_cache_key(payload["code"], payload["report_period"], payload["asset_kind"])
    set_setting(conn, key, json.dumps(payload, ensure_ascii=False))
    purge_profile_cache(conn, as_of=payload["as_of"])


def _record(
    *,
    code: str,
    asset_kind: str,
    report_period: str,
    period_kind: str,
    as_of: str,
    mode: str,
    text: str = "",
    warnings: Optional[List[str]] = None,
    model: str = "",
) -> Dict[str, Any]:
    return {
        "code": code,
        "asset_kind": asset_kind,
        "report_period": report_period,
        "period_kind": period_kind,
        "as_of": as_of,
        "mode": mode,
        "text": text,
        "warnings": list(warnings or []),
        "model": model,
        "created_at": _now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _profile_fields(profile: Any) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    keep = ("name", "short_name", "industry", "main_biz", "market", "listed")
    return {key: profile[key] for key in keep if profile.get(key)}


def _metrics_from_sections(sections: Any) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    if not isinstance(sections, list):
        return metrics
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_label = str(section.get("label") or section.get("key") or "").strip()
        for item in section.get("items") or []:
            if not isinstance(item, dict) or item.get("value") is None:
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            metric = {"section": section_label, "label": label, "value": item.get("value")}
            if item.get("status"):
                metric["status"] = item["status"]
            if item.get("note"):
                metric["note"] = item["note"]
            metrics.append(metric)
    return metrics


def build_profile_snapshot(code: str, *, asset_kind: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch structured sources and return a safe, model-ready snapshot."""
    normalized_code = str(code or "").strip()
    as_of = local_today_iso()
    identity = normalize_asset_kind(normalized_code, asset_kind)
    try:
        fundamental = build_fundamental_check(normalized_code) or {}
    except Exception:
        logger.exception("build_profile_snapshot: fundamentals failed")
        fundamental = {}
    sections = fundamental.get("sections") if isinstance(fundamental, dict) else None
    if not sections:
        return None
    try:
        extras = build_company_extras(normalized_code) or {}
    except Exception:
        logger.exception("build_profile_snapshot: company extras failed")
        extras = {}
    metrics = _metrics_from_sections(sections)
    if not metrics:
        return None
    report_period = normalize_report_period(fundamental.get("report_period"))
    period_kind = "report_period"
    if not report_period:
        period_kind = "as_of"
        report_period = as_of
    dividends = []
    for item in extras.get("dividends") or []:
        if not isinstance(item, dict):
            continue
        clean = {key: item[key] for key in ("report", "desc", "yield_pct", "ex_date") if item.get(key) is not None}
        if clean:
            dividends.append(clean)
    summary = extras.get("dividend_summary")
    if not isinstance(summary, dict):
        summary = {}
    else:
        summary = {key: summary[key] for key in ("per10_12m", "per_hand", "count", "newest") if summary.get(key) is not None}
    complete = bool(len(metrics) >= 4 and (extras.get("profile") or dividends or summary))
    return {
        "code": normalized_code,
        "asset_kind": identity,
        "report_period": report_period,
        "period_kind": period_kind,
        "as_of": as_of,
        "metrics": metrics,
        "profile": _profile_fields(extras.get("profile")),
        "dividends": dividends,
        "dividend_summary": summary,
        "information_complete": complete,
    }


def profile_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def clip_profile_text(text: str, *, limit: int = PROFILE_MAX_CHARS) -> str:
    body = str(text or "").strip()
    if len(body) <= limit:
        return body
    cut = body[:limit]
    pos = cut.rfind("。")
    return cut[: pos + 1] if pos >= 0 else ""


def _delete_profile_cache(conn, code: str, report_period: str, asset_kind: str) -> None:
    try:
        conn.execute("DELETE FROM settings WHERE key = ?", (profile_cache_key(code, report_period, asset_kind),))
    except Exception:
        logger.exception("profile cache refresh: delete failed")


def generate_profile_digest(
    conn,
    code: str,
    *,
    asset_kind: Optional[str] = None,
    refresh: bool = False,
) -> Dict[str, Any]:
    normalized_code = str(code or "").strip()
    as_of = local_today_iso()
    identity = normalize_asset_kind(normalized_code, asset_kind)
    cfg = load_ai_config(conn)
    if not cfg.enabled or not bool(cfg.features.get("profile_digest")):
        return _record(
            code=normalized_code,
            asset_kind=identity,
            report_period=as_of,
            period_kind="as_of",
            as_of=as_of,
            mode="feature_disabled",
        )

    snapshot = build_profile_snapshot(normalized_code, asset_kind=identity)
    if snapshot is None:
        return _record(
            code=normalized_code,
            asset_kind=identity,
            report_period=as_of,
            period_kind="as_of",
            as_of=as_of,
            mode="empty",
            text=INSUFFICIENT_TEXT,
            model=cfg.model,
        )

    if refresh:
        _delete_profile_cache(conn, snapshot["code"], snapshot["report_period"], snapshot["asset_kind"])
    else:
        cached = read_profile_cache(
            conn,
            snapshot["code"],
            snapshot["report_period"],
            asset_kind=snapshot["asset_kind"],
        )
        if cached:
            cached["cached"] = True
            return cached

    payload = build_payload("profile_digest", **snapshot)
    result = call_ai(
        conn,
        cfg,
        "profile_digest",
        profile_messages(payload),
        max_tokens=PROFILE_MAX_TOKENS,
        temperature=0.2,
        timeout_seconds=PROFILE_TIMEOUT_S,
    )
    if not result.get("ok"):
        reason = str(result.get("reason") or "")
        rec = _record(
            code=snapshot["code"],
            asset_kind=snapshot["asset_kind"],
            report_period=snapshot["report_period"],
            period_kind=snapshot["period_kind"],
            as_of=snapshot["as_of"],
            mode="timeout" if reason == "timeout" else "blocked",
            warnings=[reason] if reason else [],
            model=cfg.model,
        )
        if reason == "timeout":
            return rec
        try:
            write_profile_cache(conn, rec)
        except Exception:
            logger.exception("profile digest: cache write failed")
        return rec

    text = clip_profile_text(result.get("text") or "")
    if not snapshot["information_complete"] and not text.startswith("信息不完整："):
        text = clip_profile_text("信息不完整：" + text)
    checked = validate_output(
        "profile_digest",
        text,
        payload,
        strict=not cfg.shadow_mode,
        shadow=cfg.shadow_mode,
    )
    try:
        stamp_ai_warnings(conn, result.get("audit_id"), checked.get("warnings") or [])
    except Exception:
        logger.exception("profile digest: stamp warnings failed")
    if checked.get("ok") and checked.get("text"):
        rec = _record(
            code=snapshot["code"],
            asset_kind=snapshot["asset_kind"],
            report_period=snapshot["report_period"],
            period_kind=snapshot["period_kind"],
            as_of=snapshot["as_of"],
            mode="ok",
            text=str(checked["text"]),
            warnings=checked.get("warnings"),
            model=cfg.model,
        )
    else:
        rec = _record(
            code=snapshot["code"],
            asset_kind=snapshot["asset_kind"],
            report_period=snapshot["report_period"],
            period_kind=snapshot["period_kind"],
            as_of=snapshot["as_of"],
            mode="blocked",
            warnings=checked.get("warnings"),
            model=cfg.model,
        )
    try:
        write_profile_cache(conn, rec)
    except Exception:
        logger.exception("profile digest: cache write failed")
    return rec
