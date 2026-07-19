"""Multi-channel notify unit tests (no real network)."""

from unittest.mock import patch


def test_format_message_short_and_medium():
    from notify import format_message

    short = format_message(title="测试", body="第一行\n第二行", event="test", template="short")
    assert "【测试】" in short
    assert "第一行" in short
    assert "第二行" not in short

    medium = format_message(title="价格预警", body="格力到价", event="price_alert", template="medium")
    assert "invest-tracker" in medium
    assert "价格预警" in medium
    assert "格力到价" in medium


def test_dispatch_skips_when_disabled(app_module, monkeypatch):
    from notify import dispatch, save_notify_settings

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_notify_settings(conn, enabled=False)
        conn.commit()
        result = dispatch("hello", title="t", event="test", conn=conn, force=False)
        assert result["sent"] is False
        assert result["reason"] == "notify_disabled"

        # force still attempts (may fail no channels)
        result2 = dispatch("hello", title="t", event="test", conn=conn, force=True)
        assert "results" in result2


def test_dispatch_posts_to_feishu(app_module, monkeypatch):
    from notify import dispatch

    monkeypatch.setenv("NOTIFY_ENABLED", "1")
    monkeypatch.setenv("NOTIFY_FEISHU_WEBHOOK", "https://example.com/feishu")
    monkeypatch.delenv("FEISHU_ALERT_WEBHOOK", raising=False)
    monkeypatch.delenv("NOTIFY_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("NOTIFY_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("NOTIFY_DINGTALK_WEBHOOK", raising=False)
    monkeypatch.delenv("NOTIFY_WECOM_WEBHOOK", raising=False)

    class FakeResp:
        status_code = 200
        text = "ok"

        def json(self):
            return {"StatusCode": 0}

    with patch("requests.post", return_value=FakeResp()) as mock_post:
        with app_module.get_db_connection(app_module.DB_PATH) as conn:
            result = dispatch(
                "body",
                title="试推",
                event="test",
                channels=["feishu"],
                conn=conn,
                force=True,
            )
            conn.commit()
        assert result["sent"] is True
        assert mock_post.called
        args, kwargs = mock_post.call_args
        assert "example.com/feishu" in args[0]
        assert kwargs["json"]["msg_type"] == "text"


def test_deposit_due_detects_windows(app_module):
    from datetime import date, timedelta
    from notify import check_deposit_due

    today = date.today()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute("DELETE FROM deposits")
        conn.execute(
            "INSERT INTO deposits (bank_name, amount, interest_rate, due_date) VALUES (?,?,?,?)",
            ("交行", 200000, 1.3, (today - timedelta(days=2)).isoformat()),
        )
        conn.execute(
            "INSERT INTO deposits (bank_name, amount, interest_rate, due_date) VALUES (?,?,?,?)",
            ("中行", 50000, 1.0, (today + timedelta(days=5)).isoformat()),
        )
        conn.execute(
            "INSERT INTO deposits (bank_name, amount, interest_rate, due_date) VALUES (?,?,?,?)",
            ("农行", 100000, 1.9, (today + timedelta(days=20)).isoformat()),
        )
        conn.commit()
        info = check_deposit_due(conn)
        assert info["count"] == 3
        assert len(info["buckets"]["overdue"]) == 1
        assert len(info["buckets"]["d7"]) == 1
        assert len(info["buckets"]["d30"]) == 1
        assert info["has_actionable"] is True


def test_notify_api_status_and_test(client, app_module, monkeypatch):
    monkeypatch.setenv("NOTIFY_ENABLED", "1")
    status = client.get("/notify/status")
    assert status.status_code == 200
    body = status.json()
    assert "channels" in body
    assert "event_channels" in body
    assert "feishu" in body["channels"]

    # no webhook configured → sent false no_channels or all_failed
    res = client.post("/notify/test", json={"text": "hi", "channels": ["feishu"], "force": True})
    assert res.status_code == 200
    data = res.json()
    assert "results" in data

    logs = client.get("/notify/logs?limit=5")
    assert logs.status_code == 200
    assert "items" in logs.json()


def test_notify_settings_roundtrip(client):
    res = client.put(
        "/notify/settings",
        json={
            "enabled": True,
            "cooldown_minutes": 120,
            "template": "short",
            "event_channels": {"price_alert": "telegram,feishu", "deposit_due": "feishu"},
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert data["cooldown_minutes"] == 120
    assert data["template"] == "short"
    assert "telegram" in data["event_channels"]["price_alert"]


def test_legacy_feishu_env_still_configures_channel(monkeypatch):
    from notify import channel_config

    monkeypatch.delenv("NOTIFY_FEISHU_WEBHOOK", raising=False)
    monkeypatch.setenv("FEISHU_ALERT_WEBHOOK", "https://open.feishu.cn/open-apis/bot/v2/hook/legacy")
    cfg = channel_config()
    assert cfg["feishu"]["configured"] is True
