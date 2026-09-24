"""akshare reason fetchers. Lazy import. Never raise.

Return [] if empty, None if the source failed or timed out.
"""
from __future__ import annotations

import contextlib
import io
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

NOTICE_DEADLINE_S = 150.0
NOTICE_TOTAL_BUDGET_S = 300.0
NOTICE_LOOKBACK_DAYS = 3

DEFAULT_MOVE_BOARDS = (
    "大笔卖出",
    "封跌停板",
    "打开涨停板",
    "60日新低",
    "60日大幅下跌",
    "向下缺口",
    "大笔买入",
    "封涨停板",
    "打开跌停板",
    "火箭发射",
)

NEWS_TITLE_NAMES = ("新闻标题", "标题", "title")
NEWS_CONTENT_NAMES = ("新闻内容", "内容", "content")
NEWS_TIME_NAMES = ("发布时间", "时间", "published_at", "日期")
NEWS_SOURCE_NAMES = ("文章来源", "来源", "source")
NEWS_URL_NAMES = ("新闻链接", "链接", "url", "网址")

NOTICE_CODE_NAMES = ("代码", "股票代码", "code")
NOTICE_NAME_NAMES = ("名称", "股票简称", "name")
NOTICE_TYPE_NAMES = ("公告类型", "类型", "notice_type")
NOTICE_TITLE_NAMES = ("公告标题", "标题", "title")
NOTICE_DATE_NAMES = ("公告日期", "日期", "date")
NOTICE_URL_NAMES = ("网址", "链接", "url")

GLOBAL_TITLE_NAMES = ("标题", "title")
GLOBAL_CONTENT_NAMES = ("内容", "content")
GLOBAL_DATE_NAMES = ("发布日期", "日期", "date")
GLOBAL_TIME_NAMES = ("发布时间", "时间", "published_at")

MOVE_TIME_NAMES = ("时间", "event_time", "异动时间")
MOVE_CODE_NAMES = ("代码", "股票代码", "code")
MOVE_NAME_NAMES = ("名称", "股票简称", "name")


def _with_deadline(fn, *, deadline_s: float, default):
    """Run fn in a daemon thread; return default if it exceeds deadline_s.

    The worker cannot be killed after timeout. Notices use one thread per
    lookback day (capped by NOTICE_TOTAL_BUDGET_S); leaked threads are
    bounded by cron frequency, not killed.
    """
    box = [default]

    def runner():
        try:
            box[0] = fn()
        except Exception:
            box[0] = default

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(deadline_s)
    if thread.is_alive():
        return default
    return box[0]


_STDERR_LOCK = threading.Lock()


@contextlib.contextmanager
def _quiet_stderr():
    """Mute tqdm. Only one redirect_stderr layer at a time (timeout leaks)."""
    previous = os.environ.get("TQDM_DISABLE")
    os.environ["TQDM_DISABLE"] = "1"
    held = _STDERR_LOCK.acquire(blocking=False)
    buf = io.StringIO()
    try:
        if held:
            with contextlib.redirect_stderr(buf):
                yield
        else:
            yield
    finally:
        if held:
            _STDERR_LOCK.release()
        if previous is None:
            os.environ.pop("TQDM_DISABLE", None)
        else:
            os.environ["TQDM_DISABLE"] = previous


