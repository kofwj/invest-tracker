import logging
import sqlite3
from datetime import date as dt_date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from .database import LOCAL_TZ
except ImportError:
    from database import LOCAL_TZ


def ensure_snapshot_columns(conn):
    cols = [row[1] for row in conn.execute("PRAGMA table_info(daily_snapshots)").fetchall()]
    if "pending_purchase" not in cols:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN pending_purchase REAL DEFAULT 0")
    if "lifetime_profit" not in cols:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN lifetime_profit REAL DEFAULT 0")
    if "equity_mv" not in cols:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN equity_mv REAL DEFAULT 0")
    if "bond_mv" not in cols:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN bond_mv REAL DEFAULT 0")
    if "reit_mv" not in cols:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN reit_mv REAL DEFAULT 0")
    if "unpriced_count" not in cols:
        # 该日快照里 last_price 缺失（按 0 计市值）的持仓只数
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN unpriced_count INTEGER DEFAULT 0")
    if "price_date" not in cols:
        # 该快照所依据的价格日期（本地 YYYY-MM-DD），未知为 NULL
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN price_date TEXT")
    if "price_stale" not in cols:
        # 1 表示记录时最新价不是当天的（低置信快照）
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN price_stale INTEGER DEFAULT 0")


def ensure_portfolio_cash_flows_table(conn):
    # created_at is written explicitly by the app (app-local time); the
    # DEFAULT only remains as a safety net and must not depend on the
    # container OS timezone (old default datetime('now','localtime') drifted
    # 8h from APP_TIMEZONE on UTC containers).
    conn.execute("""CREATE TABLE IF NOT EXISTS portfolio_cash_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        flow_type TEXT NOT NULL,
        amount REAL NOT NULL,
        source TEXT,
        remark TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    # 绩效/勾稽按日期顺序读全表：无索引时是全表扫 + 临时 B 树排序
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_portfolio_cash_flows_date_id ON portfolio_cash_flows(date, id)"
    )


def ensure_reconcile_table(conn):
    """人工对账表：手录实盘总资产，与计算快照对比误差。"""
    conn.execute("""CREATE TABLE IF NOT EXISTS snapshot_reconcile (
        date TEXT PRIMARY KEY,
        manual_total_assets REAL NOT NULL,
        note TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")


def save_reconcile(conn, date_iso, manual_total_assets, note=""):
    ensure_reconcile_table(conn)
    conn.execute(
        """INSERT INTO snapshot_reconcile (date, manual_total_assets, note)
           VALUES (?, ?, ?)
           ON CONFLICT(date) DO UPDATE SET
               manual_total_assets = excluded.manual_total_assets,
               note = excluded.note,
               created_at = CURRENT_TIMESTAMP""",
        (date_iso, float(manual_total_assets), str(note or "")),
    )
    return {"status": "success", "date": date_iso}


def latest_reconcile_with_gap(conn):
    """最近一次人工对账：与当日计算快照对比误差。"""
    ensure_reconcile_table(conn)
    row = conn.execute(
        "SELECT * FROM snapshot_reconcile ORDER BY date DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    rec = dict(row)
    rec["manual_total_assets"] = float(rec.get("manual_total_assets") or 0)
    snap = conn.execute(
        "SELECT total_assets FROM daily_snapshots WHERE date = ?",
        (rec["date"],),
    ).fetchone()
    calc = float(snap["total_assets"]) if (snap and snap["total_assets"] is not None) else None
    rec["calculated_total_assets"] = calc
    if calc is not None:
        rec["gap"] = round(rec["manual_total_assets"] - calc, 2)
        rec["gap_pct"] = round(rec["gap"] / calc * 100, 2) if calc != 0 else None
    else:
        rec["gap"] = None
        rec["gap_pct"] = None
    return rec


def _count_unpriced_holdings(conn):
    """兜底：调用方没给缺价标记时，直接按持仓表现算一次（老调用方兼容）。"""
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM holdings "
            "WHERE quantity > 0 AND (last_price IS NULL OR last_price <= 0)"
        ).fetchone()
    except Exception:
        return 0
    try:
        if isinstance(row, sqlite3.Row):
            return int(row["cnt"] or 0)
        return int((row[0] if row else 0) or 0)
    except (TypeError, ValueError, IndexError):
        return 0


def resolve_unpriced_count(conn, dashboard):
    """本次快照里缺价（市值按 0 计）的持仓只数。只记录，不阻断快照。"""
    if not isinstance(dashboard, dict):
        return _count_unpriced_holdings(conn)
    raw = dashboard.get("unpriced_count")
    if raw is None and "unpriced_codes" in dashboard:
        raw = len(dashboard.get("unpriced_codes") or [])
    if raw is None:
        return _count_unpriced_holdings(conn)
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


# settings 里记录「最近一次成功同步价」的时间键。
# 不能只用 holdings.updated_at 判据：用户录一笔交易会触发 recalc_holdings
# 刷新它，价格就"看起来是新的"。
LAST_PRICE_SYNC_KEY = "last_price_sync_at"
LAST_PRICE_SYNC_FAILED_KEY = "last_price_sync_failed"


def _local_today_iso():
    """本地"今天"；动态读 database 模块属性，测试 monkeypatch 才生效。"""
    try:
        from .database import local_today_iso
    except ImportError:
        from database import local_today_iso
    return local_today_iso()


def _normalize_timestamp(value):
    """把库里各种时间写法规整成 'YYYY-MM-DD HH:MM:SS'；解析不了返回 None。"""
    text = str(value or "").strip().replace("T", " ")
    if not text:
        return None
    text = text[:19]
    if len(text) == 10:
        text += " 00:00:00"
    try:
        datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return text


def count_holdings_needing_price(conn):
    """需要行情价的持仓只数（只有 quantity > 0 才需要定价）。"""
    try:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM holdings WHERE quantity > 0").fetchone()
        if isinstance(row, sqlite3.Row):
            return int(row["cnt"] or 0)
        return int((row[0] if row else 0) or 0)
    except (TypeError, ValueError, IndexError):
        return 0


def latest_price_sync_at(conn):
    """最近一次成功同步价的时间（本地 naive 串），未知返回 None。

    优先 settings.last_price_sync_at（价格同步专用，不会被录交易刷新）；
    老库没有该键时回落到 MAX(holdings.updated_at) WHERE quantity > 0。
    """
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (LAST_PRICE_SYNC_KEY,)
        ).fetchone()
    except Exception:
        row = None
    if row is not None:
        value = row["value"] if isinstance(row, sqlite3.Row) else row[0]
        ts = _normalize_timestamp(value)
        if ts:
            return ts
    try:
        row2 = conn.execute(
            "SELECT MAX(updated_at) AS latest FROM holdings "
            "WHERE quantity > 0 AND updated_at IS NOT NULL"
        ).fetchone()
    except Exception:
        return None
    if row2 is None:
        return None
    latest = row2["latest"] if isinstance(row2, sqlite3.Row) else row2[0]
    return _normalize_timestamp(latest)


def last_price_sync_failed_codes(conn):
    """最近一次价格同步里取不到价的代码列表（逗号分隔存 settings），没有则空。"""
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (LAST_PRICE_SYNC_FAILED_KEY,)
        ).fetchone()
    except Exception:
        return []
    if row is None:
        return []
    value = row["value"] if isinstance(row, sqlite3.Row) else row[0]
    return [c.strip() for c in str(value or "").split(",") if c.strip()]


