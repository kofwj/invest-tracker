"""N4 公告要点分类（`notice_class`）：给已命中的公告打「相关 / 无关 / 无法判断」。

范围与红线：
  · **只做公告**（`kind == "notice"`），新闻留后（量大、噪音更多）；**只进站内**，不进任何推送通道。
  · **空就承认空**：窗口内没有公告 → 直接返回空结果、**不调模型**（省额度也不编话）。
  · **允许弃权**：「无法判断」是三值之一，prompt 明说证据不足就给它、不要为了好看去推断。
  · **结构化输出走字段级复核**：label 必须在三值内、title 必须精确命中输入、why ≤20 字、
    禁用词（投资建议 / 因果）在 strict 下丢**该条**（不是整批）。
    为什么不套 `validate_output`：它那套"数字可溯 / 来源可溯 / 推测措辞"是给叙述性文本设计的 ——
    对 JSON 分类结果要么误杀（"可能只是人事任免"会被判推测）、要么漏检（label 合法性它根本不管）。
  · **影子模式不影响本例**（与 N6 / `nl_rule` 同口径）：结论只在站内展示、本来就要人看，
    没有"推送"可拦，所以照常返回结果、照常写审计。

缓存：键 `ai_notice_class_{code}_{日期}`（同一天同一标的只调一次模型）。
  ok / empty 当天有效，但 **empty 在 16:40 公告补抓之后会重算**（照 A3 的 `EMPTY_RETRY_AFTER`）；
  失败（含超时）只缓存 10 分钟 —— 与 N6「超时不缓存」略有差异，原因是这里每次打开弹窗都会请求，
  超时会让用户每次盯着 30 秒转圈；10 分钟足够挡掉连环重试，又不至于把一次抖动钉一整天。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from .ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from .ai_entry import _json_object
    from .ai_payload import ALLOWED_KEYS, TRADE_ADVICE_TERMS, build_payload
    from .cash import set_setting
    from .database import LOCAL_TZ, local_today_iso
    from .reason_cache import NOTICE_REFILL_HOUR, NOTICE_REFILL_MINUTE
    from .reason_cache import reasons_for_holdings
except ImportError:
    from ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from ai_entry import _json_object
    from ai_payload import ALLOWED_KEYS, TRADE_ADVICE_TERMS, build_payload
    from cash import set_setting
    from database import LOCAL_TZ, local_today_iso
    from reason_cache import NOTICE_REFILL_HOUR, NOTICE_REFILL_MINUTE
    from reason_cache import reasons_for_holdings

NOTICE_MAX_TOKENS = 300
# 交互式：点开弹窗等人（与 N1/A5 同口径）。
NOTICE_TIMEOUT_S = 30
# 一次最多分类 10 条：T-2 窗口里的公告通常只有一两条，多的多半是噪音
NOTICE_MAX_ITEMS = 10
NOTICE_WHY_MAX_CHARS = 20
NOTICE_FAIL_TTL_MINUTES = 10
CACHE_KEEP_DAYS = 30
CACHE_PREFIX = "ai_notice_class_"
LABELS = ("相关", "无关", "无法判断")
CAUSAL_TERMS = ("因为", "由于", "导致", "原因在于", "拖累")
EMPTY_RETRY_AFTER = (NOTICE_REFILL_HOUR, NOTICE_REFILL_MINUTE)

SYSTEM_PROMPT = """你是公告分类助手。只给给出的每条公告打一个标签，不要做别的事。
输出严格 JSON：{"results":[{"title":"原文标题","label":"相关|无关|无法判断","why":"不超过 20 字"}]}
硬规则：
1. 只能使用 items 里出现过的 title，逐字照抄；不许改写、不许新增条目。
2. label 只能取 labels 里的三个值之一。
3. 证据不足就给「无法判断」——不要为了让结论好看而推断。人事任免、H 股披露表格、
   经营范围变更这类与股价没有直接对应关系的公告，就该说无法判断或无关。
4. 禁止投资建议与因果判断：不许写「利好 / 利空 / 建议买入 / 减仓 / 目标价」，
   也不许写「因为…导致…」。why 只描述这条公告本身是什么，不要预测股价。
5. why 不超过 20 字，不要复述标题。