def _ok(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text not in ("", "nan", "None", "NaT")


def _str(value: Any) -> str:
    if not _ok(value):
        return ""
    if hasattr(value, "strftime"):
        try:
            if hasattr(value, "year") and hasattr(value, "hour"):
                return value.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(value, "year"):
                return value.strftime("%Y-%m-%d")
            if hasattr(value, "hour"):
                return value.strftime("%H:%M:%S")
        except Exception:
            pass
    return str(value).strip()


def akshare_yyyymmdd(date: str) -> str:
    """akshare stock_notice_report wants YYYYMMDD, not ISO."""
    digits = "".join(ch for ch in str(date or "") if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ""


def notice_lookback_days(date: str, lookback_days: int = NOTICE_LOOKBACK_DAYS) -> List[str]:
    end = akshare_yyyymmdd(date)
    if not end:
        return []
    try:
        end_d = datetime.strptime(end, "%Y%m%d").date()
    except ValueError:
        return [end]
    n = max(1, int(lookback_days))
    return [(end_d - timedelta(days=i)).strftime("%Y%m%d") for i in range(n - 1, -1, -1)]


def iso_day(date: str) -> str:
    digits = "".join(ch for ch in str(date or "") if ch.isdigit())
    if len(digits) >= 8:
        return "%s-%s-%s" % (digits[:4], digits[4:6], digits[6:8])
    text = str(date or "").strip()
    return text[:10] if len(text) >= 10 and text[4] == "-" else text


def combine_published_at(date_part: str, time_part: str, fallback_day: str = "") -> str:
    day = iso_day(date_part) if date_part else iso_day(fallback_day)
    clock = str(time_part or "").strip()
    if clock and ":" in clock:
        if " " in clock:
            return clock
        clock = clock[:8]
        return ("%s %s" % (day, clock)).strip()
    return day or iso_day(fallback_day)


def _rows_from_df(df) -> tuple:
    if df is None:
        return [], []
    if hasattr(df, "empty") and bool(df.empty):
        return [], []
    if isinstance(df, list):
        columns = list(df[0].keys()) if df and isinstance(df[0], dict) else []
        return df, [str(c) for c in columns]
    try:
        columns = [str(c) for c in list(df.columns)]
        records = df.to_dict(orient="records")
        return records, columns
    except Exception:
        return [], []


def _has_any(columns: Sequence[str], names: Sequence[str]) -> bool:
    colset = {str(c) for c in columns}
    return any(name in colset for name in names)


def _val(record: Dict[str, Any], columns: Sequence[str], names: Sequence[str], pos: int) -> str:
    for name in names:
        if isinstance(record, dict) and name in record and _ok(record.get(name)):
            return _str(record.get(name))
        if isinstance(record, dict):
            for key, value in record.items():
                if str(key) == name and _ok(value):
                    return _str(value)
    if columns and 0 <= pos < len(columns):
        key = columns[pos]
        if isinstance(record, dict) and key in record and _ok(record.get(key)):
            return _str(record.get(key))
    if isinstance(record, dict):
        values = list(record.values())
        if 0 <= pos < len(values) and _ok(values[pos]):
            return _str(values[pos])
    return ""


def _norm_code(code: Any) -> str:
    text = str(code or "").strip().upper()
    for suffix in (".SH", ".SZ", ".BJ"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return ""
    return digits.zfill(6) if len(digits) <= 6 else digits


def _safe_ak(call, *args, **kwargs):
    try:
        import akshare as ak  # lazy: not required for app boot / unit tests

        fn = getattr(ak, call)
        return fn(*args, **kwargs)
    except Exception:
        logger.exception("akshare %s failed", call)
        return None


def fetch_stock_news(code: str, *, limit: int = 10) -> List[Dict[str, Any]]:
    code_n = _norm_code(code)
    if not code_n:
        return []
    try:
        df = _safe_ak("stock_news_em", symbol=code_n)
        records, columns = _rows_from_df(df)
        if not records:
            return []
        expected = NEWS_TITLE_NAMES + NEWS_CONTENT_NAMES + NEWS_TIME_NAMES
        if not _has_any(columns, expected):
            return []
        out: List[Dict[str, Any]] = []
        for row in records[: max(1, int(limit))]:
            title = _val(row, columns, NEWS_TITLE_NAMES, 1)
            if not title:
                continue
            out.append(
                {
                    "code": code_n,
                    "kind": "news",
                    "title": title,
                    "content": _val(row, columns, NEWS_CONTENT_NAMES, 2),
                    "published_at": _val(row, columns, NEWS_TIME_NAMES, 3),
                    "source": _val(row, columns, NEWS_SOURCE_NAMES, 4),
                    "url": _val(row, columns, NEWS_URL_NAMES, 5),
                }
            )
        return out
    except Exception:
        logger.exception("fetch_stock_news failed for %s", code_n)
        return []


def _fetch_notices_impl(date: str) -> Optional[List[Dict[str, Any]]]:
    df = _safe_ak("stock_notice_report", date=date)
    if df is None:
        return None
    records, columns = _rows_from_df(df)
    if not records:
        return []
    expected = NOTICE_CODE_NAMES + NOTICE_TITLE_NAMES
    if not _has_any(columns, expected):
        return []
    out: List[Dict[str, Any]] = []
    for row in records:
        code = _norm_code(_val(row, columns, NOTICE_CODE_NAMES, 0))
        title = _val(row, columns, NOTICE_TITLE_NAMES, 3)
        if not code or not title:
            continue
        out.append(
            {
                "code": code,
                "name": _val(row, columns, NOTICE_NAME_NAMES, 1),
                "kind": "notice",
                "notice_type": _val(row, columns, NOTICE_TYPE_NAMES, 2),
                "title": title,
                "date": iso_day(_val(row, columns, NOTICE_DATE_NAMES, 4) or date),
                "url": _val(row, columns, NOTICE_URL_NAMES, 5),
            }
        )
    return out


def fetch_notices(date: str, *, lookback_days: int = NOTICE_LOOKBACK_DAYS) -> Optional[List[Dict[str, Any]]]:
    """Return notices over lookback_days, [] if none, None if every day failed.

    Each day has its own deadline so a slow day does not discard earlier days.
    """
    days = notice_lookback_days(date, lookback_days)
    if not days:
        return []
    merged: List[Dict[str, Any]] = []
    any_ok = False
    started = time.monotonic()
    try:
        for i, day in enumerate(days):
            elapsed = time.monotonic() - started
            if i > 0 and elapsed >= NOTICE_TOTAL_BUDGET_S:
                logger.warning(
                    "fetch_notices stopping after %.0fs, skip remaining days", elapsed
                )
                break
            remaining = NOTICE_TOTAL_BUDGET_S - elapsed
            deadline = NOTICE_DEADLINE_S if i == 0 else min(NOTICE_DEADLINE_S, remaining)
            if deadline <= 0:
                break

            def _run(ak_day=day):
                with _quiet_stderr():
                    return _fetch_notices_impl(ak_day)

            part = _with_deadline(_run, deadline_s=deadline, default=None)
            if part is None:
                continue
            if not isinstance(part, list):
                continue
            any_ok = True
            merged.extend(part)
        return merged if any_ok else None
    except Exception:
        logger.exception("fetch_notices failed")
        return merged if any_ok else None


def fetch_global_news(date: str) -> Optional[List[Dict[str, Any]]]:
    day = iso_day(date)
    try:
        df = _safe_ak("stock_info_global_cls")
        if df is None:
            return None
        records, columns = _rows_from_df(df)
        expected = GLOBAL_TITLE_NAMES + GLOBAL_CONTENT_NAMES + GLOBAL_DATE_NAMES
        if not _has_any(columns, expected):
            return []
        out: List[Dict[str, Any]] = []
        for row in records:
            title = _val(row, columns, GLOBAL_TITLE_NAMES, 0)
            if not title:
                continue
            date_part = _val(row, columns, GLOBAL_DATE_NAMES, 3) or day
            time_part = _val(row, columns, GLOBAL_TIME_NAMES, 2)
            out.append(
                {
                    "kind": "market_news",
                    "title": title,
                    "content": _val(row, columns, GLOBAL_CONTENT_NAMES, 1),
                    "published_at": combine_published_at(date_part, time_part, day),
                }
            )
        return out
    except Exception:
        logger.exception("fetch_global_news failed")
        return None


def fetch_intraday_moves(boards: Sequence[str], date: str) -> Optional[List[Dict[str, Any]]]:
    """Return moves, [] if none, None if every board failed."""
    day = str(date or "").strip()
    names = [str(b or "").strip() for b in (boards or ()) if str(b or "").strip()]
    if not names:
        return []
    out: List[Dict[str, Any]] = []
    ok_boards = 0
    fail_boards = 0
    for name in names:
        try:
            df = _safe_ak("stock_changes_em", symbol=name)
            if df is None:
                fail_boards += 1
                continue
            records, columns = _rows_from_df(df)
            if not records:
                ok_boards += 1
                continue
            if not _has_any(columns, MOVE_CODE_NAMES + MOVE_NAME_NAMES + MOVE_TIME_NAMES):
                fail_boards += 1
                continue
            ok_boards += 1
            for row in records:
                code = _norm_code(_val(row, columns, MOVE_CODE_NAMES, 1))
                event_time = _val(row, columns, MOVE_TIME_NAMES, 0)
                if not code or not event_time:
                    continue
                out.append(
                    {
                        "code": code,
                        "name": _val(row, columns, MOVE_NAME_NAMES, 2),
                        "kind": "move",
                        "board": name,
                        "event_time": event_time,
                        "date": day,
                    }
                )
        except Exception:
            logger.exception("fetch_intraday_moves failed for %s", name)
            fail_boards += 1
            continue
    if fail_boards:
        logger.warning("intraday moves: %s/%s boards failed", fail_boards, len(names))
    if ok_boards == 0:
        return None
    return out