def resolve_snapshot_price_state(conn, today_iso=None):
    """/snapshots 与 /cron/snapshot 共用的价格新鲜度判据。

    - needs_fresh_price：存在 quantity > 0 的持仓才需要行情价；没有任何需定价
      持仓（例如只存银行存款）时一律放行，否则这类用户永远记不了快照。
    - price_date：最近一次成功同步价的本地日期；从未同步过为 None。
    - is_stale：price_date != 今天（从未同步过也算 stale）；无需定价时恒为 False。
    """
    sync_at = latest_price_sync_at(conn)
    price_date = sync_at[:10] if sync_at else None
    needs = count_holdings_needing_price(conn) > 0
    today = str(today_iso or _local_today_iso() or "")[:10]
    return {
        "needs_fresh_price": needs,
        "price_date": price_date,
        "is_stale": bool(needs and price_date != today),
        "last_price_sync_at": sync_at,
        "failed_codes": last_price_sync_failed_codes(conn),
    }


def stale_price_detail(price_state, today_iso=None):
    """价格不新鲜时的中文提示（含基准日期），给人看。"""
    if not isinstance(price_state, dict):
        price_state = {}
    price_date = price_state.get("price_date")
    if price_date:
        head = f"最新价还是 {price_date} 的"
    elif today_iso:
        head = f"最新价还没有成功同步过（{today_iso} 取不到当日价）"
    else:
        head = "最新价还没有成功同步过（基准日期未知）"
    failed = price_state.get("failed_codes") or []
    tail = ""
    if failed:
        shown = "、".join(failed[:5])
        more = f" 等 {len(failed)} 只" if len(failed) > 5 else ""
        tail = f"最近一次同步有 {len(failed)} 只取不到价（{shown}{more}）。"
    return f"{head}，现在记录会让这天的收益失真（快照值会沿用旧价）。{tail}先点「同步价」，或用 force=true 强制记录"


