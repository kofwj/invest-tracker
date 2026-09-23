"""缺价持仓回归测试（任务二）。

真实事件：2026-09-22 16:40 那次同步 8/10 只取价失败，缺价持仓的 last_price 保持 0，
市值被按 0 计入总资产、浮盈记成 -avg_cost*qty，并把错误的当日收益写进快照。
这里锁定「只记录 + 只暴露标记、不改数字、不阻断快照」的保守行为。
"""
import sqlite3


def _insert_holding(conn, code, quantity, avg_cost, diluted_cost, last_price):
    conn.execute(
        "INSERT INTO holdings (code, name, category, quantity, avg_cost, diluted_cost, "
        "total_dividend, last_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (code, code, "A股权益", quantity, avg_cost, diluted_cost, 0.0, last_price),
    )


def _seed_holdings(app_module, rows):
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        for row in rows:
            _insert_holding(conn, *row)
        conn.commit()
    finally:
        conn.close()


def _set_price_sync_at(app_module, day_iso):
    """测试造数据：模拟当天成功同步过一次价格（否则快照价格闸门会 409）。"""
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('last_price_sync_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (f"{day_iso} 15:20:00",),
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_snapshot(app_module, date_iso):
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        return conn.execute(
            "SELECT date, total_assets, total_market_value, unpriced_count "
            "FROM daily_snapshots WHERE date = ?",
            (date_iso,),
        ).fetchone()
    finally:
        conn.close()


def test_compute_portfolio_totals_reports_unpriced_without_changing_numbers(app_module):
    # 正常持仓 + 缺价(0) + 缺价(NULL)
    _seed_holdings(
        app_module,
        [
            ("600001", 100, 8.0, 7.0, 12.0),
            ("600002", 200, 5.0, 5.0, 0),
            ("600003", 10, 3.0, 3.0, None),
        ],
    )

    from portfolio_totals import compute_portfolio_totals

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        totals = compute_portfolio_totals(conn)
    finally:
        conn.close()

    assert totals["unpriced_codes"] == ["600002", "600003"]
    assert totals["unpriced_count"] == 2

    # 现有键名 / 数值语义完全不变：缺价持仓市值仍按 0 计
    for key in (
        "holdings",
        "holdings_count",
        "total_market_value",
        "bank_balance",
        "securities_cash",
        "cash_base",
        "transaction_cash_flow",
        "pending_purchase",
        "pending_count",
        "total_assets",
        "total_profit",
        "lifetime_profit",
        "category_market_value",
    ):
        assert key in totals, key
    assert totals["holdings_count"] == 3
    assert totals["total_market_value"] == 1200.0
    assert totals["total_assets"] == 1200.0
    assert round(totals["total_profit"], 2) == -630.0


def test_priced_holdings_never_appear_in_unpriced_codes(app_module):
    _seed_holdings(app_module, [("600010", 100, 8.0, 7.0, 12.0), ("600011", 50, 4.0, 4.0, 4.5)])

    from portfolio_totals import compute_portfolio_totals

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        totals = compute_portfolio_totals(conn)
    finally:
        conn.close()

    assert totals["unpriced_codes"] == []
    assert totals["unpriced_count"] == 0


def test_zero_quantity_holding_is_not_counted_as_unpriced(app_module):
    # 已清仓（quantity = 0）即使没价格也不算缺价
    _seed_holdings(app_module, [("600020", 0, 8.0, 7.0, 0)])

    from portfolio_totals import compute_portfolio_totals

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        totals = compute_portfolio_totals(conn)
    finally:
        conn.close()

    assert totals["unpriced_count"] == 0
    assert totals["unpriced_codes"] == []


def test_snapshot_records_and_refreshes_unpriced_count(client, app_module, monkeypatch):
    import database as db

    monkeypatch.setattr(db, "local_today_iso", lambda: "2026-09-22")
    _seed_holdings(
        app_module,
        [
            ("600101", 100, 8.0, 7.0, 12.0),
            ("600102", 200, 5.0, 5.0, 0),
            ("600103", 10, 3.0, 3.0, None),
        ],
    )

    _set_price_sync_at(app_module, "2026-09-22")

    first = client.post("/snapshots")
    assert first.status_code == 200
    assert first.json()["action"] == "created"

    row = _fetch_snapshot(app_module, "2026-09-22")
    assert row is not None
    assert row[3] == 2  # 缺价 2 只（0 / NULL），正常持仓不计
    # 缺价持仓市值仍按 0 计：快照数字与改动前口径一致
    assert row[2] == 1200.0

    # 同一天再快照：更新分支也要刷新缺价计数（取价失败的那只恢复了）
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute("UPDATE holdings SET last_price = 6 WHERE code = '600102'")
        conn.commit()
    finally:
        conn.close()

    second = client.post("/snapshots")
    assert second.status_code == 200
    assert second.json()["action"] == "updated"
    assert _fetch_snapshot(app_module, "2026-09-22")[3] == 1


def test_snapshot_from_legacy_dashboard_dict_still_records_unpriced_count(app_module):
    """老调用方（dashboard 字典里没有缺价键）也要落库正确，而不是静默写 0。"""
    _seed_holdings(app_module, [("600201", 100, 8.0, 7.0, 0), ("600202", 10, 3.0, 3.0, 4.0)])

    from database import open_db
    from snapshots import create_snapshot_record

    legacy_dashboard = {
        "total_assets": 0,
        "total_market_value": 0,
        "bank_balance": 0,
        "securities_cash": 0,
        "total_profit": 0,
        "holdings_count": 2,
    }
    with open_db() as conn:
        create_snapshot_record(conn, "2026-09-23", legacy_dashboard)
        conn.commit()

    assert _fetch_snapshot(app_module, "2026-09-23")[3] == 1


def test_timeline_exposes_unpriced_count(client, app_module, monkeypatch):
    import database as db

    monkeypatch.setattr(db, "local_today_iso", lambda: "2026-09-24")
    _seed_holdings(app_module, [("600301", 100, 8.0, 7.0, 0)])

    _set_price_sync_at(app_module, "2026-09-24")

    res = client.post("/snapshots")
    assert res.status_code == 200

    rows = client.get("/performance/timeline").json()
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-09-24"]["unpriced_count"] == 1
    # 缺价没有阻断快照，逐日收益依旧照常给出
    assert by_date["2026-09-24"]["daily_change"] is None

    # 历史快照（建列之前写的老数据）读出来是 0，不是 None/缺字段
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO daily_snapshots (date, total_assets, total_market_value, bank_balance, "
            "securities_cash, total_profit, holdings_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-09-25", 1000, 1000, 0, 0, 0, 1),
        )
        conn.commit()
    finally:
        conn.close()

    rows = client.get("/performance/timeline").json()
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-09-25"]["unpriced_count"] == 0