示例输出：
{"results":[{"title":"农业银行:关于非执行董事任职的公告","label":"无法判断","why":"仅人事任免，与股价无直接对应"}]}
"""


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


def notice_cache_key(code: str, day: str) -> str:
    return "%s%s_%s" % (CACHE_PREFIX, str(code or "").strip(), str(day or "")[:10])


def read_notice_cache(conn, code: str, *, day: Optional[str] = None) -> Optional[Dict[str, Any]]:
    today = str(day or local_today_iso())[:10]
    raw = _get_setting(conn, notice_cache_key(code, today))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("code") or "") != str(code or "").strip():
        return None
    if str(data.get("date") or "")[:10] != today:
        return None
    return data


def purge_notice_cache(conn, *, day: str) -> None:
    try:
        cut = (datetime.strptime(str(day)[:10], "%Y-%m-%d").date() - timedelta(days=CACHE_KEEP_DAYS)).isoformat()
    except ValueError:
        return
    try:
        rows = conn.execute(
            # ESCAPE 必须显式声明（A4/N2 都踩过）：`_` 在 LIKE 里是通配、`\` 不是转义
            "SELECT key FROM settings WHERE key LIKE ? ESCAPE '\\'",
            (CACHE_PREFIX.replace("_", "\\_") + "%",),
        ).fetchall()
    except Exception:
        return
    for row in rows:
        key = str(row["key"] if hasattr(row, "keys") else row[0] or "")
        tail = key[len(CACHE_PREFIX) :]
        day_part = tail.rsplit("_", 1)[-1][:10]
        if day_part and day_part < cut:
            try:
                conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            except Exception:
                pass


def _record(
    *,
    code: str,
    name: str = "",
    day: str,
    mode: str,
    results: Optional[List[Dict[str, Any]]] = None,
    warnings=None,
    model: str = "",
    items_count: int = 0,
) -> Dict[str, Any]:
    return {
        "code": str(code or "").strip(),
        "date": str(day)[:10],
        "name": name or "",
        "mode": mode,
        "results": list(results or []),
        "warnings": list(warnings or []),
        "model": model or "",
        "items_count": int(items_count or 0),
        "cached": False,
        "generated_at": _now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


def write_notice_cache(conn, record: Dict[str, Any]) -> None:
    code = str(record.get("code") or "")
    day = str(record.get("date") or local_today_iso())[:10]
    if not code:
        return
    set_setting(conn, notice_cache_key(code, day), json.dumps(record, ensure_ascii=False))
    purge_notice_cache(conn, day=day)


def _age_minutes(record: Dict[str, Any], *, now: Optional[datetime] = None) -> float:
    raw = str(record.get("generated_at") or "")
    try:
        generated = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 1e9
    return ((now or _now_local()) - generated).total_seconds() / 60.0


def _empty_cache_expired(record: Dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    """空结果只在 16:40 公告补抓之前算数：补抓之后再打开就该重算（照 A3）。"""
    if str(record.get("mode") or "") != "empty":
        return False
    now = now or _now_local()
    hour, minute = EMPTY_RETRY_AFTER
    cutoff = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < cutoff:
        return False
    return _age_minutes(record, now=now) > ((now - cutoff).total_seconds() / 60.0)


def _cache_usable(record: Dict[str, Any], *, day: str) -> bool:
    mode = str(record.get("mode") or "")
    if str(record.get("date") or "")[:10] != str(day)[:10]:
        return False
    if mode in ("ok", "empty"):
        return not _empty_cache_expired(record)
    # 失败：10 分钟内不重试（超时也缓存，免得每次打开弹窗都转 30 秒）
    return _age_minutes(record) < NOTICE_FAIL_TTL_MINUTES


def notice_items(conn, code: str) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
    """该标的 T-2 窗口内的**公告**条目：去重、按日期倒序、上限 10 条。

    返回 (name, items)；`items is None` 表示**取数失败**，与"窗口内确实没有公告"（`[]`）分开 ——
    失败要走 blocked + 短 TTL，不能被当成 empty 钉到当天结束（N1 的"主源失败 ≠ 空清单"同一类）。
    """
    today = local_today_iso()
    try:
        packed = reasons_for_holdings(conn, [str(code or "").strip()], as_of=today) or {}
    except Exception:
        logger.exception("notice_items: reasons failed")
        return "", None
    name = ""
    seen = set()
    items: List[Dict[str, Any]] = []
    for item in packed.get("reasons") or []:
        if not isinstance(item, dict) or str(item.get("kind") or "") != "notice":
            continue
        title = str(item.get("title") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        name = name or str(item.get("name") or "")
        items.append(
            {
                "kind": "notice",
                "notice_type": str(item.get("notice_type") or ""),
                "title": title,
                "date": str(item.get("date") or "")[:10],
            }
        )
    items.sort(key=lambda row: row.get("date") or "", reverse=True)
    return name, items[:NOTICE_MAX_ITEMS]


def assemble_notice_payload(code: str, name: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload = build_payload("notice_class", code=code, name=name, items=items)
    if set(payload) != ALLOWED_KEYS["notice_class"]:
        raise AssertionError("notice_class payload keys drifted: %s" % sorted(payload))
    return payload


def notice_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _review_results(raw_text: str, *, allowed_titles: set, strict: bool) -> Dict[str, Any]:
    """字段级复核：逐条裁剪，不整批丢。返回 {results, warnings, reason}。"""
    warnings: List[str] = []
    data = _json_object(raw_text)
    if data is None:
        return {"results": [], "warnings": warnings, "reason": "unparsable"}
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        return {"results": [], "warnings": warnings, "reason": "unparsable"}

    results: List[Dict[str, Any]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        label = str(item.get("label") or "").strip()
        why = str(item.get("why") or "").strip()
        if title not in allowed_titles:
            # 引用可溯：标题必须逐字命中输入（模型改写/新增条目一律不采信）
            warnings.append("来源不可溯: %s" % (title[:24] or "（空标题）"))
            continue
        if label not in LABELS:
            warnings.append("标签非法: %s" % (label[:12] or "（空标签）"))
            continue
        banned = [term for term in TRADE_ADVICE_TERMS if term in why]
        causal = [term for term in CAUSAL_TERMS if term in why]
        if banned or causal:
            warnings.append(
                "why 含%s: %s" % ("投资建议词" if banned else "因果措辞", "、".join(banned + causal))
            )
            if strict:
                continue
        if len(why) > NOTICE_WHY_MAX_CHARS:
            warnings.append("why 超长已截断: %s" % title[:24])
            why = why[:NOTICE_WHY_MAX_CHARS]
        results.append({"title": title, "label": label, "why": why})

    if not results:
        return {"results": [], "warnings": warnings, "reason": "blocked"}
    return {"results": results, "warnings": warnings, "reason": ""}


def classify_notice_points(
    conn, code: str, *, day: Optional[str] = None, refresh: bool = False
) -> Dict[str, Any]:
    """按需分类（打开弹窗时调用）。refresh=True（用户点刷新）跳过缓存读。永不抛。"""
    today = str(day or local_today_iso())[:10]
    normalized = str(code or "").strip()
    if not normalized:
        return _record(code="", day=today, mode="blocked", warnings=["code 为空"])

    cfg = load_ai_config(conn)
    if not cfg.enabled:
        return _record(code=normalized, day=today, mode="disabled", model=cfg.model)
    if not bool(cfg.features.get("notice_class")):
        # 用例关闭时不取数、不调模型（与其它用例同口径）
        return _record(code=normalized, day=today, mode="feature_disabled", model=cfg.model)

    if not refresh:
        cached = read_notice_cache(conn, normalized, day=today)
        if cached and _cache_usable(cached, day=today):
            cached["cached"] = True
            return cached

    name, items = notice_items(conn, normalized)
    if items is None:
        # 取数失败 ≠ 窗口内没有公告：写成 empty 会被当天缓存钉到 16:40，
        # 上午一次缓存抖动就让人一整天以为"这只没公告"（N1 的"主源失败 ≠ 空清单"同一类）。
        rec = _record(
            code=normalized,
            name=name,
            day=today,
            mode="blocked",
            model=cfg.model,
            warnings=["原因缓存读取失败"],
        )
        try:
            write_notice_cache(conn, rec)  # blocked 只钉 10 分钟（见 _cache_usable）
        except Exception:
            logger.exception("classify_notice_points: cache write failed")
        return rec
    if not items:
        # 空就承认空：不调模型，也不编"没有公告所以是技术性下跌"这类话
        rec = _record(code=normalized, name=name, day=today, mode="empty", model=cfg.model)
        try:
            write_notice_cache(conn, rec)
        except Exception:
            logger.exception("classify_notice_points: cache write failed")
        return rec

    try:
        payload = assemble_notice_payload(normalized, name, items)
    except Exception:
        logger.exception("classify_notice_points: payload failed")
        return _record(
            code=normalized, name=name, day=today, mode="blocked", model=cfg.model, items_count=len(items)
        )

    try:
        conn.commit()
    except Exception:
        pass

    result = call_ai(
        conn,
        cfg,
        "notice_class",
        notice_messages(payload),
        max_tokens=NOTICE_MAX_TOKENS,
        temperature=0.0,
        timeout_seconds=NOTICE_TIMEOUT_S,
    )
    if not result.get("ok"):
        reason = str(result.get("reason") or "blocked")
        mode = reason if reason in ("timeout", "budget", "not_configured") else "blocked"
        rec = _record(
            code=normalized, name=name, day=today, mode=mode, model=cfg.model, items_count=len(items)
        )
        try:
            write_notice_cache(conn, rec)
        except Exception:
            logger.exception("classify_notice_points: cache write failed")
        return rec

    reviewed = _review_results(
        str(result.get("text") or ""),
        allowed_titles={str(row.get("title") or "") for row in items},
        strict=not cfg.shadow_mode,
    )
    try:
        stamp_ai_warnings(conn, result.get("audit_id"), reviewed.get("warnings") or [])
    except Exception:
        logger.exception("classify_notice_points: stamp warnings failed")

    mode = "ok" if reviewed.get("results") else str(reviewed.get("reason") or "blocked")
    rec = _record(
        code=normalized,
        name=name,
        day=today,
        mode=mode,
        results=reviewed.get("results"),
        warnings=reviewed.get("warnings"),
        model=cfg.model,
        items_count=len(items),
    )
    # 影子模式不作特殊处理：站内结论本来就要人看，没有推送可拦（与 N6/nl_rule 同口径）。
    try:
        write_notice_cache(conn, rec)
    except Exception:
        logger.exception("classify_notice_points: cache write failed")
    return rec
