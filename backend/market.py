"""Market summary + simple price alerts (read-only observer over the ledger).

Does not mutate holdings/transactions. Index/holding quotes come from Eastmoney.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    from .database import LOCAL_TZ
    from .portfolio_totals import compute_portfolio_totals
    from .price_sync import fetch_eastmoney_quotes
except ImportError:
    from database import LOCAL_TZ
    from portfolio_totals import compute_portfolio_totals
    from price_sync import fetch_eastmoney_quotes

logger = logging.getLogger(__name__)

# Configurable watchlist of major A-share indices (explicit Eastmoney secid).
DEFAULT_INDICES = [
    {"code": "000001", "name": "上证指数", "secid": "1.000001"},
    {"code": "399001", "name": "深证成指", "secid": "0.399001"},
    {"code": "000300", "name": "沪深300", "secid": "1.000300"},
    {"code": "399006", "name": "创业板指", "secid": "0.399006"},
    {"code": "000510", "name": "中证A500", "secid": "1.000510"},
]

ALLOWED_TARGET_TYPES = {"holding", "index", "portfolio"}
ALLOWED_CONDITIONS = {"above", "below"}
# price：绝对价格；change_pct：单标的日内涨跌幅（相对昨收）%; portfolio_pnl：组合当日盈亏 %
# 后两者的 threshold 是**带符号**的（above=涨到 +2，below=跌到 −2）。
ALLOWED_RULE_TYPES = {"price", "change_pct", "portfolio_pnl"}
PORTFOLIO_RULE_CODE = "PORTFOLIO"
DEFAULT_COOLDOWN_MINUTES = 240
WATCHLIST_SETTING_KEY = "market_watchlist"
COOLDOWN_SETTING_KEY = "alert_cooldown_minutes"
# 每日推送上限：盘中 3 分钟一轮、规则又是"多个标的各一条"，没有上限会炸屏。
# 只约束定时推送，手动「立即检查」不受限。
DAILY_CAP_SETTING_KEY = "alert_daily_cap"
DEFAULT_DAILY_CAP = 10


def ensure_alert_tables(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            condition TEXT NOT NULL,
            threshold REAL NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            rule_type TEXT DEFAULT 'price'
        )"""
    )
    # 老库没有 rule_type：在请求路径上幂等补列，与 schema v17 迁移同义。
    rule_cols = [row[1] for row in conn.execute("PRAGMA table_info(alert_rules)").fetchall()]
    if "rule_type" not in rule_cols:
        conn.execute("ALTER TABLE alert_rules ADD COLUMN rule_type TEXT DEFAULT 'price'")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS alert_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            trigger_time DATETIME,
            target_code TEXT,
            triggered_price REAL,
            threshold REAL,
            message TEXT,
            rule_type TEXT,
            value REAL
        )"""
    )
    # 老库补列（与 schema v17 迁移同义）。rule_type/value 让预警历史能区分
    # "某标的价 12.5" 与"组合当日盈亏 -1.5%"—— 光看 triggered_price 是分不出的。
    event_cols = [row[1] for row in conn.execute("PRAGMA table_info(alert_events)").fetchall()]
    for col, decl in (("rule_type", "TEXT"), ("value", "REAL")):
        if col not in event_cols:
            conn.execute(f"ALTER TABLE alert_events ADD COLUMN {col} {decl}")
    # 冷却判断按 (rule_id, id DESC) 取最新一条；事件表随每日检查增长，无索引即全表扫。
    # 老库/测试里的 legacy alert_events 可能没有 rule_id 列，缺列时跳过（不在请求路径上尝试改表）。
    alert_event_cols = [row[1] for row in conn.execute("PRAGMA table_info(alert_events)").fetchall()]
    if "rule_id" in alert_event_cols:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alert_events_rule_id_id ON alert_events(rule_id, id DESC)"
        )


def _row_to_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(row)


def _get_setting(conn, key: str, default: str = "") -> str:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    except Exception:
        return default
    if not row:
        return default
    val = row["value"] if isinstance(row, sqlite3.Row) else row[0]
    return "" if val is None else str(val)


def _set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def get_alert_cooldown_minutes(conn) -> int:
    raw = os.environ.get("ALERT_COOLDOWN_MINUTES") or _get_setting(
        conn, COOLDOWN_SETTING_KEY, str(DEFAULT_COOLDOWN_MINUTES)
    )
    try:
        return max(0, int(float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_COOLDOWN_MINUTES



def get_alert_daily_cap(conn) -> int:
    """每日推送条数上限（0 = 不限）。只约束**定时推送**，手动检查不受限。"""
    raw = os.environ.get("ALERT_DAILY_CAP") or _get_setting(
        conn, DAILY_CAP_SETTING_KEY, str(DEFAULT_DAILY_CAP)
    )
    try:
        return max(0, int(float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_DAILY_CAP


def _alert_events_today(conn, now: datetime) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM alert_events WHERE date(trigger_time) = date(?)",
        (now.date().isoformat(),),
    ).fetchone()
    if row is None:
        return 0
    return int((row["n"] if isinstance(row, sqlite3.Row) else row[0]) or 0)


def list_alert_rules(conn) -> List[Dict[str, Any]]:
    ensure_alert_tables(conn)
    rows = conn.execute(
        "SELECT * FROM alert_rules ORDER BY enabled DESC, id DESC"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_alert_events(
    conn,
    *,
    limit: int = 50,
    code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    ensure_alert_tables(conn)
    limit = max(1, min(int(limit or 50), 500))
    code = str(code or "").strip()
    start_date = str(start_date or "").strip()[:10] or None
    end_date = str(end_date or "").strip()[:10] or None
    clauses = []
    params: List[Any] = []
    if code:
        clauses.append("target_code = ?")
        params.append(code)
    if start_date:
        clauses.append("date(trigger_time) >= date(?)")
        params.append(start_date)
    if end_date:
        clauses.append("date(trigger_time) <= date(?)")
        params.append(end_date)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT * FROM alert_events
        {where}
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def clear_alert_events(
    conn,
    *,
    code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    before_id: Optional[int] = None,
    allow_all: bool = False,
) -> int:
    """Delete matching alert events. Returns deleted row count.

    Without any filter this would wipe the whole table, so a filter (or an
    explicit allow_all from the route's clear-all branch) is required.
    """
    ensure_alert_tables(conn)
    code = str(code or "").strip()
    start_date = str(start_date or "").strip()[:10] or None
    end_date = str(end_date or "").strip()[:10] or None
    clauses = []
    params: List[Any] = []
    if code:
        clauses.append("target_code = ?")
        params.append(code)
    if start_date:
        clauses.append("date(trigger_time) >= date(?)")
        params.append(start_date)
    if end_date:
        clauses.append("date(trigger_time) <= date(?)")
        params.append(end_date)
    if before_id is not None:
        clauses.append("id <= ?")
        params.append(int(before_id))
    if not clauses:
        if not allow_all:
            raise ValueError("clear_alert_events 需要至少一个过滤条件（code/start_date/end_date/before_id）或显式 allow_all")
        cur = conn.execute("DELETE FROM alert_events")
        return int(cur.rowcount or 0)
    where = " AND ".join(clauses)
    cur = conn.execute(f"DELETE FROM alert_events WHERE {where}", params)
    return int(cur.rowcount or 0)


def export_alert_events_csv(
    conn,
    *,
    limit: int = 500,
    code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    rows = list_alert_events(
        conn, limit=limit, code=code, start_date=start_date, end_date=end_date
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "rule_id", "trigger_time", "target_code", "triggered_price", "threshold", "message"]
    )
    for r in rows:
        writer.writerow(
            [
                r.get("id"),
                r.get("rule_id"),
                r.get("trigger_time"),
                r.get("target_code"),
                r.get("triggered_price"),
                r.get("threshold"),
                r.get("message"),
            ]
        )
    return buf.getvalue()


def _normalize_rule_fields(
    *,
    target_type: str,
    code: str,
    condition: str,
    threshold: Any,
    rule_type: str = "price",
    name: str = "",
) -> Dict[str, Any]:
    """校验并归一化一条规则；create 与 update 共用，避免两处语义漂移。"""
    target_type = str(target_type or "").strip().lower()
    rule_type = str(rule_type or "price").strip().lower() or "price"
    code = str(code or "").strip()
    condition = str(condition or "").strip().lower()
    name = str(name or "").strip()

    if rule_type not in ALLOWED_RULE_TYPES:
        raise ValueError("rule_type 必须是 price、change_pct 或 portfolio_pnl")
    if target_type not in ALLOWED_TARGET_TYPES:
        raise ValueError("target_type 必须是 holding、index 或 portfolio")
    if condition not in ALLOWED_CONDITIONS:
        raise ValueError("condition 必须是 above 或 below")

    # 组合层规则没有具体标的，统一用 PORTFOLIO 哨兵，避免 code 为空。
    #
    # 这里只接受明确声明过的组合规则：如果调用方说 target_type=portfolio 却带着
    # rule_type=price（典型来源是"PUT {"target_type":"portfolio"}" 打到一条老价格规则上，
    # rule_type 从库里读回来还是 price），静默翻成 portfolio_pnl 会留下一条
    # threshold 仍是价格（如 12.0）的组合规则 —— 返回 200，但永远不会触发。
    # 宁可 400 让调用方讲清楚。
    if target_type == "portfolio" and rule_type != "portfolio_pnl":
        raise ValueError("target_type=portfolio 时 rule_type 必须是 portfolio_pnl")
    if rule_type == "portfolio_pnl":
        target_type = "portfolio"
        code = PORTFOLIO_RULE_CODE
        name = name or "组合当日盈亏"
    elif not code:
        raise ValueError("code 不能为空")

    try:
        threshold = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("threshold 必须是数字") from exc

    # 价格阈值不允许为负；涨跌幅/组合盈亏是带符号的（below −2 即"跌到 −2%"）。
    if rule_type == "price" and threshold < 0:
        raise ValueError("价格阈值不能为负")

    return {
        "target_type": target_type,
        "rule_type": rule_type,
        "code": code,
        "name": name or code,
        "condition": condition,
        "threshold": threshold,
    }


def create_alert_rule(
    conn,
    *,
    target_type: str,
    code: str,
    condition: str,
    threshold: float,
    name: str = "",
    enabled: bool = True,
    rule_type: str = "price",
) -> Dict[str, Any]:
    ensure_alert_tables(conn)
    fields = _normalize_rule_fields(
        target_type=target_type,
        code=code,
        condition=condition,
        threshold=threshold,
        rule_type=rule_type,
        name=name,
    )

    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    cur = conn.execute(
        """
        INSERT INTO alert_rules
            (target_type, code, name, condition, threshold, enabled,
             created_at, updated_at, rule_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fields["target_type"],
            fields["code"],
            fields["name"],
            fields["condition"],
            fields["threshold"],
            1 if enabled else 0,
            now,
            now,
            fields["rule_type"],
        ),
    )
    rule_id = int(cur.lastrowid)
    row = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
    return _row_to_dict(row)


