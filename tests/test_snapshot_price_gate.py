"""快照「价格整体没更新」闸门回归测试。

真实风险：如果某天两次价格同步都失败，16:40 的 cron 快照会沿用前一天的价格，
当日收益显示成约 0，并污染 TWR / Sharpe / 今年 / 时间轴收益尺。
这里锁定契约：
- settings.last_price_sync_at 只在「至少抓到一只价格」时写入；
- 价格不是今天的 → POST /snapshots 409（除非 force=true，落库 price_stale=1）；
- POST /cron/snapshot 价格不新鲜时只写日志、不写库；
- 没有 quantity>0 持仓的用户一律放行（只存银行存款的用户也能记快照）。
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


def _set_price_sync_at(app_module, value):
    """模拟「一次成功的价格同步」：写 settings.last_price_sync_at。"""
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('last_price_sync_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (value,),
        )
        conn.commit()
    finally:
        conn.close()


def _snapshot_rows(app_module):
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        return conn.execute(
            "SELECT date, total_assets, price_date, price_stale FROM daily_snapshots ORDER BY date"
        ).fetchall()
    finally:
        conn.close()


def _today(monkeypatch, day_iso):
    """把"今天"固定住。

    /snapshots 走 database 模块属性；routers_cron 是 import 时绑定名字，
    得单独 patch，否则 cron 用的是真实日期。
    """
    import database as db
    import routers_cron

    monkeypatch.setattr(db, "local_today_iso", lambda: day_iso)
    monkeypatch.setattr(routers_cron, "local_today_iso", lambda: day_iso)


def test_fresh_price_snapshot_is_recorded_not_stale(client, app_module, monkeypatch):
    _today(monkeypatch, "2026-09-22")
    _seed_holdings(app_module, [("600401", 100, 8.0, 7.0, 12.0)])
    _set_price_sync_at(app_module, "2026-09-22 15:20:00")

    res = client.post("/snapshots")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["action"] == "created"
    assert data["price_stale"] == 0
    assert data["price_date"] == "2026-09-22"
    # 已有响应结构不能变
    assert data["date"] == "2026-09-22"
    assert isinstance(data["id"], int)
    assert "snapshot" in data

    rows = _snapshot_rows(app_module)
    assert len(rows) == 1
    assert rows[0][0] == "2026-09-22"
    assert rows[0][2] == "2026-09-22"
    assert rows[0][3] == 0


def test_stale_price_blocks_snapshot_unless_forced(client, app_module, monkeypatch):
    _today(monkeypatch, "2026-09-22")
    _seed_holdings(app_module, [("600402", 100, 8.0, 7.0, 12.0)])
    _set_price_sync_at(app_module, "2026-09-21 15:20:00")

    blocked = client.post("/snapshots")
    assert blocked.status_code == 409
    detail = blocked.json()["detail"]
    assert "2026-09-21" in detail  # 必须带上基准日期
    assert "force=true" in detail
    assert _snapshot_rows(app_module) == []  # 被拦住时一行都不落库

    forced = client.post("/snapshots", params={"force": "true"})
    assert forced.status_code == 200
    data = forced.json()
    assert data["action"] == "created"
    assert data["price_stale"] == 1
    assert data["price_date"] == "2026-09-21"

    rows = _snapshot_rows(app_module)
    assert len(rows) == 1
    assert rows[0][2] == "2026-09-21"  # price_date = 旧价日期
    assert rows[0][3] == 1  # price_stale = 1

    # 同一天再 force：走更新分支，两列同样保持低置信标记
    again = client.post("/snapshots?force=true")
    assert again.status_code == 200
    assert again.json()["action"] == "updated"
    rows = _snapshot_rows(app_module)
    assert len(rows) == 1
    assert rows[0][3] == 1


def test_cron_snapshot_skips_without_writing_when_price_stale(client, app_module, monkeypatch):
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    headers = {"X-Cron-Token": "correct-cron-token"}
    _today(monkeypatch, "2026-09-22")
    _seed_holdings(app_module, [("600403", 100, 8.0, 7.0, 12.0)])
    _set_price_sync_at(app_module, "2026-09-21 15:20:00")

    # 先造一行前一天的快照，用来验证 skip 时既没新增也没更新
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO daily_snapshots (date, total_assets, total_market_value, bank_balance, "
            "securities_cash, total_profit, holdings_count, price_date, price_stale) "
            "VALUES ('2026-09-21', 1234.0, 1234.0, 0, 0, 0, 1, NULL, 0)"
        )
        conn.commit()
    finally:
        conn.close()

    res = client.post("/cron/snapshot", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "skipped"
    assert data["reason"] == "price_stale"
    assert data["price_date"] == "2026-09-21"

    rows = _snapshot_rows(app_module)
    assert len(rows) == 1  # 没有新增
    assert rows[0][0] == "2026-09-21"
    assert rows[0][1] == 1234.0  # 老行内容原样，没被更新
    assert rows[0][3] == 0

    # 价格变新鲜后恢复原行为（照常写库）
    _set_price_sync_at(app_module, "2026-09-22 16:40:00")
    fresh = client.post("/cron/snapshot", headers=headers)
    assert fresh.status_code == 200
    fresh_data = fresh.json()
    assert fresh_data["status"] == "success"
    assert fresh_data["action"] == "created"
    assert fresh_data["date"] == "2026-09-22"
    assert [r[0] for r in _snapshot_rows(app_module)] == ["2026-09-21", "2026-09-22"]


def test_no_holdings_needing_price_never_gated(client, app_module, monkeypatch):
    """只存银行存款/已清仓的用户：从未同步过价格也要能记快照。"""
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    _today(monkeypatch, "2026-09-23")
    # quantity = 0 的已清仓持仓不算「需要定价」
    _seed_holdings(app_module, [("600404", 0, 8.0, 7.0, 0)])

    res = client.post("/snapshots")
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "created"
    assert data["price_stale"] == 0
    assert data["price_date"] is None

    rows = _snapshot_rows(app_module)
    assert len(rows) == 1
    assert rows[0][3] == 0

    cron = client.post("/cron/snapshot", headers={"X-Cron-Token": "correct-cron-token"})
    assert cron.status_code == 200
    assert cron.json()["status"] == "success"


def test_legacy_db_falls_back_to_holdings_updated_at(client, app_module, monkeypatch):
    """老库没有 last_price_sync_at：回落到 MAX(holdings.updated_at)，当天就放行。"""
    _today(monkeypatch, "2026-09-24")
    _seed_holdings(app_module, [("600405", 100, 8.0, 7.0, 12.0)])
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute("UPDATE holdings SET updated_at = '2026-09-24 15:20:00' WHERE code = '600405'")
        conn.commit()
    finally:
        conn.close()

    res = client.post("/snapshots")
    assert res.status_code == 200
    assert res.json()["price_stale"] == 0
    assert res.json()["price_date"] == "2026-09-24"

    # 昨天的 updated_at → 拦
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute("UPDATE holdings SET updated_at = '2026-09-23 15:20:00' WHERE code = '600405'")
        conn.execute("DELETE FROM daily_snapshots")
        conn.commit()
    finally:
        conn.close()

    assert client.post("/snapshots").status_code == 409


def test_timeline_exposes_price_fields(client, app_module, monkeypatch):
    _today(monkeypatch, "2026-09-25")
    _seed_holdings(app_module, [("600406", 100, 8.0, 7.0, 12.0)])
    _set_price_sync_at(app_module, "2026-09-25 15:20:00")
    assert client.post("/snapshots").status_code == 200

    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        # 老快照（建列之前写的）：两列为 NULL
        conn.execute(
            "INSERT INTO daily_snapshots (date, total_assets, total_market_value, bank_balance, "
            "securities_cash, total_profit, holdings_count) VALUES ('2026-09-24', 1000, 1000, 0, 0, 0, 1)"
        )
        # force 记下来的低置信快照
        conn.execute(
            "INSERT INTO daily_snapshots (date, total_assets, total_market_value, bank_balance, "
            "securities_cash, total_profit, holdings_count, price_date, price_stale) "
            "VALUES ('2026-09-23', 900, 900, 0, 0, 0, 1, '2026-09-22', 1)"
        )
        conn.commit()
    finally:
        conn.close()

    rows = client.get("/performance/timeline").json()
    by_date = {r["date"]: r for r in rows}
    assert set(by_date) == {"2026-09-23", "2026-09-24", "2026-09-25"}
    for row in rows:
        assert "price_stale" in row
        assert "price_date" in row
    assert by_date["2026-09-25"]["price_stale"] == 0
    assert by_date["2026-09-25"]["price_date"] == "2026-09-25"
    assert by_date["2026-09-24"]["price_stale"] == 0  # 老快照回落 0
    assert by_date["2026-09-24"]["price_date"] is None
    assert by_date["2026-09-23"]["price_stale"] == 1
    assert by_date["2026-09-23"]["price_date"] == "2026-09-22"


def _settings_value(app_module, key):
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _seed_sync_holding(app_module):
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute("DELETE FROM holdings")
        conn.execute(
            "INSERT INTO holdings (code, name, category, quantity, avg_cost, diluted_cost, "
            "total_dividend, last_price) VALUES ('600407', '测试标的', 'A股权益', 100, 8, 7, 0, 12.0)"
        )
        conn.commit()
    finally:
        conn.close()


def test_price_sync_writes_last_price_sync_at_on_success(app_module, monkeypatch):
    """整批都成功才写 last_price_sync_at，格式与 holdings.updated_at 一致。"""
    from routers_holdings import _sync_prices_impl

    _seed_sync_holding(app_module)
    assert _settings_value(app_module, "last_price_sync_at") is None

    monkeypatch.setattr(
        "routers_holdings.fetch_stock_quotes",
        lambda codes: {"600407": {"price": 13.0, "source": "东方财富行情"}},
    )
    monkeypatch.setattr("kline_cache.sync_klines_for_holdings", lambda conn, *a, **k: {})

    result = _sync_prices_impl(backup=False)
    assert result["status"] == "success"
    assert result["updated"] == 1

    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        updated_at = conn.execute(
            "SELECT updated_at FROM holdings WHERE code = '600407'"
        ).fetchone()[0]
    finally:
        conn.close()
    # 与 holdings.updated_at 同一时刻、同一本地时区格式（YYYY-MM-DD HH:MM:SS）
    assert _settings_value(app_module, "last_price_sync_at") == str(updated_at)[:19]


def test_price_sync_all_failed_keeps_previous_last_price_sync_at(app_module, monkeypatch):
    """全部取不到价 → 不写 last_price_sync_at（否则闸门会以为价格是新的）。"""
    from routers_holdings import _sync_prices_impl

    _seed_sync_holding(app_module)
    _set_price_sync_at(app_module, "2026-09-01 15:20:00")

    monkeypatch.setattr("routers_holdings.fetch_stock_quotes", lambda codes: {})
    monkeypatch.setattr("routers_holdings.fetch_open_fund_nav", lambda code: None)
    monkeypatch.setattr("kline_cache.sync_klines_for_holdings", lambda conn, *a, **k: {})

    result = _sync_prices_impl(backup=False)
    assert result["status"] == "success"
    assert result["updated"] == 0
    assert result["failed"]
    assert _settings_value(app_module, "last_price_sync_at") == "2026-09-01 15:20:00"


def test_never_synced_price_blocks_with_baseline_hint(client, app_module, monkeypatch):
    """从未成功同步过价格（也没有 holdings.updated_at）→ 同样拦，提示里带日期。"""
    _today(monkeypatch, "2026-09-26")
    _seed_holdings(app_module, [("600408", 100, 8.0, 7.0, 12.0)])

    res = client.post("/snapshots")
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "2026-09-26" in detail
    assert "force=true" in detail
    assert _snapshot_rows(app_module) == []


def test_price_sync_partial_failure_does_not_mark_prices_fresh(app_module, monkeypatch):
    """部分成功（例如 8/10 取不到价）不算「价格已更新」。

    2026-09-23 的真实事故：东财实时行情接口整段不可用，10 只里只有 2 只货基
    （走天天基金）成功，旧的"至少一只成功"规则把当天标成新鲜 → 16:40 的快照
    用 09-22 的价写下了 09-23，当日收益显示 +148（真实涨跌完全没进来），
    并会污染 TWR / 今年 / 时间轴收益尺。所以收紧为「整批都成功才刷新时间戳」，
    同时把取不到价的代码记下来，让闸门提示能说清原因。
    """
    from routers_holdings import _sync_prices_impl

    _seed_sync_holding(app_module)
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO holdings (code, name, category, quantity, avg_cost, diluted_cost, "
            "total_dividend, last_price) VALUES ('f002001', '华夏成长', '债基', 1000, 1.0, 1.0, 0, 1.0)"
        )
        conn.commit()
    finally:
        conn.close()
    _set_price_sync_at(app_module, "2026-09-22 15:20:00")

    # 股票取不到价（模拟东财挂），货基正常 → 部分成功
    monkeypatch.setattr("routers_holdings.fetch_stock_quotes", lambda codes: {})
    monkeypatch.setattr("routers_holdings.fetch_open_fund_nav", lambda code: 1.10)
    monkeypatch.setattr("kline_cache.sync_klines_for_holdings", lambda conn, *a, **k: {})

    result = _sync_prices_impl(backup=False)
    assert result["status"] == "success"
    assert result["updated"] == 1                 # 货基确实更新了
    assert [f["code"] for f in result["failed"]] == ["600407"]
    # 关键：时间戳没被刷新，闸门仍会认为价格是旧的
    assert _settings_value(app_module, "last_price_sync_at") == "2026-09-22 15:20:00"
    # 失败标的被记下来，供 409 提示说明原因
    assert _settings_value(app_module, "last_price_sync_failed") == "600407"


def test_price_sync_clean_run_clears_failed_codes(app_module, monkeypatch):
    """整批成功时要清掉上一次的失败记录。"""
    from routers_holdings import _sync_prices_impl

    _seed_sync_holding(app_module)
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('last_price_sync_failed', '600999') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        "routers_holdings.fetch_stock_quotes",
        lambda codes: {"600407": {"price": 13.0, "source": "腾讯行情"}},
    )
    monkeypatch.setattr("kline_cache.sync_klines_for_holdings", lambda conn, *a, **k: {})

    result = _sync_prices_impl(backup=False)
    assert result["failed"] == []
    assert _settings_value(app_module, "last_price_sync_failed") == ""


def test_stale_detail_mentions_failed_codes(client, app_module, monkeypatch):
    """闸门的 409 文案要说清是哪些标的取不到价。"""
    _today(monkeypatch, "2026-09-26")
    _seed_holdings(app_module, [("600408", 100, 8.0, 7.0, 12.0)])
    _set_price_sync_at(app_module, "2026-09-25 15:20:00")
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('last_price_sync_failed', '600408,159352') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()
    finally:
        conn.close()

    res = client.post("/snapshots")
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "2 只取不到价" in detail
    assert "600408" in detail and "159352" in detail
