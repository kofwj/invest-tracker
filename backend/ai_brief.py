"""P1 evening-brief AI segment: payload, prompt, cache, shadow inject.

Never serializes build_evening_brief() / compute_portfolio_totals().
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from .ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from .ai_payload import ALLOWED_KEYS, build_payload, validate_output
    from .cash import set_setting
    from .database import LOCAL_TZ, local_today_iso
    from .discipline import build_discipline_report
    from .market import _holding_price_map, _portfolio_day_pnl, build_market_summary
    from .reason_cache import (
        NOTICE_REFILL_HOUR,
        NOTICE_REFILL_MINUTE,
        WINDOW_DAYS,
        _holding_codes as _reason_holding_codes,
        reasons_for_holdings,
    )
except ImportError:
    from ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from ai_payload import ALLOWED_KEYS, build_payload, validate_output
    from cash import set_setting
    from database import LOCAL_TZ, local_today_iso
    from discipline import build_discipline_report
    from market import _holding_price_map, _portfolio_day_pnl, build_market_summary
    from reason_cache import (
        NOTICE_REFILL_HOUR,
        NOTICE_REFILL_MINUTE,
        WINDOW_DAYS,
        _holding_codes as _reason_holding_codes,
        reasons_for_holdings,
    )

BRIEF_TIMEOUT_S = 20
BRIEF_MAX_CHARS = 200
BRIEF_MAX_TOKENS = 200
EMPTY_LINE = "未找到相关公告或新闻"
PENDING_LINE = "（今日 AI 段未生成）"
CACHE_PREFIX = "ai_brief_"
CACHE_KEEP_DAYS = 30
EMPTY_RETRY_AFTER = (NOTICE_REFILL_HOUR, NOTICE_REFILL_MINUTE)
SHADOW_HINT = "（影子模式：仅预览，不随推送发送）"


def _now_local() -> datetime:
    if LOCAL_TZ is not None:
        return datetime.now(LOCAL_TZ).replace(tzinfo=None)
    return datetime.now()

SYSTEM_PROMPT = """你是持仓复盘助手。只能使用用户给出的 JSON 字段。
硬规则：
1. 引用制：不得引入清单之外的事件、公司、政策、时间。
2. 必须带来源：每条事实后跟 [标题]，标题必须与 JSON 里 reasons/moves 的 title 完全一致。
3. 禁止断言因果：只能写「同期有这些信息」，不得写「因为/由于/导致」。
4. 空则承认：无条目时输出「未找到相关公告或新闻」。
5. counts 的 up/down/flat 全为 0 时不得写「全部持平/全部平盘」（缺行情不是平盘）。
禁止出现总资产、成本、仓位占比、组合涨跌幅。
纯文本，无 markdown 标题，不超过 200 字。

