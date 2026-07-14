"""Market summary + simple price alerts (read-only observer over the ledger).

Does not mutate holdings/transactions. Index/holding quotes come from Eastmoney.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

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

ALLOWED_TARGET_TYPES = {"holding", "index"}
ALLOWED_CONDITIONS = {"above", "below"}


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
            updated_at DATETIME
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS alert_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER,
            trigger_time DATETIME,
            target_code TEXT,
            triggered_price REAL,
            threshold REAL,
            message TEXT
        )"""
    )


def _row_to_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(row)


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
) -> List[Dict[str, Any]]:
    ensure_alert_tables(conn)
    limit = max(1, min(int(limit or 50), 500))
    code = str(code or "").strip()
    if code:
        rows = conn.execute(
            """
            SELECT * FROM alert_events
            WHERE target_code = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (code, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM alert_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_alert_rule(
    conn,
    *,
    target_type: str,
    code: str,
    condition: str,
    threshold: float,
    name: str = "",
    enabled: bool = True,
) -> Dict[str, Any]:
    ensure_alert_tables(conn)
    target_type = str(target_type or "").strip().lower()
    code = str(code or "").strip()
    condition = str(condition or "").strip().lower()
    name = str(name or "").strip()
    if target_type not in ALLOWED_TARGET_TYPES:
        raise ValueError("target_type 必须是 holding 或 index")
    if not code:
        raise ValueError("code 不能为空")
    if condition not in ALLOWED_CONDITIONS:
        raise ValueError("condition 必须是 above 或 below")
    try:
        threshold = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("threshold 必须是数字") from exc
    if threshold < 0:
        raise ValueError("threshold 不能为负")

    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    cur = conn.execute(
        """
        INSERT INTO alert_rules
            (target_type, code, name, condition, threshold, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            target_type,
            code,
            name or code,
            condition,
            threshold,
            1 if enabled else 0,
            now,
            now,
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

    target_type = str(payload.get("target_type", ex["target_type"]) or "").strip().lower()
    code = str(payload.get("code", ex["code"]) or "").strip()
    condition = str(payload.get("condition", ex["condition"]) or "").strip().lower()
    name = str(payload.get("name", ex.get("name") or "") or "").strip()
    if "threshold" in payload:
        try:
            threshold = float(payload["threshold"])
        except (TypeError, ValueError) as exc:
            raise ValueError("threshold 必须是数字") from exc
    else:
        threshold = float(ex["threshold"])
    if "enabled" in payload:
        enabled = 1 if payload["enabled"] else 0
    else:
        enabled = int(ex.get("enabled") or 0)

    if target_type not in ALLOWED_TARGET_TYPES:
        raise ValueError("target_type 必须是 holding 或 index")
    if not code:
        raise ValueError("code 不能为空")
    if condition not in ALLOWED_CONDITIONS:
        raise ValueError("condition 必须是 above 或 below")
    if threshold < 0:
        raise ValueError("threshold 不能为负")

    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    conn.execute(
        """
        UPDATE alert_rules
        SET target_type = ?, code = ?, name = ?, condition = ?, threshold = ?,
            enabled = ?, updated_at = ?
        WHERE id = ?
        """,
        (target_type, code, name or code, condition, threshold, enabled, now, rule_id),
    )
    row = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
    return _row_to_dict(row)


def delete_alert_rule(conn, rule_id: int) -> bool:
    ensure_alert_tables(conn)
    cur = conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    return cur.rowcount > 0


def _index_secid_map() -> Dict[str, str]:
    return {item["code"]: item["secid"] for item in DEFAULT_INDICES}


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
        # Stable contrib: if live % missing but have prev_close + price, derive
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
        indices.append(
            {
                "code": code,
                "name": q.get("name") or item["name"],
                "price": q.get("price"),
                "change_pct": q.get("change_pct"),
                "prev_close": q.get("prev_close"),
                "available": q.get("price") is not None,
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
                "day_contrib": None if day_pnl is None else round(day_pnl, 2),
                "source": h["source"],
            }
        )
    contrib_rows.sort(key=lambda r: abs(r.get("day_contrib") or 0), reverse=True)

    totals = compute_portfolio_totals(conn)
    hs300 = next((i for i in indices if i["code"] == "000300"), None)
    portfolio_chg = None
    market_mv = float(totals.get("total_market_value") or 0)
    if market_mv > 0 and any(r.get("day_contrib") is not None for r in contrib_rows):
        portfolio_chg = (today_contrib / market_mv) * 100.0

    signal_text = "持仓与指数涨跌可能背离：请以持仓逐项贡献为准，不要只看大盘。"
    if portfolio_chg is not None and hs300 and hs300.get("change_pct") is not None:
        p = portfolio_chg
        m = float(hs300["change_pct"])
        if p >= 0 and m < 0:
            signal_text = f"今日持仓约 {p:+.2f}%，沪深300 {m:+.2f}%：持仓相对大盘偏强。"
        elif p < 0 and m > 0:
            signal_text = f"今日持仓约 {p:+.2f}%，沪深300 {m:+.2f}%：大盘涨、组合偏弱（防御仓常见）。"
        elif abs(p - m) < 0.15:
            signal_text = f"今日持仓约 {p:+.2f}%，与沪深300（{m:+.2f}%）大致同步。"
        else:
            signal_text = f"今日持仓约 {p:+.2f}%，沪深300 {m:+.2f}%。"

    cache_ttl = os.environ.get("MARKET_QUOTE_CACHE_SECONDS", "120")
    return {
        "indices": indices,
        "holdings_day": contrib_rows[:20],
        "signals": {
            "today_contrib_estimate": round(today_contrib, 2),
            "portfolio_change_pct_estimate": None if portfolio_chg is None else round(portfolio_chg, 4),
            "portfolio_vs_market": signal_text,
            "total_market_value": round(market_mv, 2),
            "total_profit": round(float(totals.get("total_profit") or 0), 2),
            "lifetime_profit": round(float(totals.get("lifetime_profit") or 0), 2),
        },
        "index_error": index_err,
        "quote_cache_seconds": int(cache_ttl) if str(cache_ttl).isdigit() else 120,
        "last_updated": now.isoformat(sep=" ", timespec="seconds"),
    }


def _resolve_price(
    rule: Dict[str, Any],
    holding_map: Dict[str, Dict[str, Any]],
    index_map: Dict[str, Dict[str, Any]],
) -> Tuple[Optional[float], str]:
    code = str(rule.get("code") or "").strip()
    ttype = str(rule.get("target_type") or "").strip().lower()
    if ttype == "index":
        q = index_map.get(code) or {}
        price = q.get("price")
        name = q.get("name") or rule.get("name") or code
        return (None if price is None else float(price), name)
    h = holding_map.get(code)
    if h:
        return float(h.get("price") or 0) or None, h.get("name") or code
    try:
        q = fetch_eastmoney_quotes([code]).get(code) or {}
        if q.get("price") is not None:
            return float(q["price"]), q.get("name") or rule.get("name") or code
    except Exception:
        pass
    return None, rule.get("name") or code


def notify_feishu_alerts(triggered: List[Dict[str, Any]], webhook: Optional[str] = None) -> Dict[str, Any]:
    """Send triggered alerts to Feishu bot webhook. No-op if webhook empty."""
    webhook = (webhook if webhook is not None else os.environ.get("FEISHU_ALERT_WEBHOOK", "")).strip()
    if not webhook:
        return {"sent": False, "reason": "no_webhook"}
    if not triggered:
        return {"sent": False, "reason": "no_triggers"}
    lines = ["【invest-tracker 价格预警】"]
    for t in triggered[:30]:
        lines.append(str(t.get("message") or t))
    if len(triggered) > 30:
        lines.append(f"…共 {len(triggered)} 条")
    payload = {"msg_type": "text", "content": {"text": "\n".join(lines)}}
    try:
        res = requests.post(webhook, json=payload, timeout=10)
        ok = 200 <= res.status_code < 300
        if not ok:
            logger.warning("feishu alert webhook status=%s body=%s", res.status_code, res.text[:200])
        return {
            "sent": ok,
            "status_code": res.status_code,
            "count": len(triggered),
            "reason": None if ok else f"http_{res.status_code}",
        }
    except Exception as exc:
        logger.warning("feishu alert webhook failed: %s", exc)
        return {"sent": False, "reason": str(exc), "count": len(triggered)}


def check_alerts(
    conn,
    *,
    record_events: bool = True,
    notify: bool = False,
    webhook: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_alert_tables(conn)
    rules = [
        r
        for r in list_alert_rules(conn)
        if int(r.get("enabled") or 0) == 1
    ]
    if not rules:
        return {
            "triggered": [],
            "checked_count": 0,
            "trigger_count": 0,
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
                pass

    holding_map = _holding_price_map(conn)
    triggered = []
    now = datetime.now(LOCAL_TZ).replace(tzinfo=None)
    for r in rules:
        price, name = _resolve_price(r, holding_map, index_map)
        if price is None:
            continue
        cond = str(r.get("condition") or "").lower()
        thr = float(r.get("threshold") or 0)
        hit = (cond == "above" and price >= thr) or (cond == "below" and price <= thr)
        if not hit:
            continue
        msg = (
            f"{name}({r.get('code')}) 现价 {price:.4f} "
            f"{'≥' if cond == 'above' else '≤'} 阈值 {thr:.4f}"
        )
        item = {
            "rule_id": r["id"],
            "target_type": r.get("target_type"),
            "code": r.get("code"),
            "name": name,
            "condition": cond,
            "threshold": thr,
            "price": price,
            "message": msg,
            "trigger_time": now.isoformat(sep=" ", timespec="seconds"),
        }
        triggered.append(item)
        if record_events:
            conn.execute(
                """
                INSERT INTO alert_events
                    (rule_id, trigger_time, target_code, triggered_price, threshold, message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (r["id"], now, r.get("code"), price, thr, msg),
            )

    notify_result = {"sent": False, "reason": "skipped"}
    if notify:
        notify_result = notify_feishu_alerts(triggered, webhook=webhook)

    return {
        "triggered": triggered,
        "checked_count": len(rules),
        "trigger_count": len(triggered),
        "notify": notify_result,
    }
