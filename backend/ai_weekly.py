"""N2 周报 AI 段：把「这周钱从哪来」写成一段受约束的白话。

与 A3（晚报）**同一套管线**：payload 白名单 → 按周缓存 → 空数据短路 → call_ai → 裁剪 →
validate_output → 写缓存；影子模式只生成、只写审计、不进推送。差别只在 payload 与 prompt。

窗口 = **本周一 → min(本周五, 今天)**：
  · 周六早上推送（见 scripts/cron_sync_prices.sh 的建议行）时 Friday ≤ today，
    覆盖的正是"刚收完的那个交易周"，即用户说的"上一整周 / 上周分析"；
  · 手动在一周中间跑，end 夹到今天 = "本周至今"，不会把未来日期当区间终点。
  想改成"日历上的上周一~上周日"，只改 `week_bounds` 一个函数。

金额口径（**别照抄细则**）：用 `build_performance_summary(start, end)` 的**区间**字段
`period_gain` / `period_net_contribution`。它的 `total_gain` / `net_contribution` 是**全期**口径，
拿它当"这周赚了多少"会把开户以来的总收益写进周报 —— 与 `period_gain_pct` 的注释同一回事。

推送内容 = **确定性抬头（纯代码算，含区间收益/净投入/破线/到期）+ AI 段（≤150 字）**。
细则没写抬头，但只推一句"本周未找到相关公告或新闻"的周报没有意义；抬头由代码写数字，
AI 只负责"同期有没有对应信息"，两者的来源在输出校验里都能对回去。

缓存键 `ai_weekly_{ISO年}-W{周}`：同一周只调一次模型 —— 周报对日额度几乎零压力。
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from .ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from .ai_payload import ALLOWED_KEYS, build_payload, validate_output
    from .cash import set_setting
    from .database import LOCAL_TZ, local_today_iso
    from .discipline import build_discipline_report
    from .notify import check_deposit_due, notify_weekly_brief
    from .performance import build_performance_summary
    from .reason_cache import WINDOW_DAYS
    from .reason_cache import _holding_codes as _reason_holding_codes
    from .reason_cache import reasons_for_holdings
except ImportError:
    from ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from ai_payload import ALLOWED_KEYS, build_payload, validate_output
    from cash import set_setting
    from database import LOCAL_TZ, local_today_iso
    from discipline import build_discipline_report
    from notify import check_deposit_due, notify_weekly_brief
    from performance import build_performance_summary
    from reason_cache import WINDOW_DAYS
    from reason_cache import _holding_codes as _reason_holding_codes
    from reason_cache import reasons_for_holdings

WEEKLY_CACHE_PREFIX = "ai_weekly_"
WEEKLY_MAX_CHARS = 150
WEEKLY_MAX_TOKENS = 200
# 非时效敏感（一周一次、结果缓存），与 A3 一样给足预算。
WEEKLY_TIMEOUT_S = 120
WEEKLY_EMPTY_LINE = "本周未找到相关公告或新闻"
CACHE_KEEP_DAYS = 30

SYSTEM_PROMPT = """你是持仓周报助手。只能使用用户给出的 JSON 字段。
硬规则：
1. 引用制：不得引入清单之外的事件、公司、政策、时间。
2. 必须带来源：每条事实后跟 [标题]，标题必须与 JSON 里 reasons/moves 的 title 完全一致。
3. 禁止断言因果：只能写「同期有这些信息」，不得写「因为/由于/导致/拖累」。
4. 空则承认：reasons 与 moves 都为空时，输出「本周未找到相关公告或新闻」。
5. 不要重复复述金额与条数（抬头已经写了），也不要写具体日期区间，只说"本周"；
   字段为 null 表示**算不出来**（缺基准快照）：不要写成 0，也不要写"本周没有盈亏 / 基本持平"。
6. 禁止出现总资产、成本、仓位占比、组合涨跌幅、任何买卖建议。
纯文本，无 markdown 标题，不超过 150 字。

反面示例（禁止）：
因为农行发布人事公告，所以银行股整周承压。
正面示例：
本周未找到相关公告或新闻。
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


