"""流水线心跳（dead-man switch）：让「根本没跑」自己喊出来。

前三道防线都默认「任务跑了」：备份失败写 stderr、行情同步失败返回 500、日终快照被价格闸门
拦下还会返回 skipped。但这些全是**事后翻日志**才能发现的事——真实失效场景是周末想看净值，
才发现周三起就没快照了。

所以给每条流水线两条命：

1. **对外 dead-man**：成功时 ping 一次 ``HEARTBEAT_<JOB>_URL``（healthchecks.io 这类）。
   我们这边不需要活着：整机宕机、cron 被删、容器起不来，外部服务超时后自己报警。
2. **对内逾期检查**：每次跑完把时间写进 ``settings.heartbeat:<job>:last_ok_at``，
   ``/cron/notify-events`` 里顺手判一次逾期，逾期就走 notify 的 ``ops`` 通道喊人。
   没配外部 URL 也能用，代价是「本进程还活着」时才会发现。

不做的事：不重试、不吞失败、不猜原因。心跳只负责「让谁知道」，不负责修。
"""
from __future__ import annotations

import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from .cash import set_setting
except ImportError:
    from cash import set_setting

HEARTBEAT_PREFIX = "heartbeat:"
_PREFIX_SLOT = HEARTBEAT_PREFIX
HEARTBEAT_EVENT = "ops"

#: job → 展示名 + 默认逾期阈值（小时）。
#: 阈值按「多久没成功就算出事」定，不是按 cron 频率：
#: - 备份每天一次，30h 足够容一次失败重跑；
#: - 行情/快照只看交易日，96h 能扛住四天长假，不会把正常休市当故障喊。
JOB_SPECS: Dict[str, Dict[str, Any]] = {
    "backup": {"label": "数据库备份", "max_age_hours": 30},
    "sync_prices": {"label": "行情同步", "max_age_hours": 96},
    "snapshot": {"label": "日终快照", "max_age_hours": 96},
}

DEFAULT_MAX_AGE_HOURS = 48
PING_TIMEOUT_SECONDS = 5.0


def _spec(job: str) -> Dict[str, Any]:
    """未知 job 也允许上报（宁可有记录，也不要因为写错名字静默丢弃）。"""
    spec = dict(JOB_SPECS.get(job) or {})
    spec.setdefault("label", job)
    spec.setdefault("max_age_hours", DEFAULT_MAX_AGE_HOURS)
    env_key = f"HEARTBEAT_{job.upper()}_MAX_AGE_HOURS"
    raw = os.environ.get(env_key)
    if raw:
        try:
            spec["max_age_hours"] = float(raw)
        except ValueError:
            pass
    return spec


def _key(job: str, field: str) -> str:
    return f"{_PREFIX_SLOT}{job}:{field}"


def _now(tz=None) -> datetime:
    if tz is None:
        try:
            try:
                from .database import LOCAL_TZ
            except ImportError:
                from database import LOCAL_TZ
            tz = LOCAL_TZ
        except Exception:
            tz = None
    return datetime.now(tz).replace(tzinfo=None) if tz else datetime.now()


def _get_text(conn, key: str, default: str = "") -> str:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return default
    if not row:
        return default
    value = row["value"] if isinstance(row, sqlite3.Row) else row[0]
    return default if value is None else str(value)


def _parse_dt(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "")[:19])
    except ValueError:
        return None


def record_heartbeat(
    conn,
    job: str,
    *,
    ok: bool = True,
    detail: str = "",
    at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """记一次运行结果。``ok=True`` 才刷新 ``last_ok_at``，失败只留痕不清零。"""
    stamp = (at or _now()).replace(microsecond=0)
    iso = stamp.isoformat(sep=" ")
    set_setting(conn, _key(job, "last_run_at"), iso)
    set_setting(conn, _key(job, "last_detail"), str(detail or "")[:500])
    if ok:
        set_setting(conn, _key(job, "last_ok_at"), iso)
    spec = _spec(job)
    return {
        "job": job,
        "label": spec["label"],
        "ok": bool(ok),
        "at": iso,
        "detail": str(detail or ""),
    }


def _job_status(conn, job: str, now: datetime) -> Dict[str, Any]:
    spec = _spec(job)
    last_ok_raw = _get_text(conn, _key(job, "last_ok_at"))
    last_run_raw = _get_text(conn, _key(job, "last_run_at"))
    detail = _get_text(conn, _key(job, "last_detail"))
    last_ok = _parse_dt(last_ok_raw)
    max_age = float(spec["max_age_hours"])
    age_hours: Optional[float] = None
    if last_ok is None:
        level = "never"
    else:
        age_hours = round(max((now - last_ok).total_seconds(), 0.0) / 3600.0, 2)
        if age_hours >= max_age:
            level = "overdue"
        elif age_hours >= max_age * 0.8:
            level = "due"
        else:
            level = "ok"
    return {
        "job": job,
        "label": spec["label"],
        "last_ok_at": last_ok_raw or None,
        "last_run_at": last_run_raw or None,
        "last_detail": detail or "",
        "age_hours": age_hours,
        "max_age_hours": max_age,
        # 「从来没有成功过」也算逾期：新装完忘了配 crontab 正是最需要被告知的情况,
        # 只在第一次成功上报之前喊（cooldown 兜住频率），之后就看 age 了。
        "overdue": level in ("overdue", "never"),
        "level": level,
        "external_url": bool(_external_url(job)),
    }


def heartbeat_status(
    conn, *, now: Optional[datetime] = None, jobs: Optional[List[str]] = None
) -> Dict[str, Any]:
    """所有流水线的心跳状态 + 逾期清单（前端运维页 & 逾期通知共用）。"""
    stamp = (now or _now()).replace(microsecond=0)
    names = list(jobs) if jobs is not None else list(JOB_SPECS.keys())
    rows = [_job_status(conn, job, stamp) for job in names]
    overdue = [row["job"] for row in rows if row["overdue"]]
    return {
        "checked_at": stamp.isoformat(sep=" "),
        "jobs": rows,
        "overdue": overdue,
        "ok": not overdue,
    }


def _external_url(job: str) -> str:
    return (os.environ.get(f"HEARTBEAT_{str(job).upper()}_URL") or "").strip()


def _mask(url: str) -> str:
    """日志里只留 host，别把 check 的 UUID 抄进日志/通知。"""
    try:
        parts = urllib.parse.urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}/…"
    except Exception:
        return "…"