def create_snapshot_record(conn, today_iso, dashboard):
    ensure_snapshot_columns(conn)
    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    lifetime = dashboard.get("lifetime_profit", 0)
    unpriced_count = resolve_unpriced_count(conn, dashboard)
    # 价格新鲜度用共享判据（不要从 dashboard 的 price_stale/updated_at 猜）：
    # force 记录时这里自然落成 price_stale=1 + 旧价日期。
    price_state = resolve_snapshot_price_state(conn, today_iso)
    price_date = price_state["price_date"]
    price_stale = 1 if price_state["is_stale"] else 0
    existing = conn.execute("SELECT id FROM daily_snapshots WHERE date = ?", (today_iso,)).fetchone()
    if existing:
        conn.execute("""
            UPDATE daily_snapshots
            SET total_assets = ?, total_market_value = ?, bank_balance = ?, securities_cash = ?,
                pending_purchase = ?, total_profit = ?, lifetime_profit = ?, holdings_count = ?,
                equity_mv = ?, bond_mv = ?, reit_mv = ?, created_at = ?, unpriced_count = ?,
                price_date = ?, price_stale = ?
            WHERE date = ?
        """, (
            dashboard['total_assets'],
            dashboard['total_market_value'],
            dashboard['bank_balance'],
            dashboard['securities_cash'],
            dashboard.get('pending_purchase', 0),
            dashboard['total_profit'],
            lifetime,
            dashboard['holdings_count'],
            (dashboard.get("category_market_value") or {}).get("权益", 0),
            (dashboard.get("category_market_value") or {}).get("债基", 0),
            (dashboard.get("category_market_value") or {}).get("REITs", 0),
            now,
            unpriced_count,
            price_date,
            price_stale,
            today_iso,
        ))
        return existing['id'], 'updated'

    conn.execute("""
        INSERT INTO daily_snapshots
        (date, total_assets, total_market_value, bank_balance, securities_cash, pending_purchase,
         total_profit, lifetime_profit, holdings_count, equity_mv, bond_mv, reit_mv, created_at,
         unpriced_count, price_date, price_stale)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        today_iso,
        dashboard['total_assets'],
        dashboard['total_market_value'],
        dashboard['bank_balance'],
        dashboard['securities_cash'],
        dashboard.get('pending_purchase', 0),
        dashboard['total_profit'],
        lifetime,
        dashboard['holdings_count'],
        (dashboard.get("category_market_value") or {}).get("权益", 0),
        (dashboard.get("category_market_value") or {}).get("债基", 0),
        (dashboard.get("category_market_value") or {}).get("REITs", 0),
        now,
        unpriced_count,
        price_date,
        price_stale,
    ))
    snapshot_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return snapshot_id, 'created'


def list_snapshots_rows(conn, start_date: Optional[str] = None, end_date: Optional[str] = None):
    ensure_snapshot_columns(conn)
    query = "SELECT * FROM daily_snapshots"
    params = []
    if start_date and end_date:
        query += " WHERE date BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE date >= ?"
        params = [start_date]
    elif end_date:
        query += " WHERE date <= ?"
        params = [end_date]
    query += " ORDER BY date DESC"
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def snapshots_summary_data(conn, start_date: Optional[str] = None, end_date: Optional[str] = None):
    ensure_snapshot_columns(conn)
    query = "SELECT * FROM daily_snapshots"
    params = []
    if start_date and end_date:
        query += " WHERE date BETWEEN ? AND ?"
        params = [start_date, end_date]
    elif start_date:
        query += " WHERE date >= ?"
        params = [start_date]
    elif end_date:
        query += " WHERE date <= ?"
        params = [end_date]
    query += " ORDER BY date ASC"
    rows = conn.execute(query, params).fetchall()
    if len(rows) < 2:
        return {"message": "需要至少两个快照来计算变化", "count": len(rows)}

    first = dict(rows[0])
    last = dict(rows[-1])
    anomaly = None
    prev = dict(rows[-2])
    try:
        prev_assets = float(prev.get("total_assets") or 0)
        last_assets = float(last.get("total_assets") or 0)
        if prev_assets > 0:
            day_chg_pct = (last_assets / prev_assets - 1.0) * 100.0
            day_chg_amt = last_assets - prev_assets
            # 异常：单日总资产变动 ≥2% 且金额 ≥1万
            if abs(day_chg_pct) >= 2.0 and abs(day_chg_amt) >= 10000:
                direction = "涨" if day_chg_amt > 0 else "跌"
                anomaly = {
                    "from_date": prev.get("date"),
                    "to_date": last.get("date"),
                    "change_amount": round(day_chg_amt, 2),
                    "change_pct": round(day_chg_pct, 2),
                    "text": (
                        f"盘后留意：总资产从 {prev.get('date')} 到 {last.get('date')} "
                        f"大约{direction}了 {abs(day_chg_amt):.0f} 元（{day_chg_pct:+.2f}%）。"
                        f"可能是行情、入金/出金或记账变动，建议对照资金流水。"
                    ),
                }
    except Exception as exc:
        logger.warning("snapshots_summary_data: day_over_day_anomaly failed: %s", exc)
        anomaly = None

    return {
        "period": f"{first['date']} 至 {last['date']}",
        "days": (dt_date.fromisoformat(last['date']) - dt_date.fromisoformat(first['date'])).days,
        "total_assets": {
            "start": first['total_assets'],
            "end": last['total_assets'],
            "change": last['total_assets'] - first['total_assets'],
            "change_pct": (last['total_assets'] / first['total_assets'] - 1) * 100 if first['total_assets'] else 0,
        },
        "total_market_value": {
            "start": first['total_market_value'],
            "end": last['total_market_value'],
            "change": last['total_market_value'] - first['total_market_value'],
        },
        "bank_balance": {
            "start": first['bank_balance'],
            "end": last['bank_balance'],
            "change": last['bank_balance'] - first['bank_balance'],
        },
        "securities_cash": {
            "start": first['securities_cash'],
            "end": last['securities_cash'],
            "change": last['securities_cash'] - first['securities_cash'],
        },
        "pending_purchase": {
            "start": first.get('pending_purchase', 0),
            "end": last.get('pending_purchase', 0),
            "change": (last.get('pending_purchase', 0) or 0) - (first.get('pending_purchase', 0) or 0),
        },
        "lifetime_profit": {
            "start": first.get('lifetime_profit', 0) or 0,
            "end": last.get('lifetime_profit', 0) or 0,
            "change": (last.get('lifetime_profit', 0) or 0) - (first.get('lifetime_profit', 0) or 0),
        },
        "day_over_day_anomaly": anomaly,
    }
