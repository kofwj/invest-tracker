"""总资产 / 净值校准（账实平差）。

个人记账系统真正的死法不是算错，而是「看板显示 1,024,500、券商 App 显示 1,021,800」
这种日积月累的偏差把信任磨掉：为了找那 2,700 块要翻 90 天交割单，于是干脆不记了。

所以这里只做一件事：**承认差额存在**。

- 用户填一个「实测总资产」（券商 + 银行实际看到的数）；
- 差额作为一条可见的「记账平差」挂到总资产上（settings.total_assets_adjustment）；
- 看板 / 快照立刻与实盘对齐，平差余额本身可见，下次校准再吃一次差额即可（可正可负，会自动收敛）。

不做的事：不把差额摊回具体持仓或流水。持仓差异归券商 CSV 导入（broker_reconcile），
证券现金差异归现金校准（securities_cash），这里只管「合起来对不上」的那部分。
"""
from __future__ import annotations

import math
import sqlite3
from datetime import date, datetime
from typing import Any, Dict, Optional

try:
    from .cash import get_setting_float, set_setting
except ImportError:
    from cash import get_setting_float, set_setting

TOTAL_ASSETS_ADJUSTMENT_KEY = "total_assets_adjustment"
# 多久没校准就该提醒。30 天 ≈ 一个月只对一次账，比「每周逐笔对」现实得多。
CALIBRATION_STALE_DAYS = 30


def ensure_total_asset_calibration_table(conn) -> None:
    """校准历史表：每次「实测 → 吸收差额」留一行，幂等。"""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS total_asset_calibrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            manual_total_assets REAL NOT NULL,
            displayed_total_assets REAL NOT NULL,
            gap REAL NOT NULL,
            adjustment_after REAL NOT NULL,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""
    )


def total_asset_adjustment(conn) -> float:
    """当前累计平差余额。读不到（老库 / 空库 / 表未建）一律按 0 处理。"""
    try:
        value = get_setting_float(conn, TOTAL_ASSETS_ADJUSTMENT_KEY, 0.0)
    except sqlite3.OperationalError:
        return 0.0
    if not math.isfinite(value):
        return 0.0
    return float(value)


def _today_iso(today_iso: Optional[str] = None) -> str:
    if today_iso:
        return str(today_iso)[:10]
    try:
        from datetime import datetime as _dt

        try:
            from .database import LOCAL_TZ
        except ImportError:
            from database import LOCAL_TZ

        if LOCAL_TZ is not None:
            return _dt.now(LOCAL_TZ).date().isoformat()
        return _dt.now().date().isoformat()
    except Exception:
        return date.today().isoformat()


def apply_calibration(
    conn,
    manual_total_assets: float,
    *,
    displayed_total_assets: Optional[float] = None,
    note: str = "",
    date_iso: Optional[str] = None,
) -> Dict[str, Any]:
    """把「实测总资产」吃进账本。

    `displayed_total_assets` 是校准前看板上的总资产（**已包含**历史平差）。
    差额 = 实测 − 看板，新的平差余额 = 旧平差 + 差额，于是校准后看板正好等于实测值。
    多校准几次不会累加失真：每次都是「对着当前显示值」重新收敛。
    """
    try:
        manual = float(manual_total_assets)
    except (TypeError, ValueError):
        raise ValueError("实测总资产必须是数字")
    if not math.isfinite(manual):
        raise ValueError("实测总资产必须是有限数字")

    if displayed_total_assets is None:
        try:
            from .portfolio_totals import compute_portfolio_totals
        except ImportError:
            from portfolio_totals import compute_portfolio_totals

        displayed = float(compute_portfolio_totals(conn).get("total_assets") or 0.0)
    else:
        displayed = float(displayed_total_assets)
    if not math.isfinite(displayed):
        displayed = 0.0

    ensure_total_asset_calibration_table(conn)
    before = total_asset_adjustment(conn)
    gap = round(manual - displayed, 2)
    after = round(before + gap, 2)
    day = _today_iso(date_iso)

    conn.execute(
        """INSERT INTO total_asset_calibrations
           (date, manual_total_assets, displayed_total_assets, gap, adjustment_after, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (day, manual, round(displayed, 2), gap, after, str(note or "")),
    )
    set_setting(conn, TOTAL_ASSETS_ADJUSTMENT_KEY, after)
    return {
        "status": "success",
        "date": day,
        "manual_total_assets": round(manual, 2),
        "displayed_total_assets": round(displayed, 2),
        "gap": gap,
        "adjustment_before": round(before, 2),
        "adjustment_after": after,
        "calibrated_total_assets": round(displayed + gap, 2),
        "note": str(note or ""),
    }


def latest_calibration(conn) -> Optional[Dict[str, Any]]:
    try:
        ensure_total_asset_calibration_table(conn)
        row = conn.execute(
            "SELECT * FROM total_asset_calibrations ORDER BY date DESC, id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    return dict(row)


def _days_between(date_iso: str, today_iso: str) -> Optional[int]:
    try:
        start = datetime.fromisoformat(str(date_iso)[:10]).date()
        end = datetime.fromisoformat(str(today_iso)[:10]).date()
    except Exception:
        return None
    return max((end - start).days, 0)


def calibration_status(conn, today_iso: Optional[str] = None) -> Dict[str, Any]:
    """看板用的校准状态：平差余额、距上次校准多少天、上次差额多少。"""
    today = _today_iso(today_iso)
    adjustment = total_asset_adjustment(conn)
    last = latest_calibration(conn)
    if not last:
        return {
            "adjustment": round(adjustment, 2),
            "has_history": False,
            "last_calibration_date": None,
            "days_since": None,
            "last_gap": None,
            "last_manual_total_assets": None,
            "stale_days": CALIBRATION_STALE_DAYS,
            "level": "never",
            "hint": "还没有校准过：填一次券商+银行的实际总额，把账本和实盘对齐",
        }

    days = _days_between(last.get("date"), today)
    gap = last.get("gap")
    gap = None if gap is None else round(float(gap), 2)
    if days is None:
        level = "due"
    elif days >= CALIBRATION_STALE_DAYS * 2:
        level = "overdue"
    elif days >= CALIBRATION_STALE_DAYS:
        level = "due"
    else:
        level = "ok"

    if days is None:
        head = f"上次校准 {last.get('date')}"
    elif days == 0:
        head = "今天校准过"
    else:
        head = f"距上次校准 {days} 天"
    tail = "" if gap is None else f" · 上次差额 {gap:+,.2f}"
    return {
        "adjustment": round(adjustment, 2),
        "has_history": True,
        "last_calibration_date": last.get("date"),
        "days_since": days,
        "last_gap": gap,
        "last_manual_total_assets": (
            None if last.get("manual_total_assets") is None else round(float(last["manual_total_assets"]), 2)
        ),
        "stale_days": CALIBRATION_STALE_DAYS,
        "level": level,
        "hint": head + tail,
    }
