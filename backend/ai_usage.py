"""A6 用量与命中率统计 + 审计导出（全部只读）。

口径写死在这里，避免各处各算一套：
  attempted = `feature != 'test'` 的行数（试推不占用量口径）；ok / failed 同口径
  fail_rate = failed / attempted，attempted == 0 → 0.0
  by_feature 只列出现过的 feature；avg_ms 只对 `ok = 1` 行取平均，没有就 null
  by_reason  只统计 `ok = 0` 行的 reason（空 reason 归 "unknown"）
  daily      窗口内**每一天都在**（零调用的日子补 0）—— 空白的一天往往正是"cron 停了"
  reasons_hit 从**四张本地原因缓存表**统计，**不是**从 ai_call_log：
    审计里存的是 messages 摘要（还被截到 500 字），拿它算命中率会失真。
    news / notices / moves 按"命中持仓"过滤；market_news 是全市场电报、**没有 code**，
    所以只计入 by_source、不计入 days_with_hits —— 否则每天都有电报，这个数就没意义了。
  不猜成本：没有 token 单价表就不返回任何金额字段（只报调用数、耗时与 tokens）。

日界口径照抄 `ai_client._count_today_calls`（`created_at LIKE/substr 当天`），
不另立一套 —— 否则"总上限"和这里的统计会对不上。
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

try:
    from .database import local_today_iso
    from .reason_cache import _holding_codes
except ImportError:
    from database import local_today_iso
    from reason_cache import _holding_codes

USAGE_MAX_DAYS = 30
USAGE_DEFAULT_DAYS = 7
HIT_SOURCES = ("news", "notices", "moves", "market_news")
AUDIT_COLUMNS = (
    "id",
    "created_at",
    "feature",
    "model",
    "shadow",
    "ok",
    "reason",
    "status_code",
    "duration_ms",
    "tokens",
    "payload_json",
    "output_text",
    "warnings_json",
)
USAGE_NOTE = (
    "命中率来自本地原因缓存（保留 30 天）；days 上限 30；"
    "days_with_hits 只算命中持仓的来源，market_news 是全市场电报、没有 code，只计入 by_source"
)


def clamp_days(days: Any) -> int:
    try:
        value = int(days)
    except (TypeError, ValueError):
        value = USAGE_DEFAULT_DAYS
    return max(1, min(USAGE_MAX_DAYS, value))


def window(*, days: int) -> Tuple[str, str]:
    """返回 (since, until)，两端都含；"今天"按应用时区。"""
    until = str(local_today_iso())[:10]
    try:
        start = date.fromisoformat(until) - timedelta(days=clamp_days(days) - 1)
    except ValueError:
        return until, until
    return start.isoformat(), until


def _cell(row: Any, index: int, key: str) -> Any:
    if hasattr(row, "keys"):
        try:
            return row[key]
        except Exception:
            return None
    try:
        return row[index]
    except Exception:
        return None


def _count(conn, sql: str, params: Tuple[Any, ...]) -> int:
    try:
        row = conn.execute(sql, params).fetchone()
    except sqlite3.OperationalError:
        return 0
    return int((row["n"] if hasattr(row, "keys") else row[0]) or 0)


def _call_rows(conn, *, since: str, until: str) -> List[Any]:
    try:
        return conn.execute(
            "SELECT created_at, feature, ok, reason, duration_ms, tokens FROM ai_call_log "
            "WHERE substr(created_at, 1, 10) BETWEEN ? AND ? ORDER BY id",
            (since, until),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def _daily_skeleton(since: str, until: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    try:
        start = date.fromisoformat(since)
        end = date.fromisoformat(until)
    except ValueError:
        return out
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        out[key] = {"date": key, "ok": 0, "failed": 0}
        cursor = cursor + timedelta(days=1)
    return out


def reason_hit_stats(conn, *, days: int = USAGE_DEFAULT_DAYS) -> Dict[str, Any]:
    """窗口内"有没有拿到命中持仓的原因条目"—— 这是判断 AI 值不值的关键指标。"""
    since, until = window(days=days)
    codes = set()
    try:
        codes = {str(code) for code in (_holding_codes(conn) or [])}
    except Exception:
        codes = set()

    by_source = {name: 0 for name in HIT_SOURCES}
    hit_days = set()

    # 持仓来源：三条都带 code，按"在持仓里"过滤。
    holding_sources = (
        ("news", "SELECT code, substr(published_at, 1, 10) AS d FROM news_cache "
                 "WHERE substr(published_at, 1, 10) BETWEEN ? AND ?"),
        ("notices", "SELECT code, substr(date, 1, 10) AS d FROM notice_cache "
                    "WHERE substr(date, 1, 10) BETWEEN ? AND ?"),
        ("moves", "SELECT code, substr(date, 1, 10) AS d FROM intraday_move_cache "
                  "WHERE substr(date, 1, 10) BETWEEN ? AND ?"),
    )
    for name, sql in holding_sources:
        try:
            rows = conn.execute(sql, (since, until)).fetchall()
        except sqlite3.OperationalError:
            rows = []
        for row in rows:
            code = str(_cell(row, 0, "code") or "")
            day = str(_cell(row, 1, "d") or "")[:10]
            if code and code in codes:
                by_source[name] += 1
                if day:
                    hit_days.add(day)

    # 全市场电报：没有 code，"命中持仓"不成立 → 只计入 by_source（口径见 USAGE_NOTE）。
    by_source["market_news"] = _count(
        conn,
        "SELECT COUNT(*) AS n FROM market_news_cache WHERE substr(date, 1, 10) BETWEEN ? AND ?",
        (since, until),
    )

    return {
        "window_days": clamp_days(days),
        "days_with_hits": len(hit_days),
        "by_source": by_source,
        "holding_count": len(codes),
    }


def ai_usage_summary(conn, *, days: int = USAGE_DEFAULT_DAYS) -> Dict[str, Any]:
    days = clamp_days(days)
    since, until = window(days=days)
    rows = _call_rows(conn, since=since, until=until)

    attempted = ok_count = failed = 0
    by_feature: Dict[str, Dict[str, Any]] = {}
    by_reason: Dict[str, int] = {}
    daily = _daily_skeleton(since, until)

    for row in rows:
        feature = str(_cell(row, 1, "feature") or "")
        if feature == "test":
            continue  # 试推不占用量口径（与 ai_client 的日上限一致）
        attempted += 1
        is_ok = int(_cell(row, 2, "ok") or 0) == 1
        day = str(_cell(row, 0, "created_at") or "")[:10]
        slot = daily.setdefault(day, {"date": day, "ok": 0, "failed": 0})
        key = feature or "unknown"
        bucket = by_feature.setdefault(key, {"feature": key, "ok": 0, "failed": 0, "tokens": 0, "_ms": []})
        if is_ok:
            ok_count += 1
            slot["ok"] += 1
            bucket["ok"] += 1
            ms = _cell(row, 4, "duration_ms")
            if ms is not None:
                try:
                    bucket["_ms"].append(float(ms))
                except (TypeError, ValueError):
                    pass
        else:
            failed += 1
            slot["failed"] += 1
            bucket["failed"] += 1
            reason = str(_cell(row, 3, "reason") or "") or "unknown"
            by_reason[reason] = by_reason.get(reason, 0) + 1
        tokens = _cell(row, 5, "tokens")
        if tokens:
            try:
                bucket["tokens"] += int(tokens)
            except (TypeError, ValueError):
                pass

    features_out = []
    for key in sorted(by_feature):
        bucket = by_feature[key]
        samples = bucket.pop("_ms")
        bucket["avg_ms"] = round(sum(samples) / len(samples)) if samples else None
        features_out.append(bucket)

    return {
        "days": days,
        "since": since,
        "until": until,
        "calls": {
            "attempted": attempted,
            "ok": ok_count,
            "failed": failed,
            "fail_rate": (failed / attempted) if attempted else 0.0,
        },
        "by_feature": features_out,
        "by_reason": [{"reason": k, "count": by_reason[k]} for k in sorted(by_reason, key=lambda x: (-by_reason[x], x))],
        "daily": [daily[key] for key in sorted(daily)],
        "reasons_hit": reason_hit_stats(conn, days=days),
        "note": USAGE_NOTE,
    }


def audit_rows(conn, *, days: int = USAGE_DEFAULT_DAYS) -> List[Dict[str, Any]]:
    """窗口内的审计行。**不含任何密钥**：ai_call_log 本来就没有密钥列，
    payload_json 存的是 messages 摘要（请求头里的 key 从不落库）。"""
    days = clamp_days(days)
    since, until = window(days=days)
    try:
        rows = conn.execute(
            "SELECT %s FROM ai_call_log WHERE substr(created_at, 1, 10) BETWEEN ? AND ? ORDER BY id"
            % ", ".join(AUDIT_COLUMNS),
            (since, until),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if hasattr(row, "keys"):
            out.append({key: row[key] for key in row.keys()})
        else:
            out.append({key: row[i] for i, key in enumerate(AUDIT_COLUMNS)})
    return out


def audit_payload(conn, *, days: int = USAGE_DEFAULT_DAYS) -> Dict[str, Any]:
    """自描述的信封：复盘时要能知道"这份导出覆盖哪段窗口"。"""
    days = clamp_days(days)
    since, until = window(days=days)
    rows = audit_rows(conn, days=days)
    return {"since": since, "until": until, "days": days, "count": len(rows), "rows": rows}


def audit_json(conn, *, days: int = USAGE_DEFAULT_DAYS) -> str:
    return json.dumps(audit_payload(conn, days=days), ensure_ascii=False, indent=2)


def audit_csv(conn, *, days: int = USAGE_DEFAULT_DAYS) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(AUDIT_COLUMNS)
    for row in audit_rows(conn, days=days):
        writer.writerow(["" if row.get(key) is None else row.get(key) for key in AUDIT_COLUMNS])
    return buf.getvalue()


def audit_filename(fmt: str) -> str:
    return "ai-audit-%s.%s" % (str(local_today_iso()).replace("-", ""), "csv" if fmt == "csv" else "json")
