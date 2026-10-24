"""流水线心跳（dead-man switch）的回归测试。

不变量：
1. 只有 ``ok=True`` 才刷新 ``last_ok_at`` —— 失败必须让「最后一次成功」继续变旧，
   否则「一直在失败」看起来跟「一直在成功」一模一样。
2. 逾期（含「从来没成功过」）会走 notify 的 ops 事件，且通知本身炸了不能带挂调用方。
3. 外部 ping 只在成功时发；没配 URL 就是安静跳过，不发、不报错。
"""
import sqlite3
from datetime import datetime, timedelta

import pytest


def _conn(app_module):
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn


def test_record_heartbeat_only_refreshes_last_ok(app_module):
    import heartbeat

    conn = _conn(app_module)
    now = datetime(2026, 1, 10, 9, 0, 0)
    heartbeat.record_heartbeat(conn, "backup", ok=True, detail="daily", at=now)
    conn.commit()

    status = heartbeat.heartbeat_status(conn, now=now, jobs=["backup"])
    row = next(r for r in status["jobs"] if r["job"] == "backup")
    assert row["level"] == "ok"
    assert row["overdue"] is False
    assert row["last_ok_at"].startswith("2026-01-10 09:00:00")
    assert row["max_age_hours"] == 30
    assert status["ok"] is True

    # 12 小时后又跑了一次但失败：last_ok_at 不能动，失败原因要留痕
    later = now + timedelta(hours=12)
    heartbeat.record_heartbeat(conn, "backup", ok=False, detail="disk full", at=later)
    conn.commit()
    row = next(
        r
        for r in heartbeat.heartbeat_status(conn, now=later, jobs=["backup"])["jobs"]
        if r["job"] == "backup"
    )
    assert row["last_ok_at"].startswith("2026-01-10 09:00:00")
    assert row["last_run_at"].startswith("2026-01-10 21:00:00")
    assert row["last_detail"] == "disk full"
    assert row["level"] == "ok"
    conn.close()


def test_heartbeat_levels_follow_max_age_thresholds(app_module):
    import heartbeat

    conn = _conn(app_module)
    start = datetime(2026, 1, 10, 2, 15, 0)
    heartbeat.record_heartbeat(conn, "backup", ok=True, at=start)
    conn.commit()

    # 30h 阈值：23h 还是 ok，24h（正好 80%）进 due，31h 就是 overdue。
    # 只看 backup 一条，另两条从没上报过会一直是 never，会把 overdue 列表弄长。
    def status_after(hours):
        return heartbeat.heartbeat_status(
            conn, now=start + timedelta(hours=hours), jobs=["backup"]
        )

    assert status_after(23)["jobs"][0]["level"] == "ok"
    assert status_after(24)["jobs"][0]["level"] == "due"
    due = status_after(25)
    assert due["jobs"][0]["level"] == "due"
    assert due["overdue"] == []
    gone = status_after(31)
    assert gone["jobs"][0]["level"] == "overdue"
    assert gone["overdue"] == ["backup"]
    assert gone["ok"] is False
    conn.close()


def test_never_reported_job_counts_as_overdue(app_module):
    """新装完忘配 crontab：没有 last_ok_at 也必须能被喊出来。"""
    import heartbeat

    conn = _conn(app_module)
    status = heartbeat.heartbeat_status(conn)
    assert status["ok"] is False
    assert "backup" in status["overdue"]
    assert all(row["level"] == "never" for row in status["jobs"])
    conn.close()