def update_alert_rule(conn, rule_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_alert_tables(conn)
    existing = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
    if not existing:
        raise KeyError("规则不存在")
    ex = _row_to_dict(existing)

    fields = _normalize_rule_fields(
        target_type=payload.get("target_type", ex["target_type"]),
        code=payload.get("code", ex["code"]),
        condition=payload.get("condition", ex["condition"]),
        threshold=payload.get("threshold", ex["threshold"]),
        rule_type=payload.get("rule_type", ex.get("rule_type") or "price"),
        name=payload.get("name", ex.get("name") or ""),
    )
    if "enabled" in payload:
        enabled = 1 if payload["enabled"] else 0
    else:
        enabled = int(ex.get("enabled") or 0)

    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    conn.execute(
        """
        UPDATE alert_rules
        SET target_type = ?, code = ?, name = ?, condition = ?, threshold = ?,
            enabled = ?, updated_at = ?, rule_type = ?
        WHERE id = ?
        """,
        (
            fields["target_type"],
            fields["code"],
            fields["name"],
            fields["condition"],
            fields["threshold"],
            enabled,
            now,
            fields["rule_type"],
            rule_id,
        ),
    )
    row = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
    return _row_to_dict(row)


def delete_alert_rule(conn, rule_id: int) -> bool:
    ensure_alert_tables(conn)
    cur = conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    return cur.rowcount > 0


def _index_secid_map() -> Dict[str, str]:
    return {item["code"]: item["secid"] for item in DEFAULT_INDICES}


def get_watchlist(conn) -> List[Dict[str, str]]:
    raw = _get_setting(conn, WATCHLIST_SETTING_KEY, "[]")
    try:
        data = json.loads(raw or "[]")
    except Exception:
        data = []
    out = []
    if not isinstance(data, list):
        return out
    for item in data:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        out.append(
            {
                "code": code,
                "name": str(item.get("name") or code).strip() or code,
                "secid": str(item.get("secid") or "").strip(),
            }
        )
    return out[:30]


def set_watchlist(conn, items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    cleaned = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        cleaned.append(
            {
                "code": code,
                "name": str(item.get("name") or code).strip() or code,
                "secid": str(item.get("secid") or "").strip(),
            }
        )
        if len(cleaned) >= 30:
            break
    _set_setting(conn, WATCHLIST_SETTING_KEY, json.dumps(cleaned, ensure_ascii=False))
    return cleaned


def fetch_index_quotes(indices: Optional[List[Dict[str, str]]] = None) -> Dict[str, Dict[str, Any]]:
    items = indices if indices is not None else DEFAULT_INDICES
    codes = [i["code"] for i in items]
    secid_map = {i["code"]: i.get("secid") for i in items if i.get("secid")}
    quotes = fetch_eastmoney_quotes(codes, secid_map=secid_map or None)
    name_map = {i["code"]: i["name"] for i in items}
    for code, q in quotes.items():
        if not q.get("name"):
            q["name"] = name_map.get(code, code)
    return quotes


def _holding_price_map(conn) -> Dict[str, Dict[str, Any]]:
    """Prefer live Eastmoney quote; fall back to holdings.last_price."""
    rows = conn.execute(
        "SELECT code, name, quantity, last_price, avg_cost, diluted_cost, total_dividend "
        "FROM holdings WHERE quantity > 0"
    ).fetchall()
    holdings = [_row_to_dict(r) for r in rows]
    codes = [str(h["code"]).strip() for h in holdings if h.get("code")]
    live = {}
    if codes:
        try:
            live = fetch_eastmoney_quotes(codes)
        except Exception:
            logger.warning("批量拉取持仓行情失败", exc_info=True)
            live = {}
    out = {}
    for h in holdings:
        code = str(h.get("code") or "").strip()
        if not code:
            continue
        q = live.get(code) or {}
        price = q.get("price")
        if price is None or price <= 0:
            price = float(h.get("last_price") or 0)
        change_pct = q.get("change_pct")
        prev_close = q.get("prev_close")
        if change_pct is None and prev_close and price and float(prev_close) > 0:
            change_pct = (float(price) / float(prev_close) - 1.0) * 100.0
        out[code] = {
            "code": code,
            "name": q.get("name") or h.get("name") or code,
            "price": float(price or 0),
            "change_pct": change_pct,
            "prev_close": prev_close,
            "quantity": float(h.get("quantity") or 0),
            "avg_cost": float(h.get("avg_cost") or 0),
            "last_price_db": float(h.get("last_price") or 0),
            "total_dividend": float(h.get("total_dividend") or 0),
            "source": "live" if q.get("price") not in (None, 0) else "db",
        }
    return out


def _portfolio_day_pnl(holding_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """组合当日盈亏：Σ(现价 − 昨收) × 数量，以及相对昨收市值的百分比。

    与"持仓浮盈"（对**成本**）严格区分 —— 这个只衡量**今天**的变动，是盘中
    波动提醒的基准。缺昨收的持仓直接跳过（取不到就不猜，宁可少算也不错算）。
    """
    pnl = 0.0
    base = 0.0
    for h in holding_map.values():
        prev = h.get("prev_close")
        price = h.get("price")
        qty = float(h.get("quantity") or 0)
        if not prev or float(prev) <= 0 or not price or qty <= 0:
            continue
        base += float(prev) * qty
        pnl += (float(price) - float(prev)) * qty
    return {
        "amount": pnl,
        "base": base,
        "change_pct": (pnl / base * 100.0) if base > 0 else None,
    }


def _build_today_highlights(
    indices: List[Dict[str, Any]],
    contrib_rows: List[Dict[str, Any]],
    portfolio_chg: Optional[float],
    hs300_chg: Optional[float],
    watch_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """人话结论，不甩技术指标名。"""
    lines: List[str] = []
    watch_rows = watch_rows or []

    # 机会/风险：涨跌幅较大的持仓/自选（结论向）
    movers = []
    for r in contrib_rows:
        chg = r.get("change_pct")
        if chg is None:
            continue
        movers.append(
            {
                "name": r.get("name") or r.get("code"),
                "code": r.get("code"),
                "change_pct": float(chg),
                "kind": "持仓",
            }
        )
    for r in watch_rows:
        chg = r.get("change_pct")
        if chg is None:
            continue
        movers.append(
            {
                "name": r.get("name") or r.get("code"),
                "code": r.get("code"),
                "change_pct": float(chg),
                "kind": "自选",
            }
        )
    if movers:
        strong = [m for m in movers if m["change_pct"] >= 3.0]
        weak = [m for m in movers if m["change_pct"] <= -3.0]
        strong.sort(key=lambda x: x["change_pct"], reverse=True)
        weak.sort(key=lambda x: x["change_pct"])
        if strong:
            s = strong[0]
            lines.append(
                f"机会留意：{s['kind']}「{s['name']}」今天大约涨 {s['change_pct']:+.2f}%，可关注是否跟你计划有关（不是买卖指令）。"
            )
        if weak:
            w = weak[0]
            lines.append(
                f"风险留意：{w['kind']}「{w['name']}」今天大约跌 {w['change_pct']:+.2f}%，别急着加仓；先看是不是你本来就想减的票。"
            )

    idx_with = [i for i in indices if i.get("change_pct") is not None]
    if idx_with:
        best = max(idx_with, key=lambda x: float(x["change_pct"]))
        worst = min(idx_with, key=lambda x: float(x["change_pct"]))
        lines.append(
            f"大盘：{best.get('name')} {float(best['change_pct']):+.2f}%，"
            f"{worst.get('name')} {float(worst['change_pct']):+.2f}%。"
        )
    if portfolio_chg is not None and hs300_chg is not None:
        diff = portfolio_chg - hs300_chg
        if abs(diff) < 0.15:
            lines.append(f"你的组合大约 {portfolio_chg:+.2f}%，和大盘差不多。")
        elif diff > 0:
            lines.append(
                f"你的组合大约 {portfolio_chg:+.2f}%，比沪深300（{hs300_chg:+.2f}%）强一点。"
            )
        else:
            lines.append(
                f"你的组合大约 {portfolio_chg:+.2f}%，比沪深300（{hs300_chg:+.2f}%）弱一点——防守仓常见，先别慌。"
            )
    with_contrib = [r for r in contrib_rows if r.get("day_contrib") is not None]
    if with_contrib:
        top = max(with_contrib, key=lambda r: float(r["day_contrib"]))
        bottom = min(with_contrib, key=lambda r: float(r["day_contrib"]))
        if float(top["day_contrib"]) > 0:
            lines.append(
                f"今天赚钱主要靠：{top.get('name')}（大约 {float(top['day_contrib']):+.0f} 元）。"
            )
        if float(bottom["day_contrib"]) < 0:
            lines.append(
                f"今天拖后腿：{bottom.get('name')}（大约 {float(bottom['day_contrib']):+.0f} 元）。"
            )
    if not lines:
        lines.append("行情或持仓数据不全，今天看点暂无法生成。")
    # 去重保序
    seen = set()
    out = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out[:6]


def build_market_summary(conn) -> Dict[str, Any]:
    """Index quotes + lightweight portfolio signals (no DB mutation)."""
    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    index_err = None
    try:
        index_quotes = fetch_index_quotes()
    except Exception as exc:
        index_quotes = {}
        index_err = str(exc)

    indices = []
    for item in DEFAULT_INDICES:
        code = item["code"]
        q = index_quotes.get(code) or {}
        chg = q.get("change_pct")
        prev = q.get("prev_close")
        price = q.get("price")
        if chg is None and prev and price and float(prev) > 0:
            chg = (float(price) / float(prev) - 1.0) * 100.0
        indices.append(
            {
                "code": code,
                "name": q.get("name") or item["name"],
                "price": price,
                "change_pct": None if chg is None else round(float(chg), 4),
                "prev_close": prev,
                "available": price is not None,
            }
        )

    # Custom watchlist (extra symbols, not replacing defaults)
    watchlist = get_watchlist(conn)
    watch_rows = []
    if watchlist:
        try:
            secid_map = {w["code"]: w["secid"] for w in watchlist if w.get("secid")}
            wq = fetch_eastmoney_quotes(
                [w["code"] for w in watchlist],
                secid_map=secid_map or None,
            )
        except Exception:
            logger.warning("拉取自选行情失败", exc_info=True)
            wq = {}
        for w in watchlist:
            code = w["code"]
            q = wq.get(code) or {}
            chg = q.get("change_pct")
            prev = q.get("prev_close")
            price = q.get("price")
            if chg is None and prev and price and float(prev) > 0:
                chg = (float(price) / float(prev) - 1.0) * 100.0
            watch_rows.append(
                {
                    "code": code,
                    "name": q.get("name") or w.get("name") or code,
                    "price": price,
                    "change_pct": None if chg is None else round(float(chg), 4),
                    "prev_close": prev,
                    "available": price is not None,
                }
            )

    holding_map = _holding_price_map(conn)
    contrib_rows = []
    today_contrib = 0.0
    for code, h in holding_map.items():
        chg = h.get("change_pct")
        mv = float(h["quantity"]) * float(h["price"] or 0)
        day_pnl = None
        if chg is not None and mv:
            day_pnl = mv * (float(chg) / 100.0)
            today_contrib += day_pnl
        contrib_rows.append(
            {
                "code": code,
                "name": h["name"],
                "market_value": round(mv, 2),
                "price": h["price"],
                "change_pct": None if chg is None else round(float(chg), 4),
                "prev_close": h.get("prev_close"),
                "day_contrib": None if day_pnl is None else round(day_pnl, 2),
                "source": h["source"],
            }
        )
    contrib_rows.sort(key=lambda r: abs(r.get("day_contrib") or 0), reverse=True)

    totals = compute_portfolio_totals(conn)
    hs300 = next((i for i in indices if i["code"] == "000300"), None)
    a500 = next((i for i in indices if i["code"] == "000510"), None)
    market_mv = float(totals.get("total_market_value") or 0)
    portfolio_chg = None
    if market_mv > 0 and any(r.get("day_contrib") is not None for r in contrib_rows):
        portfolio_chg = (today_contrib / market_mv) * 100.0

    hs300_chg = None if not hs300 or hs300.get("change_pct") is None else float(hs300["change_pct"])
    a500_chg = None if not a500 or a500.get("change_pct") is None else float(a500["change_pct"])

    signal_text = "持仓与指数涨跌可能背离：请以持仓逐项贡献为准，不要只看大盘。"
    if portfolio_chg is not None and hs300_chg is not None:
        p = portfolio_chg
        m = hs300_chg
        if p >= 0 and m < 0:
            signal_text = f"今日持仓约 {p:+.2f}%，沪深300 {m:+.2f}%：持仓相对大盘偏强。"
        elif p < 0 and m > 0:
            signal_text = f"今日持仓约 {p:+.2f}%，沪深300 {m:+.2f}%：大盘涨、组合偏弱（防御仓常见）。"
        elif abs(p - m) < 0.15:
            signal_text = f"今日持仓约 {p:+.2f}%，与沪深300（{m:+.2f}%）大致同步。"
        else:
            signal_text = f"今日持仓约 {p:+.2f}%，沪深300 {m:+.2f}%。"

    # Multi-index comparison block (今日 vs 沪深300 / A500)
    comparisons = []
    if portfolio_chg is not None:
        for label, chg in (("沪深300", hs300_chg), ("中证A500", a500_chg)):
            if chg is None:
                continue
            comparisons.append(
                {
                    "benchmark": label,
                    "portfolio_pct": round(portfolio_chg, 4),
                    "benchmark_pct": round(chg, 4),
                    "diff_pct": round(portfolio_chg - chg, 4),
                    "text": (
                        f"组合 {portfolio_chg:+.2f}% vs {label} {chg:+.2f}% "
                        f"（差 {portfolio_chg - chg:+.2f} 个百分点）"
                    ),
                }
            )

    highlights = _build_today_highlights(indices, contrib_rows, portfolio_chg, hs300_chg, watch_rows)

    cache_ttl = os.environ.get("MARKET_QUOTE_CACHE_SECONDS", "120")
    return {
        "indices": indices,
        "watchlist": watch_rows,
        "holdings_day": contrib_rows[:20],
        "signals": {
            "today_contrib_estimate": round(today_contrib, 2),
            "portfolio_change_pct_estimate": None if portfolio_chg is None else round(portfolio_chg, 4),
            "portfolio_vs_market": signal_text,
            "comparisons": comparisons,
            "today_highlights": highlights,
            "total_market_value": round(market_mv, 2),
            "total_profit": round(float(totals.get("total_profit") or 0), 2),
            "lifetime_profit": round(float(totals.get("lifetime_profit") or 0), 2),
        },
        "index_error": index_err,
        "quote_cache_seconds": int(cache_ttl) if str(cache_ttl).isdigit() else 120,
        "alert_cooldown_minutes": get_alert_cooldown_minutes(conn),
        "last_updated": now.isoformat(sep=" ", timespec="seconds"),
    }


def _resolve_price(
    rule: Dict[str, Any],
    holding_map: Dict[str, Dict[str, Any]],
    index_map: Dict[str, Dict[str, Any]],
) -> Tuple[Optional[float], str, Optional[float], Optional[float]]:
    """Return price, name, change_pct, prev_close."""
    code = str(rule.get("code") or "").strip()
    ttype = str(rule.get("target_type") or "").strip().lower()
    if ttype == "portfolio":
        # 组合层规则没有单一标的，价格与涨跌幅由 _portfolio_day_pnl 汇总；
        # 这里直接短路，避免拿 "PORTFOLIO" 去行情接口白跑一次请求。
        return None, rule.get("name") or "组合当日盈亏", None, None
    if ttype == "index":
        q = index_map.get(code) or {}
        price = q.get("price")
        name = q.get("name") or rule.get("name") or code
        return (
            None if price is None else float(price),
            name,
            q.get("change_pct"),
            q.get("prev_close"),
        )
    h = holding_map.get(code)
    if h:
        return (
            float(h.get("price") or 0) or None,
            h.get("name") or code,
            h.get("change_pct"),
            h.get("prev_close"),
        )
    try:
        q = fetch_eastmoney_quotes([code]).get(code) or {}
        if q.get("price") is not None:
            return (
                float(q["price"]),
                q.get("name") or rule.get("name") or code,
                q.get("change_pct"),
                q.get("prev_close"),
            )
    except Exception:
        logger.warning("拉取 %s 行情失败", code, exc_info=True)
        pass
    return None, rule.get("name") or code, None, None


def _rule_in_cooldown(conn, rule_id: int, cooldown_minutes: int, now: datetime) -> bool:
    if cooldown_minutes <= 0:
        return False
    row = conn.execute(
        """
        SELECT trigger_time FROM alert_events
        WHERE rule_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (rule_id,),
    ).fetchone()
    if not row:
        return False
    raw = row["trigger_time"] if isinstance(row, sqlite3.Row) else row[0]
    if not raw:
        return False
    try:
        if isinstance(raw, datetime):
            last = raw
        else:
            last = datetime.fromisoformat(str(raw).replace("Z", "").strip()[:19])
    except ValueError:
        return False
    return (now - last) < timedelta(minutes=cooldown_minutes)


def notify_feishu_alerts(triggered: List[Dict[str, Any]], webhook: Optional[str] = None) -> Dict[str, Any]:
    """Backward-compatible alias → multi-channel notify_price_alerts.

    ``webhook`` is only used as a one-off Feishu override when provided;
    otherwise channels come from notify event map / env.
    """
    if not triggered:
        return {"sent": False, "reason": "no_triggers", "results": []}
    try:
        try:
            from .notify import dispatch, build_price_alert_text, post_webhook_response
        except ImportError:
            from notify import dispatch, build_price_alert_text, post_webhook_response

        text = build_price_alert_text(triggered)
        if webhook:
            # legacy: force only this feishu webhook via temporary env-less path
            payload = {"msg_type": "text", "content": {"text": f"【invest-tracker 价格预警】\n{text}"}}
            try:
                # 校验与建连一步完成，避免攻击者可控 DNS 在两步之间换答案绕过 SSRF 校验
                res = post_webhook_response(webhook, payload, timeout=10)
                ok = 200 <= res.status_code < 300
                return {
                    "sent": ok,
                    "status_code": res.status_code,
                    "count": len(triggered),
                    "reason": None if ok else f"http_{res.status_code}",
                    "results": [{"channel": "feishu", "ok": ok, "status_code": res.status_code}],
                }
            except Exception as exc:
                return {"sent": False, "reason": str(exc), "count": len(triggered), "results": []}
        return dispatch(text, title="价格预警", event="price_alert", respect_cooldown=False)
    except Exception as exc:
        logger.warning("notify_price_alerts failed: %s", exc)
        return {"sent": False, "reason": str(exc), "count": len(triggered), "results": []}


def check_alerts(
    conn,
    *,
    record_events: bool = True,
    notify: bool = False,
    webhook: Optional[str] = None,
    respect_cooldown: bool = True,
) -> Dict[str, Any]:
    ensure_alert_tables(conn)
    rules = [
        r
        for r in list_alert_rules(conn)
        if int(r.get("enabled") or 0) == 1
    ]
    cooldown_minutes = get_alert_cooldown_minutes(conn) if respect_cooldown else 0
    if not rules:
        return {
            "triggered": [],
            "skipped_cooldown": [],
            "checked_count": 0,
            "trigger_count": 0,
            "cooldown_minutes": cooldown_minutes,
            "message": "没有启用的预警规则",
            "notify": {"sent": False, "reason": "no_rules"},
        }

    need_index = any(str(r.get("target_type")) == "index" for r in rules)
    index_map: Dict[str, Dict[str, Any]] = {}
    if need_index:
        try:
            index_map = fetch_index_quotes()
        except Exception:
            index_map = {}
    for r in rules:
        if str(r.get("target_type")) != "index":
            continue
        code = str(r.get("code") or "").strip()
        if code and code not in index_map:
            secid = _index_secid_map().get(code)
            try:
                extra = fetch_eastmoney_quotes([code], secid_map={code: secid} if secid else None)
                index_map.update(extra)
            except Exception:
                logger.warning("拉取指数 %s 行情失败", code, exc_info=True)

    holding_map = _holding_price_map(conn)
    portfolio = _portfolio_day_pnl(holding_map)
    triggered = []
    skipped_cooldown = []
    # 取不到数据而没被评估的规则要留痕：否则 checked_count 照算、triggered 为空，
    # 用户和日志都看不出"这条规则根本没跑"（停牌、源不返回昨收、整只行情失败）。
    skipped_no_data = []
    skipped_daily_cap = []
    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)

    # 每日上限只约束**定时推送**（notify=True）。手动「立即检查」是用户主动想看当前
    # 状态，被上限挡住只会让人以为规则坏了，所以那种情况下不启用上限。
    daily_cap = get_alert_daily_cap(conn)
    cap_active = bool(notify) and daily_cap > 0
    sent_today = _alert_events_today(conn, now) if cap_active else 0

    for r in rules:
        rule_type = str(r.get("rule_type") or "price").strip().lower() or "price"
        price, name, change_pct, prev_close = _resolve_price(r, holding_map, index_map)
        cond = str(r.get("condition") or "").lower()
        thr = float(r.get("threshold") or 0)

        # 三种规则比的是不同的量：绝对价格 / 日内涨跌幅 / 组合当日盈亏。
        # 归一成 value 之后，判定与文案都只剩一套分支。
        if rule_type == "portfolio_pnl":
            value = portfolio["change_pct"]
            name = "组合当日盈亏"
        elif rule_type == "change_pct":
            value = None if change_pct is None else float(change_pct)
        else:
            value = price

        if value is None:
            reason = {
                "portfolio_pnl": "今日没有任何持仓能算出昨收，组合当日盈亏未知",
                "change_pct": "取不到昨收，日内涨跌幅未知（停牌或数据源未返回）",
            }.get(rule_type, "取不到现价")
            skipped_no_data.append(
                {"rule_id": r["id"], "code": r.get("code"), "rule_type": rule_type, "reason": reason}
            )
            continue


        hit = (cond == "above" and value >= thr) or (cond == "below" and value <= thr)
        if not hit:
            continue
        if respect_cooldown and _rule_in_cooldown(conn, int(r["id"]), cooldown_minutes, now):
            skipped_cooldown.append(
                {
                    "rule_id": r["id"],
                    "code": r.get("code"),
                    "reason": f"冷却中（{cooldown_minutes} 分钟内已触发过）",
                }
            )
            continue

        if cap_active and sent_today >= daily_cap:
            skipped_daily_cap.append(
                {
                    "rule_id": r["id"],
                    "code": r.get("code"),
                    "reason": f"已达今日上限（{daily_cap} 条），本条不再推送",
                }
            )
            continue

        comparator = "≥" if cond == "above" else "≤"
        if rule_type == "portfolio_pnl":
            amount = portfolio["amount"]
            msg = (
                f"组合当日盈亏 {value:+.2f}% {comparator} 阈值 {thr:+.2f}%"
                f"（约 {amount:+,.0f} 元）"
            )
        elif rule_type == "change_pct":
            msg = (
                f"{name}({r.get('code')}) 日内 {value:+.2f}% {comparator} 阈值 {thr:+.2f}%"
            )
            # 涨跌幅规则靠昨收就能判定，极少数情况下拿不到现价（停牌瞬间/源只回昨收），
            # 此时不能按价格格式化，否则整轮 /alerts/check 直接 500。
            if price is not None:
                msg += f"，现价 {price:.4f}"
            if prev_close is not None:
                try:
                    msg += f"，昨收 {float(prev_close):.4f}"
                except (TypeError, ValueError):
                    pass
        else:
            chg_part = ""
            if change_pct is not None:
                chg_part = f"，涨跌 {float(change_pct):+.2f}%"
            prev_part = ""
            if prev_close is not None:
                try:
                    prev_part = f"，昨收 {float(prev_close):.4f}"
                except (TypeError, ValueError):
                    prev_part = ""
            msg = (
                f"{name}({r.get('code')}) 现价 {price:.4f} "
                f"{comparator} 阈值 {thr:.4f}"
                f"{chg_part}{prev_part}"
            )

        item = {
            "rule_id": r["id"],
            "rule_type": rule_type,
            "target_type": r.get("target_type"),
            "code": r.get("code"),
            "name": name,
            "condition": cond,
            "threshold": thr,
            "price": price,
            "value": round(float(value), 4),
            "change_pct": None if change_pct is None else round(float(change_pct), 4),
            "prev_close": prev_close,
            "message": msg,
            "trigger_time": now.isoformat(sep=" ", timespec="seconds"),
        }
        triggered.append(item)
        if record_events:
            conn.execute(
                """
                INSERT INTO alert_events
                    (rule_id, trigger_time, target_code, triggered_price, threshold,
                     message, rule_type, value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                # 组合规则没有单一标的价，写 NULL 而不是 0 —— 写 0 会让预警历史
                # 显示成"价格 0.0000"，和"某标的真的跌到 0"分不开。
                (r["id"], now, r.get("code"), price, thr, msg, rule_type, float(value)),
            )
            sent_today += 1

    notify_result = {"sent": False, "reason": "skipped"}
    if notify:
        try:
            try:
                from .notify import notify_price_alerts
            except ImportError:
                from notify import notify_price_alerts

            if webhook:
                notify_result = notify_feishu_alerts(triggered, webhook=webhook)
            else:
                notify_result = notify_price_alerts(triggered, conn=conn)
        except Exception as exc:
            logger.warning("alert notify failed: %s", exc)
            notify_result = {"sent": False, "reason": str(exc)}

    return {
        "triggered": triggered,
        "skipped_cooldown": skipped_cooldown,
        "skipped_no_data": skipped_no_data,
        "skipped_daily_cap": skipped_daily_cap,
        "daily_cap": daily_cap,
        "checked_count": len(rules),
        "trigger_count": len(triggered),
        "cooldown_minutes": cooldown_minutes,
        "notify": notify_result,
    }