反面示例（禁止）：
因为农行发布人事公告，所以银行股下跌。
正面示例：
未找到相关公告或新闻。
"""


def _get_setting(conn, key: str) -> Optional[str]:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    value = row["value"] if hasattr(row, "keys") else row[0]
    return None if value is None else str(value)


def _counts_from_holding_map(holding_map: Dict[str, Any]) -> Dict[str, int]:
    """up/down/flat only count rows with a numeric change_pct; missing is not flat."""
    items = list(holding_map.values()) if isinstance(holding_map, dict) else []
    up = down = flat = 0
    for row in items:
        if not isinstance(row, dict):
            continue
        raw = row.get("change_pct")
        if raw is None:
            continue
        try:
            chg = float(raw)
        except (TypeError, ValueError):
            continue
        if chg > 0:
            up += 1
        elif chg < 0:
            down += 1
        else:
            flat += 1
    return {"up": up, "down": down, "flat": flat, "holdings": len(items)}


def clip_brief_text(text: str, *, limit: int = BRIEF_MAX_CHARS) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    cut = body[:limit]
    pos = cut.rfind("。")
    if pos >= 0:
        return cut[: pos + 1]
    return ""


def brief_cache_key(as_of: str) -> str:
    return CACHE_PREFIX + str(as_of or "")[:10]


def read_brief_cache(conn, as_of: str) -> Optional[Dict[str, Any]]:
    raw = _get_setting(conn, brief_cache_key(as_of))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict) or str(data.get("date") or "")[:10] != str(as_of)[:10]:
        return None
    return data


def purge_brief_cache(conn, *, as_of: str) -> None:
    try:
        cut = (datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date() - timedelta(days=CACHE_KEEP_DAYS)).isoformat()
    except ValueError:
        return
    try:
        rows = conn.execute(
            "SELECT key FROM settings WHERE key LIKE ?",
            (CACHE_PREFIX + "%",),
        ).fetchall()
    except Exception:
        return
    for row in rows:
        key = str(row["key"] if hasattr(row, "keys") else row[0] or "")
        day = key[len(CACHE_PREFIX) :][:10]
        if day and day < cut:
            try:
                conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            except Exception:
                pass


def write_brief_cache(conn, record: Dict[str, Any], *, as_of: str) -> None:
    payload = {
        "date": str(as_of)[:10],
        "mode": record.get("mode") or "blocked",
        "text": record.get("text") or "",
        "warnings": list(record.get("warnings") or []),
        "model": record.get("model") or "",
        "generated_at": record.get("generated_at") or _now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }
    set_setting(conn, brief_cache_key(as_of), json.dumps(payload, ensure_ascii=False))
    purge_brief_cache(conn, as_of=as_of)


def empty_cache_expired(record: Dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    """mode=empty is only sticky until the 16:40 notice refill."""
    if not isinstance(record, dict) or str(record.get("mode") or "") != "empty":
        return False
    now = now or _now_local()
    hour, minute = EMPTY_RETRY_AFTER
    cutoff = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < cutoff:
        return False
    gen = str(record.get("generated_at") or "")
    try:
        gen_dt = datetime.strptime(gen[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    return gen_dt < cutoff


def assemble_brief_payload(conn, *, as_of: Optional[str] = None) -> Dict[str, Any]:
    """Build a brief payload from explicit sources. Never copies a totals/brief dict."""
    today = str(as_of or local_today_iso())[:10]
    summary: Dict[str, Any] = {}
    try:
        summary = build_market_summary(conn) or {}
    except Exception:
        logger.exception("assemble_brief_payload: market summary failed")
        summary = {}

    holding_map: Dict[str, Any] = {}
    try:
        holding_map = _holding_price_map(conn) or {}
    except Exception:
        logger.exception("assemble_brief_payload: holding map failed")
        holding_map = {}

    amount = 0.0
    try:
        amount = float(_portfolio_day_pnl(holding_map).get("amount") or 0)
    except Exception:
        logger.exception("assemble_brief_payload: day pnl failed")
        try:
            amount = float((summary.get("signals") or {}).get("today_contrib_estimate") or 0)
        except (TypeError, ValueError):
            amount = 0.0

    holdings_day = list(summary.get("holdings_day") or [])
    movers = []
    for row in holdings_day[:3]:
        if not isinstance(row, dict):
            continue
        movers.append(
            {
                "code": row.get("code"),
                "name": row.get("name"),
                "change_pct": row.get("change_pct"),
                "contribution": row.get("day_contrib"),
            }
        )

    hs300 = None
    for item in summary.get("indices") or []:
        if isinstance(item, dict) and str(item.get("code") or "") == "000300":
            hs300 = item
            break
    benchmark = {}
    if hs300 is not None:
        benchmark = {"name": "沪深300", "change_pct": hs300.get("change_pct")}

    disc: Dict[str, Any] = {}
    try:
        disc = build_discipline_report(conn) or {}
    except Exception:
        logger.exception("assemble_brief_payload: discipline failed")
        disc = {}
    breaches = [b for b in (disc.get("breaches") or []) if isinstance(b, dict) and b.get("level") == "warning"]

    codes = _reason_holding_codes(conn)
    packed = {"reasons": [], "moves": [], "reason_coverage": {"matched": 0, "window_days": WINDOW_DAYS["notice"], "note": ""}}
    try:
        packed = reasons_for_holdings(conn, codes, as_of=today) or packed
    except Exception:
        logger.exception("assemble_brief_payload: reasons failed")
        packed = {
            "reasons": [],
            "moves": [],
            "reason_coverage": {
                "matched": 0,
                "window_days": WINDOW_DAYS["notice"],
                "note": "原因缓存暂不可用",
            },
        }

    payload = build_payload(
        "brief",
        as_of=today,
        day_pnl_amount=amount,
        counts=_counts_from_holding_map(holding_map),
        movers=movers,
        benchmark=benchmark,
        discipline_breach_count=len(breaches),
        plans=disc.get("plans") or [],
        reasons=packed.get("reasons") or [],
        moves=packed.get("moves") or [],
        reason_coverage=packed.get("reason_coverage") or {},
    )
    if set(payload) != ALLOWED_KEYS["brief"]:
        raise AssertionError("brief payload keys drifted: %s" % sorted(payload))
    return payload


def brief_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _record(*, mode: str, text: str = "", warnings=None, model: str = "") -> Dict[str, Any]:
    return {
        "mode": mode,
        "text": text or "",
        "warnings": list(warnings or []),
        "model": model or "",
        "generated_at": _now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


def generate_brief_segment(conn, *, as_of: Optional[str] = None) -> Dict[str, Any]:
    """Generate today's AI segment. Writes cache. Never raises."""
    today = str(as_of or local_today_iso())[:10]
    cfg = load_ai_config(conn)
    if not cfg.enabled or not bool(cfg.features.get("brief")):
        return _record(mode="disabled")

    cached = read_brief_cache(conn, today)
    if cached and not empty_cache_expired(cached):
        return cached

    try:
        conn.commit()
    except Exception:
        pass

    try:
        payload = assemble_brief_payload(conn, as_of=today)
    except Exception:
        logger.exception("generate_brief_segment: assemble failed")
        rec = _record(mode="blocked")
        try:
            write_brief_cache(conn, rec, as_of=today)
        except Exception:
            logger.exception("generate_brief_segment: cache write failed")
        return rec

    if not (payload.get("reasons") or payload.get("moves")):
        rec = _record(mode="empty", text=EMPTY_LINE, model=cfg.model)
        try:
            write_brief_cache(conn, rec, as_of=today)
        except Exception:
            logger.exception("generate_brief_segment: cache write failed")
        return rec

    try:
        conn.commit()
    except Exception:
        pass

    result = call_ai(
        conn,
        cfg,
        "brief",
        brief_messages(payload),
        max_tokens=BRIEF_MAX_TOKENS,
        temperature=0.2,
        timeout_seconds=BRIEF_TIMEOUT_S,
    )
    if not result.get("ok"):
        mode = "timeout" if str(result.get("reason") or "") == "timeout" else "blocked"
        rec = _record(mode=mode, model=cfg.model)
        try:
            write_brief_cache(conn, rec, as_of=today)
        except Exception:
            logger.exception("generate_brief_segment: cache write failed")
        return rec

    clipped = clip_brief_text(str(result.get("text") or ""))
    checked = validate_output(
        "brief",
        clipped,
        payload,
        strict=not cfg.shadow_mode,
        shadow=cfg.shadow_mode,
    )
    try:
        stamp_ai_warnings(conn, result.get("audit_id"), checked.get("warnings") or [])
    except Exception:
        logger.exception("generate_brief_segment: stamp warnings failed")

    if not checked.get("ok") or not checked.get("text"):
        rec = _record(mode="blocked", warnings=checked.get("warnings"), model=cfg.model)
    else:
        rec = _record(
            mode="ok",
            text=str(checked.get("text") or ""),
            warnings=checked.get("warnings"),
            model=cfg.model,
        )
    try:
        write_brief_cache(conn, rec, as_of=today)
    except Exception:
        logger.exception("generate_brief_segment: cache write failed")
    return rec


