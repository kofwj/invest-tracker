"""A4 价格预警附言（`alert_note`）：payload、prompt、缓存、限次、影子。

注入点只有 `market.check_alerts` —— 它同时握着 `conn` 与 `triggered`，算好的附言作为参数
传给两个推送出口（`notify_price_alerts` / `notify_feishu_alerts`）。**AI 不进主链路**：
任何失败都返回 `""`，预警文本逐字节不变。

限次是三层叠加（前两层是 market 既有的，本模块只加第三层）：
  规则级：价格类 240 分钟冷却 / 百分比类升级式（既有）
  任务级：每日推送上限（既有）
  附言级：`(rule_id, 日期)` 缓存 + 单次 ≤3 条 + 当日 ≤6 次成功调用（本模块新增）
为什么非要第三层：3 分钟一轮的 cron，一条反复触发的规则会把额度吃光并刷屏。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from .ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from .ai_payload import ALLOWED_KEYS, build_payload, validate_output
    from .cash import set_setting
    from .database import LOCAL_TZ, local_today_iso
    from .market import PORTFOLIO_RULE_CODE, _holding_price_map, _portfolio_day_pnl, build_market_summary
    from .reason_cache import _holding_codes as _reason_holding_codes
    from .reason_cache import reasons_for_holdings
except ImportError:
    from ai_client import call_ai, load_ai_config, stamp_ai_warnings
    from ai_payload import ALLOWED_KEYS, build_payload, validate_output
    from cash import set_setting
    from database import LOCAL_TZ, local_today_iso
    from market import PORTFOLIO_RULE_CODE, _holding_price_map, _portfolio_day_pnl, build_market_summary
    from reason_cache import _holding_codes as _reason_holding_codes
    from reason_cache import reasons_for_holdings

NOTE_CACHE_PREFIX = "ai_alert_note_"
NOTE_MAX_CHARS = 60
NOTE_MAX_TOKENS = 120
# 盘中：失败立刻回落，绝不拖住推送。
NOTE_TIMEOUT_S = 30
NOTE_PER_RUN_LIMIT = 3
# 当天 feature='alert_note' 成功调用上限（叠在总上限之下，总上限默认 30）。
NOTE_DAILY_LIMIT = 6
# 一轮检查给附言的总预算：3 条 × 30s 最坏情况会占掉 3 分钟 cron 的一半，
# 超预算就停止生成本轮剩余的（已生成的照发；失败会缓存，不会反复打）。
NOTE_RUN_BUDGET_S = 20
NOTE_MAX_PEERS = 3
CACHE_KEEP_DAYS = 30
ALERT_EMPTY_LINE = "同期未找到相关公告或新闻"
SHADOW_HINT = "（影子模式：仅预览，不随推送发送）"

SYSTEM_PROMPT = """你是持仓预警助手。只能使用用户给出的 JSON 字段。
硬规则：
1. 引用制：不得引入清单之外的事件、公司、政策、时间。
2. 必须带来源：只能引用 JSON 里 reasons 的 title；没有条目就不写来源。
3. 禁止断言因果：只能写「同期有这些信息」，不得写「因为/由于/导致/拖累」。
4. 空则承认：reasons 与 moves 都为空时，只输出「同期未找到相关公告或新闻」。
5. 不得出现总资产、成本、仓位占比、组合涨跌幅。
6. 纯文本单句，以标的名称为主语，不超过 60 字，不要 markdown。

反面示例（禁止）：
因为农行发布人事公告，所以银行股下跌。
正面示例：
同期未找到相关公告或新闻。
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


def note_cache_key(as_of: str, rule_id: int) -> str:
    return "%s%s_%s" % (NOTE_CACHE_PREFIX, str(as_of or "")[:10], int(rule_id))