def test_check_heartbeats_marks_missing_job_once(app_module, monkeypatch):
    import heartbeat
    import notify

    conn = _conn(app_module)
    heartbeat.record_heartbeat(conn, "backup", ok=True)
    heartbeat.record_heartbeat(conn, "sync_prices", ok=True)
    conn.commit()

    calls = []

    def fake_dispatch(**kwargs):
        calls.append(kwargs)
        return {"sent": True, "channels": ["feishu"]}

    monkeypatch.setattr(notify, "dispatch", fake_dispatch)

    # 快照从来没成功过 → 只有它逾期；「没有记录」不能等于「没事」
    result = heartbeat.check_heartbeats(conn)
    assert result["overdue"] == ["snapshot"]
    assert result["notified"] is True
    text = result["text"]
    assert "日终快照" in text
    assert "还没有任何成功记录" in text
    assert calls and calls[0]["event"] == "ops"

    # 补上快照的成功记录 → 归于安静
    heartbeat.record_heartbeat(conn, "snapshot", ok=True)
    conn.commit()
    assert heartbeat.check_heartbeats(conn)["notified"] is False



def test_check_heartbeats_survives_notify_failure(app_module, monkeypatch):
    import heartbeat
    import notify

    conn = _conn(app_module)
    heartbeat.record_heartbeat(conn, "backup", ok=True, at=datetime(2026, 1, 1, 0, 0, 0))
    conn.commit()

    def boom(**kwargs):
        raise RuntimeError("webhook down")

    monkeypatch.setattr(notify, "dispatch", boom)
    result = heartbeat.check_heartbeats(conn, now=datetime(2026, 3, 1, 0, 0, 0))
    assert "backup" in result["overdue"]
    assert result["notified"] is False
    assert "webhook down" in result["notify_error"]
    conn.close()


def test_ping_external_is_skipped_when_unconfigured_and_on_failure(monkeypatch):
    import heartbeat

    monkeypatch.delenv("HEARTBEAT_BACKUP_URL", raising=False)
    assert heartbeat.ping_external("backup") == {
        "pinged": False,
        "reason": "not_configured",
        "job": "backup",
    }

    # 失败时刻意不 ping：让外部 dead-man 超时后自己报警
    assert heartbeat.ping_external("backup", ok=False, url="https://hc-ping.com/x")["reason"] == "failure_left_silent"


def test_ping_external_swallows_network_errors(monkeypatch):
    import heartbeat

    def boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(heartbeat.urllib.request, "urlopen", boom)
    result = heartbeat.ping_external("backup", url="https://hc-ping.com/abc123")
    assert result["pinged"] is False
    assert result["reason"] == "request_failed"
    assert "connection refused" in result["error"]
    # 日志/返回值里不能出现 check 的 UUID
    assert "abc123" not in result["target"]


def test_cron_heartbeat_endpoint_records_and_validates(client, app_module, monkeypatch):
    import heartbeat

    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    headers = {"X-Cron-Token": "correct-cron-token"}

    # 没 token 的 cron 路由一律拒绝，心跳也不例外
    assert client.post("/cron/heartbeat", json={"job": "backup"}).status_code == 401

    resp = client.post(
        "/cron/heartbeat",
        json={"job": "backup", "ok": True, "detail": "daily"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["job"] == "backup"
    conn = _conn(app_module)
    row = next(r for r in heartbeat.heartbeat_status(conn)["jobs"] if r["job"] == "backup")
    assert row["level"] == "ok"
    assert row["last_detail"] == "daily"
    conn.close()

    assert client.post("/cron/heartbeat", json={"job": "  "}, headers=headers).status_code == 400


def test_maintenance_status_exposes_heartbeats(client):
    body = client.get("/maintenance/status").json()
    assert "heartbeats" in body
    jobs = {row["job"] for row in body["heartbeats"]["jobs"]}
    assert {"backup", "sync_prices", "snapshot"} <= jobs


def test_notify_events_reports_heartbeat_block(client, monkeypatch):
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    body = client.post(
        "/cron/notify-events",
        json={"force": False},
        headers={"X-Cron-Token": "correct-cron-token"},
    ).json()
    assert "heartbeat" in body
    assert isinstance(body["heartbeat"]["overdue"], list)


@pytest.mark.parametrize("job", ["backup", "sync_prices", "snapshot"])
def test_job_specs_have_labels_and_thresholds(job):
    import heartbeat

    spec = heartbeat._spec(job)
    assert spec["label"] != job
    assert spec["max_age_hours"] > 0
