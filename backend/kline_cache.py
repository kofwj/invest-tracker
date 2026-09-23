"""日K缓存：从腾讯/东方财富拉前复权日K，增量存入 kline_cache 表。

数据源复用 return_sync.fetch_tencent_kline_closes 的接口，但保留完整 OHLC（开高低收量额）。
"""
from __future__ import annotations

import json as pyjson
import logging
import math
import urllib.request
from datetime import date as dt_date, datetime
from typing import List

import sqlite3

try:
    from .database import LOCAL_TZ, db_session
except ImportError:
    from database import LOCAL_TZ, db_session

logger = logging.getLogger(__name__)

KLINE_TABLE = "kline_cache"
KLINE_DEFAULT_DAYS = 400  # 腾讯接口默认返回近 420 个交易日


def ensure_kline_cache_table(conn):
    """幂等建表；老库通过 schema migration 触发，这里兜底。"""
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({KLINE_TABLE})").fetchall()]
    if not cols:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {KLINE_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code, date)
        )""")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{KLINE_TABLE}_code_date ON {KLINE_TABLE}(code, date DESC)")


# ---------------------------------------------------------------------------
# 数据拉取
# ---------------------------------------------------------------------------

def _market_prefix(code: str) -> str:
    c = str(code or "").strip().lower().replace("f", "")
    return "sh" if c.startswith(("5", "6", "9")) else "sz"


def _fnum(v, default=0.0):
    """float 且只放行有限值：NaN/Inf/空串统一回退 default，避免写库和 JSON 序列化出非法值。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _tencent_symbol(code: str) -> str:
    c = str(code or "").strip().lower().replace("f", "")
    return _market_prefix(c) + c