def read_note_cache(conn, as_of: str, rule_id: int) -> Optional[Dict[str, Any]]:
    raw = _get_setting(conn, note_cache_key(as_of, rule_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("date") or "")[:10] != str(as_of)[:10]:
        return None
    if int(data.get("rule_id") or -1) != int(rule_id):
        return None
    return data


def purge_note_cache(conn, *, as_of: str) -> None:
    try:
        cut = (
            datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date() - timedelta(days=CACHE_KEEP_DAYS)
        ).isoformat()
    except ValueError:
        return
    try:
        rows = conn.execute(
            # ESCAPE 必须显式声明：SQLite 里 `_` 默认是单字符通配、`\` 不是转义，
            # 只写 replace("_", "\\_") 而漏掉 ESCAPE，pattern 会一行都匹配不上、清理永不生效。
            "SELECT key FROM settings WHERE key LIKE ? ESCAPE '\\'",
            (NOTE_CACHE_PREFIX.replace("_", "\\_") + "%",),
        ).fetchall()
    except Exception:
        return
    for row in rows:
        key = str(row["key"] if hasattr(row, "keys") else row[0] or "")
        day_part = key[len(NOTE_CACHE_PREFIX) :][:10]
        if day_part and day_part < cut:
            try:
                conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            except Exception:
                pass


def write_note_cache(conn, record: Dict[str, Any], *, as_of: str, rule_id: int) -> None:
    payload = {
        "date": str(as_of)[:10],
        "rule_id": int(rule_id),
        "mode": record.get("mode") or "blocked",
        "text": record.get("text") or "",
        "warnings": list(record.get("warnings") or []),
        "model": record.get("model") or "",
        "generated_at": record.get("generated_at") or _now_local().strftime("%Y-%m-%d %H:%M:%S"),
    }
    set_setting(conn, note_cache_key(as_of, rule_id), json.dumps(payload, ensure_ascii=False))
    purge_note_cache(conn, as_of=as_of)


def today_note_calls(conn, day: str) -> int:
    """当天 `feature='alert_note'` 的成功调用数。

    口径照抄 `ai_client._count_today_calls`（`created_at LIKE 当天%` + `ok=1`）——
    另起一套日界口径只会让"总上限"和"附言上限"对不上。
    """
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM ai_call_log "
            "WHERE created_at LIKE ? AND ok = 1 AND IFNULL(feature,'') = 'alert_note'",
            (str(day)[:10] + "%",),
        ).fetchone()
        return int((row["n"] if hasattr(row, "keys") else row[0]) or 0)
    except sqlite3.OperationalError:
        return 0


def clip_note_text(text: str, *, limit: int = NOTE_MAX_CHARS) -> str:
    """超长时按句号截断；连一个完整句都没有就返回空串（宁可不附言，也不发半句）。"""
    body = (text or "").strip().strip("。") + "。" if (text or "").strip() else ""
    if len(body) <= limit:
        return body
    cut = body[:limit]
    pos = cut.rfind("。")
    if pos >= 0:
        return cut[: pos + 1]
    return ""


def _rule_id_of(trigger: Any) -> Optional[int]:
    """稳定整数 rule_id 才算数：拿不到就不调 AI、不写缓存（免得不同规则串用缓存）。"""
    if not isinstance(trigger, dict):
        return None
    raw = trigger.get("rule_id")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _portfolio_direction(holding_map: Dict[str, Any]) -> str:
    """只给词（up/down/flat），**不给数字** —— 金额与组合百分比永不同现。"""
    try:
        pct = _portfolio_day_pnl(holding_map or {}).get("change_pct")
    except Exception:
        logger.exception("ai_alert: portfolio day pnl failed")
        return "flat"
    if pct is None:
        return "flat"
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return "flat"
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _peers(holding_map: Dict[str, Any], trigger_code: str) -> List[Dict[str, Any]]:
    rows = []
    for code, row in (holding_map or {}).items():
        if not isinstance(row, dict) or str(code) == str(trigger_code):
            continue
        pct = row.get("change_pct")
        if pct is None:
            continue
        try:
            rows.append(
                {
                    "code": str(code),
                    "name": str(row.get("name") or code),
                    "change_pct": round(float(pct), 4),
                }
            )
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda item: abs(item["change_pct"]), reverse=True)
    return rows[:NOTE_MAX_PEERS]


def _benchmark(conn) -> Dict[str, Any]:
    try:
        summary = build_market_summary(conn) or {}
    except Exception:
        logger.exception("ai_alert: market summary failed")
        return {}
    for item in summary.get("indices") or []:
        if isinstance(item, dict) and str(item.get("code") or "") == "000300":
            return {"name": "沪深300", "change_pct": item.get("change_pct")}
    return {}


def assemble_alert_payload(conn, trigger: Dict[str, Any]) -> Dict[str, Any]:
    """按白名单构造 payload。只投喂"同期有什么"，不投喂任何金额与组合百分比。"""
    today = local_today_iso()
    holding_map: Dict[str, Any] = {}
    try:
        holding_map = _holding_price_map(conn) or {}
    except Exception:
        logger.exception("ai_alert: holding map failed")
        holding_map = {}

    trigger_code = str((trigger or {}).get("code") or "")
    reasons: List[Dict[str, Any]] = []
    moves: List[Dict[str, Any]] = []
    try:
        scope_codes = _reason_scope(conn, trigger)
        packed = reasons_for_holdings(conn, scope_codes, as_of=today) or {}
        reasons = packed.get("reasons") or []
        moves = packed.get("moves") or []
    except Exception:
        logger.exception("ai_alert: reasons failed")
        reasons, moves = [], []

    payload = build_payload(
        "alert_note",
        trigger={
            "code": (trigger or {}).get("code"),
            "name": (trigger or {}).get("name"),
            "change_pct": (trigger or {}).get("change_pct"),
            "rule": (trigger or {}).get("rule_type"),
        },
        portfolio_direction=_portfolio_direction(holding_map),
        peers=_peers(holding_map, trigger_code),
        benchmark=_benchmark(conn),
        reasons=reasons,
        moves=moves,
    )
    if set(payload) != ALLOWED_KEYS["alert_note"]:
        raise AssertionError("alert_note payload keys drifted: %s" % sorted(payload))
    return payload


