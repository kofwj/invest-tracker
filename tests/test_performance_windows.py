"""Tests for /performance/windows 时间轴收益尺。"""
import sqlite3


def _seed(client, app_module):
    # 一笔买入 → 建立 holdings
    client.post(
        "/transactions",
        json={
            "date": "2026-01-05",
            "code": "600000",
            "name": "浦发银行",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 100,
            "price": 10,
            "amount": 1000,
            "fee": 0,
            "remark": "",
        },
    )
    # 组合外部流水：投入 10 万
    client.post(
        "/portfolio-cash-flows",
        json={"date": "2026-01-05", "flow_type": "投入", "amount": 100000, "source": "工资", "remark": ""},
    )
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("UPDATE holdings SET last_price = 12 WHERE code = '600000'")
    # 三个快照：年初(1/2)、本月(当月 2 日)、今天(当前日期由本地驱动，不依赖)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    month_snap = today.replace(day=2).isoformat()
    ytd_snap = today.replace(month=1, day=2).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO daily_snapshots (date, total_assets) VALUES (?, ?)",
        (ytd_snap, 100000),
    )
    conn.execute(
        "INSERT OR REPLACE INTO daily_snapshots (date, total_assets) VALUES (?, ?)",
        (month_snap, 108000),
    )
    conn.commit()


def test_windows_returns_five_and_uses_snapshots(client, app_module):
    _seed(client, app_module)
    res = client.get("/performance/windows")
    assert res.status_code == 200
    data = res.json()
    labels = {w["label"] for w in data}
    assert labels == {"今天", "本月", "今年", "近一年", "开仓至今"}
    # 每张卡都有 gain 字段
    for w in data:
        assert "gain" in w
        assert "gain_pct" in w or w["gain"] is None
    # 本月窗口应基于当月 2 日快照
    month = next(w for w in data if w["key"] == "month")
    assert month["start_date"] == today2(app_module)
    assert month["gain_pct"] is not None


def today2(app_module):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().replace(day=2).isoformat()


def test_windows_without_snapshot_degrades(client, app_module):
    # 不注入快照/流水，只有空库 → 不炸，返回 5 张（可能 gain 为 None）
    res = client.get("/performance/windows")
    assert res.status_code == 200
    assert len(res.json()) == 5