def fetch_tencent_kline_ohlc(code: str, count: int = 420) -> List[dict]:
    """从腾讯接口拉前复权日K完整 OHLC。返回 [{date,open,high,low,close,volume,amount}]"""
    symbol = _tencent_symbol(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{count},qfq"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    data = pyjson.loads(raw).get("data", {})
    # 某些标的腾讯返回 data 直接是 {symbol: {...}}，但空 code 可能返回空 dict 或 list
    if not isinstance(data, dict):
        return []
    symbol_data = data.get(symbol, {})
    rows = symbol_data.get("qfqday") or symbol_data.get("day") or []
    out = []
    for r in rows:
        try:
            out.append({
                "date": str(r[0]),
                "open": _fnum(r[1]),
                "close": _fnum(r[2]),
                "high": _fnum(r[3]),
                "low": _fnum(r[4]),
                "volume": _fnum(r[5]) if len(r) > 5 else 0.0,
                "amount": _fnum(r[6]) if len(r) > 6 else 0.0,
            })
        except (IndexError, ValueError, TypeError) as exc:
            logger.debug("skip kline row for %s: %s", code, exc)
    return out


def fetch_eastmoney_kline_ohlc(code: str, count: int = 420) -> List[dict]:
    """东方财富日K兜底。"""
    try:
        import akshare as ak  # lazy
    except ImportError:
        return []
    c = str(code or "").strip().lower().replace("f", "")
    try:
        df = ak.stock_zh_a_hist(symbol=c, period="daily", adjust="qfq")
        if df is None or df.empty:
            return []
        out = []
        for _, row in df.iterrows():
            try:
                out.append({
                    "date": str(row["日期"]),
                    "open": _fnum(row["开盘"]),
                    "close": _fnum(row["收盘"]),
                    "high": _fnum(row["最高"]),
                    "low": _fnum(row["最低"]),
                    "volume": _fnum(row.get("成交量", 0)),
                    "amount": _fnum(row.get("成交额", 0)),
                })
            except (KeyError, ValueError, TypeError):
                continue
        return out[-count:] if len(out) > count else out
    except Exception as exc:
        logger.warning("eastmoney kline fallback failed for %s: %s", code, exc)
        return []


# ---------------------------------------------------------------------------
# 增量存档
# ---------------------------------------------------------------------------

def _local_today_iso() -> str:
    if LOCAL_TZ is not None:
        return datetime.now(LOCAL_TZ).date().isoformat()
    return dt_date.today().isoformat()


def upsert_klines(conn, code: str, rows: List[dict]) -> int:
    """增量写入；冲突按 date 覆盖。返回 upsert 的行数。"""
    ensure_kline_cache_table(conn)
    code = str(code or "").strip()
    if not code or not rows:
        return 0
    now = datetime.now(LOCAL_TZ).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
    cnt = 0
    for r in rows:
        d = str(r.get("date") or "").strip()[:10]
        if not d:
            continue
        conn.execute(
            f"""INSERT INTO {KLINE_TABLE} (code, date, open, high, low, close, volume, amount, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, date) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume, amount=excluded.amount,
                    updated_at=excluded.updated_at""",
            (code, d, _fnum(r.get("open")), _fnum(r.get("high")),
             _fnum(r.get("low")), _fnum(r.get("close")),
             _fnum(r.get("volume")), _fnum(r.get("amount")), now),
        )
        cnt += 1
    return cnt


def _fetch_kline_rows(code: str) -> List[dict]:
    """纯网络阶段：先腾讯，空则退化东财。不碰 DB，可在任何事务之外调用。"""
    rows = fetch_tencent_kline_ohlc(code, count=KLINE_DEFAULT_DAYS)
    if not rows:
        rows = fetch_eastmoney_kline_ohlc(code, count=KLINE_DEFAULT_DAYS)
    return rows or []


def _row_get(row, key: str, index: int):
    """兼容 sqlite3.Row 与普通 tuple 取值。"""
    if isinstance(row, sqlite3.Row):
        return row[key]
    return row[index]


def _synced_today_codes(conn) -> set:
    """一次查询取出「今天已同步过」的 code 集合，替代循环内逐只 SELECT。"""
    today = _local_today_iso()
    out = set()
    for row in conn.execute(
        f"SELECT code, MAX(updated_at) as last FROM {KLINE_TABLE} GROUP BY code"
    ).fetchall():
        last = _row_get(row, "last", 1)
        if last and str(last)[:10] == today:
            out.add(str(_row_get(row, "code", 0) or "").strip())
    return out


def sync_kline_for_code(conn, code: str, *, force: bool = False) -> int:
    """拉单只标的日K并入库。返回新写入的行数。

    网络拉取必须在任何 DB 事务之外：增量检查（SELECT）后立刻 commit 结束读事务，
    否则 WAL 下长时间持读快照、随后写升级会直接 SQLITE_BUSY_SNAPSHOT；
    旧实现更是把每只标的的网络 IO 都放在上一只已开的写事务里。
    """
    code = str(code or "").strip()
    if not code:
        return 0
    # f 前缀 = 场外开放式基金，没有股票式 K 线；当股票拉会把 f 剥掉串台。
    if code.lower().startswith("f"):
        return 0
    ensure_kline_cache_table(conn)
    # 增量检查：如果今天已同步过则跳过（除非 force）
    if not force:
        row = conn.execute(
            f"SELECT MAX(updated_at) as last FROM {KLINE_TABLE} WHERE code = ?", (code,)
        ).fetchone()
        last = _row_get(row, "last", 0) if row else None
        today = _local_today_iso()
        if last and str(last)[:10] == today:
            return 0
    conn.commit()  # 结束读事务：下面的网络拉取不持有任何 DB 事务/锁
    rows = _fetch_kline_rows(code)
    if not rows:
        return 0
    return upsert_klines(conn, code, rows)


def sync_klines_for_holdings(conn, *, force: bool = False) -> dict:
    """批量给所有持仓同步日K。

    两阶段：先把所有标的的网络数据拉进内存（期间不持有任何 DB 事务/锁），
    再用一个短事务批量 upsert。cron 每天 15:20/16:40 会触发，旧实现会让整个
    批量抓取期间写锁一直被占，导致并发写请求 5 秒后 database is locked。
    """
    ensure_kline_cache_table(conn)
    rows = conn.execute("SELECT code FROM holdings WHERE quantity > 0").fetchall()
    codes = [str(r["code"]).strip() for r in rows]
    # 增量集合（force 时不用）先在阶段 1 查完，然后结束读事务
    synced_today = set() if force else _synced_today_codes(conn)
    conn.commit()  # 阶段 1 结束：网络阶段不再持有 DB 事务/锁

    # 阶段 2：纯网络拉取，结果只进内存
    pending = []
    skipped = 0
    failed = []
    for code in codes:
        try:
            if not code or code.lower().startswith("f") or code in synced_today:
                skipped += 1
                continue
            fetched = _fetch_kline_rows(code)
            if not fetched:
                skipped += 1
                continue
            pending.append((code, fetched))
        except Exception as exc:
            logger.warning("kline sync failed for %s: %s", code, exc)
            failed.append({"code": code, "reason": str(exc)})

    # 阶段 3：短写事务批量落库（调用方负责 commit）
    synced = 0
    for code, fetched in pending:
        try:
            upsert_klines(conn, code, fetched)
            synced += 1
        except Exception as exc:
            logger.warning("kline sync failed for %s: %s", code, exc)
            failed.append({"code": code, "reason": str(exc)})
    return {"synced": synced, "skipped": skipped, "failed": failed}


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------

def get_cached_klines(code: str, days: int = 120) -> List[dict]:
    """从 kline_cache 读近 N 天日K。"""
    code = str(code or "").strip()
    if not code:
        return []
    with db_session(row_factory=sqlite3.Row) as conn:
        ensure_kline_cache_table(conn)
        rows = conn.execute(
            f"""SELECT date, open, high, low, close, volume, amount
                FROM {KLINE_TABLE}
                WHERE code = ?
                ORDER BY date DESC
                LIMIT ?""",
            (code, int(days)),
        ).fetchall()
    out = [dict(r) for r in rows]
    out.reverse()  # 升序给前端
    return out


def get_cached_klines_range(code: str, start_date: str, end_date: str) -> List[dict]:
    code = str(code or "").strip()
    if not code:
        return []
    with db_session(row_factory=sqlite3.Row) as conn:
        ensure_kline_cache_table(conn)
        rows = conn.execute(
            f"""SELECT date, open, high, low, close, volume, amount
                FROM {KLINE_TABLE}
                WHERE code = ? AND date BETWEEN ? AND ?
                ORDER BY date ASC""",
            (code, str(start_date)[:10], str(end_date)[:10]),
        ).fetchall()
    return [dict(r) for r in rows]