def resolve_evening_ai(conn, *, notify: bool) -> Dict[str, Any]:
    """Decide whether to append an AI segment. Never raises."""
    try:
        cfg = load_ai_config(conn)
    except Exception:
        logger.exception("resolve_evening_ai: load config failed")
        return {"mode": "disabled", "text": "", "append": False, "warnings": []}

    if not cfg.enabled or not bool(cfg.features.get("brief")):
        return {"mode": "disabled", "text": "", "append": False, "warnings": []}

    today = local_today_iso()
    if not notify:
        cached = read_brief_cache(conn, today)
        if cached:
            extra = str(cached.get("text") or "").strip()
            if extra and cfg.shadow_mode:
                extra = extra + "\n" + SHADOW_HINT
            return {**cached, "text": extra, "append": bool(extra)}
        pending = PENDING_LINE
        if cfg.shadow_mode:
            pending = PENDING_LINE + "\n" + SHADOW_HINT
        return {"mode": "pending", "text": pending, "append": True, "warnings": []}

    try:
        segment = generate_brief_segment(conn, as_of=today)
    except Exception:
        logger.exception("resolve_evening_ai: generate failed")
        return {"mode": "blocked", "text": "", "append": False, "warnings": []}

    mode = str(segment.get("mode") or "")
    text = str(segment.get("text") or "").strip()
    append = (not cfg.shadow_mode) and mode in ("ok", "empty") and bool(text)
    return {**segment, "append": append}

