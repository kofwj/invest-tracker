"""人工填价（所有行情源都挂了时的兜底）回归测试。

真实事故：2026-09-23 东方财富实时行情接口整段不可用，10 只持仓里 8 只
"未取到有效价格"。此前用户只能 force 记一个用旧价算出来的快照（数字是错的）。
这里锁定新契约：
- PUT /holdings/{code}/price：有限正数才收（否则中文 400），code 必须存在（404）；
  写 holdings.last_price/updated_at + settings.last_price_sync_at（快照闸门放行）
  + settings.manual_price_codes（排序去重）；
- 快照落 daily_snapshots.manual_price_count（只数在持仓的、含人工价的标的，
  不阻断快照）；
- GET /performance/timeline 暴露 manual_price_count（老快照回落 0）；
- 真实行情同步成功覆盖后，自动撤掉对应 code 的「人工」标记。
"""
import math
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


def _settings_value(app_module, key):
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _holding_row(app_module, code):
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT code, quantity, last_price, updated_at FROM holdings WHERE code = ?", (code,)
        ).fetchone()
    finally:
        conn.close()


def _snapshot_row(app_module, date_iso):
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT date, manual_price_count, price_stale FROM daily_snapshots WHERE date = ?",
            (date_iso,),
        ).fetchone()
    finally:
        conn.close()


def _today(monkeypatch, day_iso):
    """固定「今天」，三处一起固定。

    - /snapshots 走 database 模块属性；
    - cron 是 import 绑定；
    - 手动填价的 PUT 用 routers_holdings 里 import 进来的 datetime.now()，
      而 /snapshots 的价格闸门读 snapshots._local_today_iso()。

    只固定前两处的话，写进库的日期（真实今天）与被当成「今天」的日期会不一致，
    闸门就误判成「价格陈旧」返回 409 —— 这个测试只在机器日期恰好等于 day_iso
    时才碰巧通过（2026-09-24 起就一直红）。
    """
    from datetime import datetime as _dt

    import database as db
    import routers_cron
    import routers_holdings
    import snapshots

    monkeypatch.setattr(db, "local_today_iso", lambda: day_iso)
    monkeypatch.setattr(routers_cron, "local_today_iso", lambda: day_iso)
    monkeypatch.setattr(snapshots, "_local_today_iso", lambda: day_iso)

    frozen = _dt.fromisoformat(f"{day_iso}T19:30:00")

    class _FrozenDatetime(_dt):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(routers_holdings, "datetime", _FrozenDatetime)