def alert_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
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


def _note_names_its_target(text: str, trigger: Dict[str, Any]) -> bool:
    """附言得让人看出说的是哪条预警：至少提到标的名称或代码。"""
    body = str(text or "")
    name = str((trigger or {}).get("name") or "")
    code = str((trigger or {}).get("code") or "")
    if name and name in body:
        return True
    if code and code in body:
        return True
    return False


def _reason_scope(conn, trigger: Dict[str, Any]) -> List[str]:
    """附言是给**这一条**预警配的：只投喂该标的的原因条目。

    否则模型可能拿别的持仓的公告来解释它（附言只有 60 字，读者分不出说的是谁）。
    组合规则没有单一标的，"整个持仓"才是相关范围，所以退回全部持仓。
    """
    code = str((trigger or {}).get("code") or "")
    if code and code != PORTFOLIO_RULE_CODE:
        return [code]
    return _reason_holding_codes(conn)


def build_alert_note(conn, triggered: List[Dict[str, Any]]) -> str:
    """编排：永不抛；返回 "" 表示不加附言（失败、超限、影子模式都走这里）。

    决策顺序刻意"先便宜后昂贵"：开关 → 缓存命中 → 条数上限 → 当日额度 → 才调模型。
    """
    if not triggered:
        return ""
    try:
        cfg = load_ai_config(conn)
    except Exception:
        logger.exception("build_alert_note: load config failed")
        return ""
    if not cfg.enabled or not bool(cfg.features.get("alert_note")):
        return ""

    today = local_today_iso()
    notes: List[str] = []
    seen_rules = set()
    used = today_note_calls(conn, today)

    started = time.monotonic()
    for trigger in triggered:
        rule_id = _rule_id_of(trigger)
        if rule_id is None:
            # 拿不到 rule_id 就没法缓存与限次，跳过（不猜、不用占位符串缓存）。
            continue
        if rule_id in seen_rules:
            continue
        seen_rules.add(rule_id)
        if len(notes) >= NOTE_PER_RUN_LIMIT:
            break

        cached = read_note_cache(conn, today, rule_id)
        if cached is not None:
            if str(cached.get("text") or "").strip():
                notes.append(str(cached.get("text")).strip())
            continue

        if time.monotonic() - started >= NOTE_RUN_BUDGET_S:
            break
        if used >= NOTE_DAILY_LIMIT:
            break

        try:
            payload = assemble_alert_payload(conn, trigger)
        except Exception:
            logger.exception("build_alert_note: assemble failed")
            continue

        try:
            conn.commit()
        except Exception:
            pass

        result = call_ai(
            conn,
            cfg,
            "alert_note",
            alert_messages(payload),
            max_tokens=NOTE_MAX_TOKENS,
            temperature=0.2,
            timeout_seconds=NOTE_TIMEOUT_S,
        )
        if not result.get("ok"):
            # 失败也要落缓存：同一条规则同一天不再反复戳（保护额度，也保护推送延迟）。
            mode = "timeout" if str(result.get("reason") or "") == "timeout" else "blocked"
            try:
                write_note_cache(conn, _record(mode=mode, model=cfg.model), as_of=today, rule_id=rule_id)
            except Exception:
                logger.exception("build_alert_note: cache write failed")
            continue

        used += 1
        clipped = clip_note_text(str(result.get("text") or ""))
        checked = validate_output(
            "alert_note",
            clipped,
            payload,
            strict=not cfg.shadow_mode,
            shadow=cfg.shadow_mode,
        )
        warnings = list(checked.get("warnings") or [])
        if checked.get("ok") and checked.get("text") and not _note_names_its_target(str(checked["text"]), trigger):
            warnings.append("附言未提到标的名称或代码")
        try:
            stamp_ai_warnings(conn, result.get("audit_id"), warnings)
        except Exception:
            logger.exception("build_alert_note: stamp warnings failed")

        if not checked.get("ok") or not checked.get("text"):
            try:
                write_note_cache(
                    conn, _record(mode="blocked", warnings=warnings, model=cfg.model), as_of=today, rule_id=rule_id
                )
            except Exception:
                logger.exception("build_alert_note: cache write failed")
            continue

        text = str(checked["text"])
        try:
            write_note_cache(
                conn,
                _record(mode="ok", text=text, warnings=warnings, model=cfg.model),
                as_of=today,
                rule_id=rule_id,
            )
        except Exception:
            logger.exception("build_alert_note: cache write failed")
        notes.append(text)

    if not notes:
        return ""
    if cfg.shadow_mode:
        # 影子模式与 A3 同语义：照常调用、照写审计，但**不进推送**。
        return ""
    # 单次最多 3 条 × 每条 ≤60 字，按条目边界拼接（不截半个条目）。
    return "\n".join(notes[:NOTE_PER_RUN_LIMIT])
