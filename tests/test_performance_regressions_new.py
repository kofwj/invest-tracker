import sqlite3


def _seed_snapshots(app_module, rows):
    conn = sqlite3.connect(app_module.DB_PATH)
    for day, assets in rows:
        conn.execute(
            "INSERT OR REPLACE INTO daily_snapshots (date, total_assets) VALUES (?, ?)",
            (day, assets),
        )
    conn.commit()
    conn.close()


def _seed_flow(client, day, flow_type, amount):
    response = client.post(
        "/portfolio-cash-flows",
        json={"date": day, "flow_type": flow_type, "amount": amount},
    )
    assert response.status_code == 200, response.text


def test_summary_end_date_uses_historical_assets_and_period(client, app_module):
    _seed_snapshots(
        app_module,
        [("2026-01-01", 100000), ("2026-02-01", 110000), ("2026-03-01", 120000)],
    )
    _seed_flow(client, "2026-02-15", "投入", 5000)

    response = client.get(
        "/performance/summary",
        params={"start_date": "2026-01-01", "end_date": "2026-02-01"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["as_of_date"] == "2026-02-01"
    assert body["total_assets"] == 110000
    assert body["period_gain"] == 10000
    assert body["flow_count"] == 0


def test_timeline_end_date_filters_snapshots_and_flows(client, app_module):
    _seed_snapshots(
        app_module,
        [("2026-01-01", 100000), ("2026-02-01", 110000), ("2026-03-01", 120000)],
    )
    _seed_flow(client, "2026-03-01", "投入", 10000)

    response = client.get(
        "/performance/timeline",
        params={"start_date": "2026-01-01", "end_date": "2026-02-01"},
    )
    assert response.status_code == 200, response.text
    assert [row["date"] for row in response.json()] == ["2026-01-01", "2026-02-01"]


def test_monthly_stats_excludes_external_flow(client, app_module):
    _seed_snapshots(app_module, [("2026-01-30", 1000), ("2026-02-28", 1500)])
    _seed_flow(client, "2026-02-15", "投入", 500)

    response = client.get("/performance/summary")
    assert response.status_code == 200, response.text
    monthly = response.json()["monthly_stats"]
    assert monthly["best_month"] == 0
    assert monthly["worst_month"] == 0
    assert monthly["avg_monthly"] == 0


# ---------------------------------------------------------------- 同日流水与快照的先后

def test_flow_is_after_snapshot_uses_created_at_on_same_day():
    """同一天的流水算不算「快照之后」，由 created_at 决定（日期粒度本身无法区分）。"""
    from performance import _flow_is_after_snapshot

    snap = {"date": "2026-09-25", "created_at": "2026-09-25 15:20:00"}
    # 同日、流水在快照之前 → 快照已含这笔，不能再从收益里扣
    assert _flow_is_after_snapshot({"date": "2026-09-25", "created_at": "2026-09-25 09:00:00"}, snap) is False
    # 同日、流水在快照之后（晚上又转进来一笔）→ 必须扣，否则会被算成收益
    assert _flow_is_after_snapshot({"date": "2026-09-25", "created_at": "2026-09-25 20:00:00"}, snap) is True
    # 同一秒：边界按「已包含」处理
    assert _flow_is_after_snapshot({"date": "2026-09-25", "created_at": "2026-09-25 15:20:00"}, snap) is False
    # 跨日不看 created_at
    assert _flow_is_after_snapshot({"date": "2026-09-26", "created_at": "2026-09-26 09:00:00"}, snap) is True
    assert _flow_is_after_snapshot({"date": "2026-09-24", "created_at": "2026-09-24 23:00:00"}, snap) is False
    # ISO "T" 分隔 + 微秒也要能比（库里写回是空格分隔，但调用方不一定）
    assert _flow_is_after_snapshot({"date": "2026-09-25", "created_at": "2026-09-25T20:00:00.123456"}, snap) is True


def test_flow_is_after_snapshot_falls_back_when_created_at_missing():
    """老数据缺 created_at 时按旧口径（同日算后续现金流），不能静默变成「不算」。"""
    from performance import _flow_is_after_snapshot

    snap = {"date": "2026-09-25", "created_at": "2026-09-25 15:20:00"}
    assert _flow_is_after_snapshot({"date": "2026-09-25"}, snap) is True
    assert _flow_is_after_snapshot({"date": "2026-09-25", "created_at": None}, snap) is True
    assert _flow_is_after_snapshot({"date": "2026-09-25", "created_at": ""}, snap) is True
    # 快照那一侧缺 created_at 也回退
    assert _flow_is_after_snapshot(
        {"date": "2026-09-25", "created_at": "2026-09-25 20:00:00"},
        {"date": "2026-09-25"},
    ) is True


def _seed_flow_with_created_at(app_module, *, day, amount, created_at, flow_type="投入"):
    """直接写库：接口不允许指定 created_at，但同日先后的判定正依赖它。"""
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute(
        "INSERT INTO portfolio_cash_flows (date, flow_type, amount, created_at) VALUES (?, ?, ?, ?)",
        (day, flow_type, amount, created_at),
    )
    conn.commit()
    conn.close()


def _ytd_gain(client):
    rows = client.get("/performance/windows").json()
    return next(row for row in rows if row["key"] == "ytd")["gain"]


def test_ytd_window_ignores_snapshot_same_day_flow_by_created_at(client, app_module):
    """今年窗口：当天先在 15:20 落了快照、晚上 20:00 才转入的钱，不能被算成收益。"""
    from database import local_today_iso

    day = local_today_iso()[:4] + "-01-01"          # 今年 1 月 1 日 = ytd 窗口起点
    _seed_snapshots(app_module, [(day, 100000)])
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE daily_snapshots SET created_at = ? WHERE date = ?", (f"{day} 15:20:00", day))
    conn.commit()
    conn.close()

    _seed_flow_with_created_at(app_module, day=day, amount=5000, created_at=f"{day} 09:00:00")
    before_snapshot = _ytd_gain(client)             # 流水早于快照 → 视为快照已包含 → 不扣

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE portfolio_cash_flows SET created_at = ?", (f"{day} 20:00:00",))
    conn.commit()
    conn.close()
    after_snapshot = _ytd_gain(client)              # 流水晚于快照 → 扣掉这 5000

    assert before_snapshot is not None
    assert after_snapshot == before_snapshot - 5000