def test_manual_price_updates_holding_and_response(client, app_module, monkeypatch):
    _today(monkeypatch, "2026-09-23")
    _seed_holdings(app_module, [("600501", 100, 8.0, 7.0, 12.0)])

    res = client.put(
        "/holdings/600501/price", json={"price": 38.36, "note": "东财挂了，手动填"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["code"] == "600501"
    assert data["price"] == 38.36
    assert data["manual_price_codes"] == ["600501"]
    assert data["updated_at"].startswith("2026-09-23")
    assert set(data) == {"status", "code", "price", "updated_at", "manual_price_codes"}

    row = _holding_row(app_module, "600501")
    assert float(row["last_price"]) == 38.36
    assert str(row["updated_at"])[:10] == "2026-09-23"

    # 手动确认了今天的价 → 闸门判据看的就是这个键
    assert _settings_value(app_module, "last_price_sync_at") == data["updated_at"]


def test_manual_price_opens_snapshot_gate(client, app_module, monkeypatch):
    """手动填价后不用 force：POST /snapshots 返回 200 而不是 409。"""
    _today(monkeypatch, "2026-09-23")
    _seed_holdings(app_module, [("600502", 100, 8.0, 7.0, 0)])

    blocked = client.post("/snapshots")
    assert blocked.status_code == 409  # 从未同步过价 → 拦住

    assert client.put("/holdings/600502/price", json={"price": 9.5}).status_code == 200

    res = client.post("/snapshots")
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "created"
    assert data["price_stale"] == 0
    assert data["price_date"] == "2026-09-23"


def test_manual_price_codes_deduplicated(client, app_module, monkeypatch):
    _today(monkeypatch, "2026-09-23")
    _seed_holdings(
        app_module,
        [("600503", 100, 8.0, 7.0, 12.0), ("600504", 50, 4.0, 4.0, 5.0)],
    )

    first = client.put("/holdings/600503/price", json={"price": 13.1})
    assert first.json()["manual_price_codes"] == ["600503"]

    # 同一只再改一次：不产生重复项，值仍是最新的
    again = client.put("/holdings/600503/price", json={"price": 13.2})
    assert again.json()["manual_price_codes"] == ["600503"]
    assert _settings_value(app_module, "manual_price_codes") == "600503"
    assert float(_holding_row(app_module, "600503")["last_price"]) == 13.2

    second = client.put("/holdings/600504/price", json={"price": 6.0})
    assert second.json()["manual_price_codes"] == ["600503", "600504"]  # 保持排序
    assert _settings_value(app_module, "manual_price_codes") == "600503,600504"


def test_snapshot_records_manual_price_count_for_live_holdings_only(
    client, app_module, monkeypatch
):
    """两只人工价、其中一只已清仓（quantity=0）→ 快照只数在持仓的那只。"""
    _today(monkeypatch, "2026-09-23")
    _seed_holdings(
        app_module,
        [
            ("600505", 100, 8.0, 7.0, 0),
            ("600506", 50, 4.0, 4.0, 0),
            ("600507", 0, 3.0, 3.0, 0),
        ],
    )

    assert client.put("/holdings/600505/price", json={"price": 9.0}).status_code == 200
    assert client.put("/holdings/600507/price", json={"price": 3.3}).status_code == 200
    # 已清仓的那只也留在标记里（用户确实填过），但快照不计数
    assert _settings_value(app_module, "manual_price_codes") == "600505,600507"

    res = client.post("/snapshots")
    assert res.status_code == 200
    assert res.json()["action"] == "created"

    row = _snapshot_row(app_module, "2026-09-23")
    assert row["manual_price_count"] == 1
    # 含人工价不阻断、也不算「旧价」：不是低置信快照
    assert row["price_stale"] == 0

    # 同一天再记一次：更新分支也要刷新该计数（清仓那只被移出持仓）
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute("UPDATE holdings SET quantity = 0 WHERE code = '600505'")
        conn.commit()
    finally:
        conn.close()

    again = client.post("/snapshots")
    assert again.status_code == 200
    assert again.json()["action"] == "updated"
    assert _snapshot_row(app_module, "2026-09-23")["manual_price_count"] == 0


def test_manual_price_count_in_timeline_with_legacy_fallback(
    client, app_module, monkeypatch
):
    _today(monkeypatch, "2026-09-23")
    _seed_holdings(app_module, [("600508", 100, 8.0, 7.0, 0)])
    assert client.put("/holdings/600508/price", json={"price": 9.9}).status_code == 200
    assert client.post("/snapshots").status_code == 200

    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        # 老快照（建列之前写的）：manual_price_count 为 NULL → 读出来回落 0
        conn.execute(
            "INSERT INTO daily_snapshots (date, total_assets, total_market_value, bank_balance, "
            "securities_cash, total_profit, holdings_count) VALUES ('2026-09-22', 1000, 1000, 0, 0, 0, 1)"
        )
        conn.commit()
    finally:
        conn.close()

    rows = client.get("/performance/timeline").json()
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-09-23"]["manual_price_count"] == 1
    assert by_date["2026-09-22"]["manual_price_count"] == 0


def test_manual_price_invalid_inputs(client, app_module, monkeypatch):
    _today(monkeypatch, "2026-09-23")
    _seed_holdings(app_module, [("600509", 100, 8.0, 7.0, 12.0)])

    def _assert_400(res, bad):
        assert res.status_code == 400, bad
        detail = res.json()["detail"]
        assert isinstance(detail, str) and detail
        # 提示必须是中文（给人看的）
        assert any("\u4e00" <= ch <= "\u9fff" for ch in detail), detail

    for bad in (0, -1, -0.01, 0.0, "abc", "38.36", None, True):
        _assert_400(client.put("/holdings/600509/price", json={"price": bad}), bad)

    # JSON 规范里没有 NaN/Infinity，用裸 body 送（json.loads 能解析，
    # 必须走我们自己的 isfinite 校验而不是 pydantic 的 422）
    for raw in ('{"price": NaN}', '{"price": Infinity}', '{"price": -Infinity}'):
        _assert_400(
            client.put(
                "/holdings/600509/price",
                content=raw,
                headers={"Content-Type": "application/json"},
            ),
            raw,
        )

    _assert_400(client.put("/holdings/600509/price", json={}), {})
    # 校验失败不能动库：原价与人工标记都原样
    row = _holding_row(app_module, "600509")
    assert float(row["last_price"]) == 12.0
    assert _settings_value(app_module, "manual_price_codes") is None

    missing = client.put("/holdings/600999/price", json={"price": 1.0})
    assert missing.status_code == 404
    assert "600999" in missing.json()["detail"]


def test_successful_price_sync_clears_manual_marker(app_module, monkeypatch):
    """一次成功的同步把对应 code 从 manual_price_codes 移除（整批成功则清空）。"""
    from routers_holdings import _sync_prices_impl

    _seed_holdings(app_module, [("600510", 100, 8.0, 7.0, 0)])
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('manual_price_codes', '600510') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        "routers_holdings.fetch_stock_quotes",
        lambda codes: {"600510": {"price": 13.0, "source": "东方财富行情"}},
    )
    monkeypatch.setattr("kline_cache.sync_klines_for_holdings", lambda conn, *a, **k: {})

    result = _sync_prices_impl(backup=False)
    assert result["status"] == "success"
    assert result["failed"] == []
    assert _settings_value(app_module, "manual_price_codes") == ""
    assert float(_holding_row(app_module, "600510")["last_price"]) == 13.0


def test_partial_price_sync_keeps_marker_of_failed_code(app_module, monkeypatch):
    """部分成功：成功的 code 撤标记，取不到价那只见不到真价 → 标记保留。"""
    from routers_holdings import _sync_prices_impl

    _seed_holdings(app_module, [("600511", 100, 8.0, 7.0, 0)])
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO holdings (code, name, category, quantity, avg_cost, diluted_cost, "
            "total_dividend, last_price) VALUES ('f002001', '华夏成长', '债基', 1000, 1.0, 1.0, 0, 1.0)"
        )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('manual_price_codes', '600511,f002001') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr("routers_holdings.fetch_stock_quotes", lambda codes: {})
    monkeypatch.setattr("routers_holdings.fetch_open_fund_nav", lambda code: 1.10)
    monkeypatch.setattr("kline_cache.sync_klines_for_holdings", lambda conn, *a, **k: {})

    result = _sync_prices_impl(backup=False)
    assert [f["code"] for f in result["failed"]] == ["600511"]
    # 货基拿到真实净值 → 标记撤掉；取不到价的股票仍标着「人工」
    assert _settings_value(app_module, "manual_price_codes") == "600511"


def test_manual_price_is_finite_positive_only_via_math_module():
    """守住校验口径：nan/inf 都不算有限正数。"""
    assert not math.isfinite(float("nan"))
    assert not math.isfinite(float("inf"))
