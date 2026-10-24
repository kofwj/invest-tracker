"""总资产 / 净值校准（账实平差）的回归测试。

核心不变量：**校准后看板的总资产就等于用户填的实测总资产**，而且反复校准不会漂。
第二条：平差是一个独立可见的数（``total_assets_adjustment``），不藏进持仓或现金分项里。
"""
import sqlite3

import pytest


def _set_base_cash(app_module, amount):
    conn = sqlite3.connect(app_module.DB_PATH)
    app_module.set_setting(conn, "securities_cash", amount)
    app_module.set_setting(conn, "securities_cash_base", amount)
    conn.commit()
    conn.close()


def test_calibration_absorbs_gap_into_visible_adjustment(client, app_module):
    _set_base_cash(app_module, 10000)

    before = client.get("/dashboard").json()
    assert before["total_assets"] == 10000.0
    assert before["total_assets_adjustment"] == 0.0

    resp = client.post(
        "/snapshots/reconcile/apply",
        json={"manual_total_assets": 12500, "note": "券商 App 实盘"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["gap"] == 2500.0
    assert result["adjustment_after"] == 2500.0
    assert result["total_assets"] == 12500.0

    after = client.get("/dashboard").json()
    # 分项一个都没动，差额只体现在平差这一行上
    assert after["securities_cash"] == 10000.0
    assert after["total_assets_adjustment"] == 2500.0
    assert after["total_assets"] == 12500.0


def test_recalibration_converges_without_drift(client, app_module):
    _set_base_cash(app_module, 10000)
    client.post("/snapshots/reconcile/apply", json={"manual_total_assets": 12500})

    # 再对着「已含平差的显示值」校准同一个数：差额必须是 0，平差不再累加
    again = client.post("/snapshots/reconcile/apply", json={"manual_total_assets": 12500})
    assert again.status_code == 200
    body = again.json()
    assert body["gap"] == 0.0
    assert body["adjustment_after"] == 2500.0
    assert body["total_assets"] == 12500.0

    # 负数差额能把平差吃回去（实盘比账面少）
    shrink = client.post("/snapshots/reconcile/apply", json={"manual_total_assets": 9800})
    assert shrink.status_code == 200
    assert shrink.json()["gap"] == -2700.0
    assert shrink.json()["adjustment_after"] == -200.0
    assert client.get("/dashboard").json()["total_assets"] == 9800.0


def test_calibration_status_reports_days_and_last_gap(client, app_module):
    _set_base_cash(app_module, 10000)
    empty = client.get("/snapshots/reconcile/total-assets").json()
    assert empty["has_history"] is False
    assert empty["level"] == "never"
    assert empty["stale_days"] == 30

    client.post("/snapshots/reconcile/apply", json={"manual_total_assets": 10250})
    status = client.get("/snapshots/reconcile/total-assets").json()
    assert status["has_history"] is True
    assert status["days_since"] == 0
    assert status["level"] == "ok"
    assert status["last_gap"] == 250.0
    assert status["last_manual_total_assets"] == 10250.0
    assert "今天校准过" in status["hint"]
    assert "+250.00" in status["hint"]

    # dashboard 里带同一份状态，前端不用再多打一个请求
    assert client.get("/dashboard").json()["calibration"]["has_history"] is True


def test_calibration_status_levels_use_stale_threshold(app_module):
    """距上次校准 30 天开始提醒，60 天以上算彻底逾期。"""
    import total_asset_calibration as calibration
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    calibration.ensure_total_asset_calibration_table(conn)
    conn.execute(
        """INSERT INTO total_asset_calibrations
           (date, manual_total_assets, displayed_total_assets, gap, adjustment_after, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("2026-01-01", 1000.0, 900.0, 100.0, 100.0, ""),
    )
    conn.commit()

    assert calibration.calibration_status(conn, "2026-01-11")["level"] == "ok"
    due = calibration.calibration_status(conn, "2026-01-31")
    assert due["level"] == "due"
    assert due["days_since"] == 30
    assert "距上次校准 30 天" in due["hint"]
    assert calibration.calibration_status(conn, "2026-03-05")["level"] == "overdue"
    conn.close()


def test_apply_calibration_rejects_non_finite(app_module):
    import total_asset_calibration as calibration
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    for bad in (float("inf"), float("nan")):
        with pytest.raises(ValueError):
            calibration.apply_calibration(conn, bad, displayed_total_assets=0.0)
    conn.close()


def test_schema_version_reaches_total_asset_calibration(app_module):
    import schema as schema_module

    assert schema_module.SCHEMA_VERSION >= 22
    conn = sqlite3.connect(app_module.DB_PATH)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='total_asset_calibrations'"
    ).fetchone()
    conn.close()
    assert row is not None