def ping_external(job: str, *, ok: bool = True, url: Optional[str] = None,
                  timeout: float = PING_TIMEOUT_SECONDS) -> Dict[str, Any]:
    """成功才 ping 外部 dead-man；失败**故意不 ping** —— 让它超时后自己报警。

    任何异常都吞掉：外部服务连不上，不能反过来把备份/同步搞失败。
    """
    target = (url or _external_url(job)).strip()
    if not target:
        return {"pinged": False, "reason": "not_configured", "job": job}
    if not ok:
        return {"pinged": False, "reason": "failure_left_silent", "job": job}
    try:
        with urllib.request.urlopen(target, timeout=timeout) as resp:  # noqa: S310 (固定 https 白名单由用户配置)
            return {
                "pinged": True,
                "job": job,
                "status": getattr(resp, "status", None),
                "target": _mask(target),
            }
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {
            "pinged": False,
            "reason": "request_failed",
            "job": job,
            "target": _mask(target),
            "error": str(exc)[:200],
        }


def record_and_ping(conn, job: str, *, ok: bool = True, detail: str = "",
                    commit: bool = True) -> Dict[str, Any]:
    """记录心跳，成功时再 ping 外部 dead-man。

    先 ``commit`` 再 ping：外部服务挂掉时 urlopen 要等满 timeout，
    那 5 秒不能压在调用方的写事务里（行情同步就踩在写锁上）。
    """
    result = record_heartbeat(conn, job, ok=ok, detail=detail)
    if commit:
        try:
            conn.commit()
        except sqlite3.Error:
            pass
    result["ping"] = ping_external(job, ok=ok)
    return result


def _overdue_text(rows: List[Dict[str, Any]], checked_at: str) -> str:
    lines = [f"有 {len(rows)} 条流水线没按时跑成功："]
    for row in rows:
        if row["last_ok_at"]:
            age = row["age_hours"]
            head = f"{row['label']}：上次成功 {row['last_ok_at']}（{age:.0f} 小时前，阈值 {row['max_age_hours']:.0f} 小时）"
        else:
            head = f"{row['label']}：还没有任何成功记录（阈值 {row['max_age_hours']:.0f} 小时）"
        lines.append(f"- {head}")
        if row["last_detail"]:
            lines.append(f"  最近一次：{row['last_detail']}")
    lines.append(f"检查时间 {checked_at}")
    return "\n".join(lines)


def check_heartbeats(conn, *, notify: bool = True, force: bool = False,
                     now: Optional[datetime] = None) -> Dict[str, Any]:
    """逾期就喊人。挂在 ``/cron/notify-events`` 里跑，用户不用改 crontab。"""
    status = heartbeat_status(conn, now=now)
    overdue_rows = [row for row in status["jobs"] if row["overdue"]]
    result: Dict[str, Any] = {
        "checked_at": status["checked_at"],
        "overdue": status["overdue"],
        "notified": False,
    }
    if not overdue_rows:
        return result
    text = _overdue_text(overdue_rows, status["checked_at"])
    result["text"] = text
    if not notify:
        return result
    try:
        try:
            from .notify import dispatch
        except ImportError:
            from notify import dispatch

        result["notify"] = dispatch(
            text=text,
            title="流水线心跳逾期",
            event=HEARTBEAT_EVENT,
            conn=conn,
            force=force,
            respect_cooldown=not force,
        )
        result["notified"] = bool(result["notify"].get("sent"))
    except Exception as exc:  # 通知失败不能连带把 /cron/notify-events 打挂
        result["notify_error"] = str(exc)[:200]
    return result