def week_bounds(today_iso: Optional[str] = None) -> Tuple[str, str]:
    """本周一 → min(本周五, 今天)。周六/周日跑时周一仍是本周的那一个（ISO 周）。"""
    today = str(today_iso or local_today_iso())[:10]
    try:
        day = date.fromisoformat(today)
    except ValueError:
        return today, today
    monday = day - timedelta(days=day.weekday())
    friday = monday + timedelta(days=4)
    return monday.isoformat(), min(friday, day).isoformat()


def week_tag(start_iso: str) -> str:
    """`2026-W40`：按 ISO 周（周一起算），同周只调一次模型。"""
    try:
        day = date.fromisoformat(str(start_iso)[:10])
    except ValueError:
        return str(start_iso)[:10]
    iso = day.isocalendar()
    return "%04d-W%02d" % (iso[0], iso[1])


def weekly_cache_key(start_iso: str) -> str:
    return "%s%s" % (WEEKLY_CACHE_PREFIX, week_tag(start_iso))


def read_weekly_cache(conn, start_iso: str) -> Optional[Dict[str, Any]]:
    raw = _get_setting(conn, weekly_cache_key(start_iso))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("week") or "") != week_tag(start_iso):
        return None
    return data


def purge_weekly_cache(conn, *, as_of: str) -> None:
    try:
        cut_start = (
            date.fromisoformat(str(as_of)[:10]) - timedelta(days=CACHE_KEEP_DAYS)
        ).isoformat()
    except ValueError:
        return
    try:
        rows = conn.execute(
            # ESCAPE 必须显式声明：`_` 在 SQLite 的 LIKE 里是单字符通配、`\` 不是转义，
            # 只做 replace 不加 ESCAPE 会一行都匹配不到、清理永不生效（A4 踩过同一个坑）。
            "SELECT key FROM settings WHERE key LIKE ? ESCAPE '\\'",
            (WEEKLY_CACHE_PREFIX.replace("_", "\\_") + "%",),
        ).fetchall()
    except Exception:
        return
    for row in rows:
        key = str(row["key"] if hasattr(row, "keys") else row[0] or "")
        tag = key[len(WEEKLY_CACHE_PREFIX) :]
        try:  # 缓存键是 2026-W40，按"那一周的周一"判断是否过期
            year, week = tag.split("-W")
            week_start = date.fromisocalendar(int(year), int(week), 1).isoformat()
        except Exception:
            continue
        if week_start < cut_start:
            try:
                conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            except Exception:
                pass


def write_weekly_cache(conn, record: Dict[str, Any], *, start_iso: str) -> None:
    payload = {
        "week": week_tag(start_iso),
        "window_start": str(start_iso)[:10],
        "mode": record.get("mode") or "blocked",
        "text": record.get("text") or "",
        "warnings": list(record.get("warnings") or []),
        "model": record.get("model") or "",
        "generated_at": record.get("generated_at") or _now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }
    set_setting(conn, weekly_cache_key(start_iso), json.dumps(payload, ensure_ascii=False))
    purge_weekly_cache(conn, as_of=start_iso)


