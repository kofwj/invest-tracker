"""Tests for 逐日收益：/performance/timeline 的 daily_change / daily_pct / days_gap。

用户诉求「看不到每天的收益情况」的底层依据：一天一行，且当天收益必须剔除
外部转入/转出，否则一次大额入金会被当成“今天赚了这么多”。
"""
import sqlite3


def _seed_snapshots(app_module, rows):
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    for date_iso, total_assets in rows:
        conn.execute(
            "INSERT OR REPLACE INTO daily_snapshots (date, total_assets) VALUES (?, ?)",
            (date_iso, total_assets),
        )
    conn.commit()
    conn.close()


def _seed_flow(client, date_iso, flow_type, amount):
    res = client.post(
        "/portfolio-cash-flows",
        json={"date": date_iso, "flow_type": flow_type, "amount": amount, "source": "测试", "remark": ""},
    )
    assert res.status_code == 200, res.text


def test_timeline_exposes_daily_change(client, app_module):
    _seed_snapshots(app_module, [("2026-03-02", 100000), ("2026-03-03", 103000), ("2026-03-04", 101500)])

    res = client.get("/performance/timeline")
    assert res.status_code == 200
    rows = res.json()
    assert [r["date"] for r in rows] == ["2026-03-02", "2026-03-03", "2026-03-04"]

    first, second, third = rows
    # 第一行没有前一日基准
    assert first["prev_date"] is None
    assert first["daily_change"] is None
    assert first["daily_pct"] is None
    assert first["days_gap"] is None

    assert second["prev_date"] == "2026-03-02"
    assert second["daily_change"] == 3000.0
    assert second["daily_pct"] == 3.0
    assert second["days_gap"] == 1

    assert third["daily_change"] == -1500.0
    assert third["daily_pct"] == round(-1500 / 103000 * 100, 2)


def test_daily_change_excludes_external_cash_flow(client, app_module):
    """当天转入 5 万不能算成收益：资产 +5 万，收益应为 0。"""
    _seed_snapshots(app_module, [("2026-03-02", 100000), ("2026-03-03", 150000)])
    _seed_flow(client, "2026-03-03", "投入", 50000)

    rows = client.get("/performance/timeline").json()
    day = rows[-1]
    assert day["total_assets"] == 150000
    assert day["daily_change"] == 0.0
    assert day["daily_pct"] == 0.0


def test_daily_change_excludes_withdrawal(client, app_module):
    """取出 2 万、同时赚了 1000 → 净变动 -19000 里只有 +1000 算收益。"""
    _seed_snapshots(app_module, [("2026-03-02", 100000), ("2026-03-03", 81000)])
    _seed_flow(client, "2026-03-03", "取出", 20000)

    day = client.get("/performance/timeline").json()[-1]
    assert day["daily_change"] == 1000.0
    assert day["daily_pct"] == 1.0


def test_days_gap_flags_missing_snapshots(client, app_module):
    """快照断档时 days_gap > 1，前端据此说明这一格跨了几天。"""
    _seed_snapshots(app_module, [("2026-03-02", 100000), ("2026-03-06", 104000)])

    day = client.get("/performance/timeline").json()[-1]
    assert day["days_gap"] == 4
    assert day["daily_change"] == 4000.0


def test_timeline_empty_without_snapshots(client):
    res = client.get("/performance/timeline")
    assert res.status_code == 200
    assert res.json() == []


def test_windows_report_stale_days(client, app_module):
    """今天窗口的基准快照距今多久必须能看出来，否则旧基准会被当成“今天的收益”。"""
    _seed_snapshots(app_module, [("2026-03-02", 100000)])

    data = client.get("/performance/windows").json()
    today = next(w for w in data if w["key"] == "today")
    assert today["start_date"] == "2026-03-02"
    assert today["stale_days"] is not None
    assert today["stale_days"] > 1
    # 每个窗口都有 stale_days 字段（缺快照时为空）
    for w in data:
        assert "stale_days" in w
