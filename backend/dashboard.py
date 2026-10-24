try:
    from .portfolio_totals import compute_portfolio_totals
    from .total_asset_calibration import CALIBRATION_STALE_DAYS, calibration_status
    from .snapshots import latest_price_sync_at, manual_price_codes as _manual_price_codes
except ImportError:
    from portfolio_totals import compute_portfolio_totals
    from total_asset_calibration import CALIBRATION_STALE_DAYS, calibration_status
    from snapshots import latest_price_sync_at, manual_price_codes as _manual_price_codes

# Re-export for older imports / tests that may reference this name.
PENDING_DIRECTIONS = ("申购待确认", "待确认申购")


def _safe_manual_price_codes(conn):
    """人工填价代码列表；任何异常都回落空列表（dashboard 不能因为读不到它而 500）。"""
    try:
        return list(_manual_price_codes(conn) or [])
    except Exception:
        return []

def _safe_calibration_status(conn):
    """校准状态；读不出来就退化成「未校准」，dashboard 不能因为提醒文案而 500。"""
    try:
        return calibration_status(conn)
    except Exception:
        return {
            "adjustment": 0.0,
            "has_history": False,
            "days_since": None,
            "last_gap": None,
            "stale_days": CALIBRATION_STALE_DAYS,
            "level": "never",
            "hint": "",
        }


def build_dashboard(conn):
    totals = compute_portfolio_totals(conn)

    price_row = conn.execute(
        "SELECT MAX(updated_at) AS latest FROM holdings WHERE quantity > 0 AND updated_at IS NOT NULL"
    ).fetchone()
    snapshot_row = conn.execute("SELECT MAX(date) AS latest FROM daily_snapshots").fetchone()

    latest_price = price_row["latest"] if price_row else None
    price_age_hours = None
    price_stale = False
    if latest_price:
        try:
            from datetime import datetime

            try:
                from .database import LOCAL_TZ
            except ImportError:
                from database import LOCAL_TZ
            raw = str(latest_price).replace("T", " ")[:19]
            ts = datetime.fromisoformat(raw)
            now = datetime.now(LOCAL_TZ).replace(tzinfo=None) if LOCAL_TZ else datetime.now()
            price_age_hours = round((now - ts).total_seconds() / 3600.0, 2)
            # 交易日口径粗略：超过 20 小时未更新视为偏旧（隔夜/周末另论）
            price_stale = price_age_hours >= 20
        except Exception:
            price_age_hours = None
            price_stale = False

    return {
        "total_market_value": totals["total_market_value"],
        "bank_balance": totals["bank_balance"],
        "securities_cash": totals["securities_cash"],
        "pending_purchase": totals["pending_purchase"],
        "pending_count": totals["pending_count"],
        "total_assets": totals["total_assets"],
        # 记账平差：用户「实测总资产」与账面差额的累计余额（默认 0），
        # 单独列出来，前端在总资产旁边标一句「其中平差 ±X」，不藏进任何分项里。
        "total_assets_adjustment": totals.get("total_assets_adjustment", 0.0),
        # 校准状态：距上次校准多少天、上次差额多少，供看板提醒「该对账了」
        "calibration": _safe_calibration_status(conn),
        "total_profit": totals["total_profit"],
        "lifetime_profit": totals["lifetime_profit"],
        "holdings_count": totals["holdings_count"],
        "latest_price_updated_at": latest_price,
        "price_age_hours": price_age_hours,
        "price_stale": price_stale,
        "latest_snapshot_date": snapshot_row["latest"] if snapshot_row else None,
        "category_market_value": totals.get("category_market_value", {}),
        # 缺价持仓计数（市值按 0 计），供快照打标记与前端提示
        "unpriced_count": totals.get("unpriced_count", 0),
        "unpriced_codes": totals.get("unpriced_codes", []),
        # 当前用「人工填价」兜底的持仓（手动改过价、还没被真实行情覆盖），
        # 供前端在持仓页打标记，也便于排查"这个数是我自己填的"
        "manual_price_codes": _safe_manual_price_codes(conn),
        # 最近一次「成功同步到至少一只价格」的时间（settings.last_price_sync_at，
        # 老库回落 MAX(holdings.updated_at)）；快照价格闸门的判据来源。
        "last_price_sync_at": latest_price_sync_at(conn),
    }