def _money(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return "—"
    return "%s¥%s" % ("-" if amount < 0 else "+", "{:,.0f}".format(abs(amount)))


def build_weekly_header(summary: Dict[str, Any], *, start: str, end: str, breaches: int, due: Dict[str, Any]) -> str:
    """确定性抬头：数字全部由代码写（AI 关着也照发，AI 开着只是后面多一段）。"""
    lines = ["【周报 %s ~ %s】" % (start[5:], end[5:])]
    gain = (summary or {}).get("period_gain")
    flow = (summary or {}).get("period_net_contribution")
    if gain is None:
        # 没有基准快照时不能编数字：明明算不出来却写 0，就等于告诉用户"这周没盈亏"。
        lines.append("区间收益：缺少基准快照，算不出（净投入 %s）" % _money(flow))
    else:
        lines.append("区间收益 %s（净投入 %s）" % (_money(gain), _money(flow)))
    extras = []
    if breaches:
        extras.append("纪律破线 %d 条" % breaches)
    due_total = sum(len(due.get(key) or []) for key in ("overdue", "d0", "d7", "d30"))
    if due_total:
        extras.append("存款到期 %d 笔" % due_total)
    if extras:
        lines.append(" · ".join(extras))
    return "\n".join(lines)


def assemble_weekly_payload(conn, *, start: str, end: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """按白名单构造 payload，并返回同一批数字给确定性抬头用（**只算一次**，两处不会打架）。"""
    summary: Dict[str, Any] = {}
    try:
        summary = build_performance_summary(conn, start, end) or {}
    except Exception:
        logger.exception("assemble_weekly_payload: performance failed")
        summary = {}

    disc: Dict[str, Any] = {}
    try:
        disc = build_discipline_report(conn) or {}
    except Exception:
        logger.exception("assemble_weekly_payload: discipline failed")
        disc = {}
    breaches = [
        b for b in (disc.get("breaches") or []) if isinstance(b, dict) and b.get("level") == "warning"
    ]

    due: Dict[str, Any] = {}
    try:
        due = (check_deposit_due(conn) or {}).get("buckets") or {}
    except Exception:
        logger.exception("assemble_weekly_payload: deposits failed")
        due = {}

    reasons: List[Dict[str, Any]] = []
    moves: List[Dict[str, Any]] = []
    coverage: Dict[str, Any] = {
        "matched": 0,
        "window_days": WINDOW_DAYS["notice"],
        "note": "",
    }
    try:
        packed = reasons_for_holdings(conn, _reason_holding_codes(conn), as_of=end) or {}
        reasons = packed.get("reasons") or []
        moves = packed.get("moves") or []
        coverage = packed.get("reason_coverage") or coverage
    except Exception:
        logger.exception("assemble_weekly_payload: reasons failed")
        reasons, moves = [], []

    payload = build_payload(
        "weekly",
        window_start=start,
        window_end=end,
        net_gain=summary.get("period_gain"),
        external_flow=summary.get("period_net_contribution"),
        discipline_breach_count=len(breaches),
        plans=disc.get("plans") or [],
        deposits_due=due,
        reasons=reasons,
        moves=moves,
        reason_coverage=coverage,
    )
    if set(payload) != ALLOWED_KEYS["weekly"]:
        raise AssertionError("weekly payload keys drifted: %s" % sorted(payload))
    return payload, {"summary": summary, "breaches": len(breaches), "due": due}


def weekly_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def clip_weekly_text(text: str, *, limit: int = WEEKLY_MAX_CHARS) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    cut = body[:limit]
    pos = cut.rfind("。")
    if pos >= 0:
        return cut[: pos + 1]
    return ""


def _record(*, mode: str, text: str = "", warnings=None, model: str = "") -> Dict[str, Any]:
    return {
        "mode": mode,
        "text": text or "",
        "warnings": list(warnings or []),
        "model": model or "",
        "generated_at": _now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }


def generate_weekly_segment(conn, *, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    """生成本周 AI 段（写缓存）。永不抛。"""
    if not start or not end:
        start, end = week_bounds()

    cfg = load_ai_config(conn)
    if not cfg.enabled or not bool(cfg.features.get("weekly")):
        return _record(mode="disabled")

    cached = read_weekly_cache(conn, start)
    if cached:
        return cached

    try:
        conn.commit()
    except Exception:
        pass

    try:
        payload, context = assemble_weekly_payload(conn, start=start, end=end)
    except Exception:
        logger.exception("generate_weekly_segment: assemble failed")
        # 组包失败是"我们这边出错了"，不是"本周没内容"：同样不写缓存，别钉一周。
        return _record(mode="blocked")

    header = build_weekly_header(
        context["summary"], start=start, end=end, breaches=context["breaches"], due=context["due"]
    )

    if not (payload.get("reasons") or payload.get("moves")):
        # 空数据周：不调模型（与 A3 同口径），但抬头照发 —— 周报本来就要有数字。
        rec = _record(mode="empty", text=WEEKLY_EMPTY_LINE, model=cfg.model)
        rec["header"] = header
        try:
            write_weekly_cache(conn, rec, start_iso=start)
        except Exception:
            logger.exception("generate_weekly_segment: cache write failed")
        return rec

    try:
        conn.commit()
    except Exception:
        pass

    result = call_ai(
        conn,
        cfg,
        "weekly",
        weekly_messages(payload),
        max_tokens=WEEKLY_MAX_TOKENS,
        temperature=0.2,
        timeout_seconds=WEEKLY_TIMEOUT_S,
    )
    if not result.get("ok"):
        mode = "timeout" if str(result.get("reason") or "") == "timeout" else "blocked"
        rec = _record(mode=mode, model=cfg.model)
        rec["header"] = header
        # 失败**不写缓存**：周报一周只跑一次（周六 08:30），按成功一样钉住整周的话，
        # 一次超时这周的 AI 段就再也不会重试（`force` 只影响推送、不跳过生成缓存）。
        # 不缓存 → 再跑一次就重试；cron 一周一次，没有 A4 那种刷屏风险。
        return rec

    clipped = clip_weekly_text(str(result.get("text") or ""))
    checked = validate_output(
        "weekly",
        clipped,
        payload,
        strict=not cfg.shadow_mode,
        shadow=cfg.shadow_mode,
    )
    try:
        stamp_ai_warnings(conn, result.get("audit_id"), checked.get("warnings") or [])
    except Exception:
        logger.exception("generate_weekly_segment: stamp warnings failed")

    if not checked.get("ok") or not checked.get("text"):
        rec = _record(mode="blocked", warnings=checked.get("warnings"), model=cfg.model)
    else:
        rec = _record(
            mode="ok",
            text=str(checked.get("text") or ""),
            warnings=checked.get("warnings"),
            model=cfg.model,
        )
    rec["header"] = header
    try:
        write_weekly_cache(conn, rec, start_iso=start)
    except Exception:
        logger.exception("generate_weekly_segment: cache write failed")
    return rec


def run_weekly_brief(conn, *, notify: bool = True, force: bool = False) -> Dict[str, Any]:
    """cron 入口：生成（或读缓存）+ 可选推送。永不抛。"""
    start, end = week_bounds()
    try:
        segment = generate_weekly_segment(conn, start=start, end=end)
    except Exception:
        logger.exception("run_weekly_brief: generate failed")
        segment = _record(mode="blocked")

    mode = str(segment.get("mode") or "")
    text = str(segment.get("text") or "").strip()
    header = str(segment.get("header") or "").strip()
    # 抬头是代码算的，缓存里没有时（例如从缓存读出的老记录）现算一份，保证推送不缺数字。
    if not header:
        try:
            payload, context = assemble_weekly_payload(conn, start=start, end=end)
            header = build_weekly_header(
                context["summary"], start=start, end=end, breaches=context["breaches"], due=context["due"]
            )
        except Exception:
            logger.exception("run_weekly_brief: header rebuild failed")

    body = "\n".join([part for part in (header, text) if part])
    result: Dict[str, Any] = {
        "window_start": start,
        "window_end": end,
        "mode": mode,
        "text": text,
        "sent": False,
    }
    if not notify:
        return result

    if mode == "disabled":
        # 总开关或用例关着：连抬头也不推（细则 §2.8.6 要求"不推送"）。
        # 抬头是代码算的没错，但"周报"这个功能关着就该安静。
        result["reason"] = "disabled"
        return result
    cfg = load_ai_config(conn)
    if cfg.shadow_mode:
        # 影子模式与 A3 一致：照常生成、照写审计，但不进推送。
        result["reason"] = "shadow"
        return result
    if not body:
        result["reason"] = "empty"
        return result
    result["text"] = body
    try:
        send = notify_weekly_brief(body, conn=conn, force=force)
    except Exception as exc:
        logger.exception("run_weekly_brief: dispatch failed")
        result["reason"] = str(exc)[:200]
        return result
    result["sent"] = bool((send or {}).get("sent"))
    result["dispatch"] = send
    return result
