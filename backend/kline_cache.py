"""日K缓存：从腾讯/东方财富拉前复权日K，增量存入 kline_cache 表。

数据源复用 return_sync.fetch_tencent_kline_closes 的接口，但保留完整 OHLC（开高低收量额）。
"""
from __future__ import annotations

import json as pyjson
import logging
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
                "open": float(r[1]),
                "close": float(r[2]),
                "high": float(r[3]),
                "low": float(r[4]),
                "volume": float(r[5]) if len(r) > 5 and r[5] else 0.0,
                "amount": float(r[6]) if len(r) > 6 and r[6] else 0.0,
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
                    "open": float(row["开盘"]),
                    "close": float(row["收盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "volume": float(row.get("成交量", 0) or 0),
                    "amount": float(row.get("成交额", 0) or 0),
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
            (code, d, float(r.get("open") or 0), float(r.get("high") or 0),
             float(r.get("low") or 0), float(r.get("close") or 0),
             float(r.get("volume") or 0), float(r.get("amount") or 0), now),
        )
        cnt += 1
    return cnt


def sync_kline_for_code(conn, code: str, *, force: bool = False) -> int:
    """拉单只标的日K并入库。返回新写入的行数。"""
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
        last = row["last"] if isinstance(row, sqlite3.Row) else (row[0] if row else None)
        today = _local_today_iso()
        if last and str(last)[:10] == today:
            return 0
    # 拉数据
    rows = fetch_tencent_kline_ohlc(code, count=KLINE_DEFAULT_DAYS)
    if not rows:
        rows = fetch_eastmoney_kline_ohlc(code, count=KLINE_DEFAULT_DAYS)
    if not rows:
        return 0
    return upsert_klines(conn, code, rows)


def sync_klines_for_holdings(conn, *, force: bool = False) -> dict:
    """批量给所有持仓同步日K。"""
    ensure_kline_cache_table(conn)
    rows = conn.execute("SELECT code FROM holdings WHERE quantity > 0").fetchall()
    synced = 0
    skipped = 0
    failed = []
    for r in rows:
        code = str(r["code"]).strip()
        try:
            n = sync_kline_for_code(conn, code, force=force)
            if n > 0:
                synced += 1
            else:
                skipped += 1
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
