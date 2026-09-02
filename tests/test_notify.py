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
    monkeypatch.setenv("NOTIFY_FEISHU_WEBHOOK", "https://93.184.216.34/feishu")
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
        assert "93.184.216.34/feishu" in args[0]
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


def test_channel_credentials_ui_override_env(client, app_module, monkeypatch):
    """页面保存的通道密钥优先于 .env；不回填明文。"""
    from unittest.mock import patch

    monkeypatch.delenv("NOTIFY_FEISHU_WEBHOOK", raising=False)
    monkeypatch.delenv("FEISHU_ALERT_WEBHOOK", raising=False)
    monkeypatch.setenv("NOTIFY_ENABLED", "1")

    # 初始未配置
    st0 = client.get("/notify/status").json()
    assert st0["channels"]["feishu"]["configured"] is False
    assert st0["credential_flags"]["feishu_webhook"] is False

    save = client.put(
        "/notify/settings",
        json={
            "channel_credentials": {
                "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/from-ui",
            }
        },
    )
    assert save.status_code == 200
    body = save.json()
    assert body["channels"]["feishu"]["configured"] is True
    assert body["channels"]["feishu"]["source"] == "db"
    assert body["credential_flags"]["feishu_webhook"] is True
    # 状态接口不得回填明文 webhook
    assert "from-ui" not in str(body)
    assert "…" in (body["channels"]["feishu"].get("hint") or "") or body["channels"]["feishu"].get("hint") == "***"

    class FakeResp:
        status_code = 200
        text = "ok"

        def json(self):
            return {"StatusCode": 0}

    with patch("requests.post", return_value=FakeResp()) as mock_post:
        res = client.post(
            "/notify/test",
            json={"text": "hi", "channels": ["feishu"], "force": True},
        )
        assert res.status_code == 200
        assert res.json()["sent"] is True
        assert mock_post.called
        assert "from-ui" in mock_post.call_args[0][0]

    # 清除库值后回到未配置（无 env 时）
    clear = client.put(
        "/notify/settings",
        json={"channel_credentials": {"feishu_webhook": ""}},
    )
    assert clear.status_code == 200
    assert clear.json()["channels"]["feishu"]["configured"] is False
    assert clear.json()["credential_flags"]["feishu_webhook"] is False


def test_feishu_app_mode_configures_and_posts_via_api(app_module, monkeypatch):
    import notify as notify_mod  # reset token cache to keep token call count deterministic
    notify_mod._token_cache = {}
    notify_mod._token_cache_at = 0.0
    from notify import dispatch

    monkeypatch.setenv("NOTIFY_ENABLED", "1")
    for k in ("NOTIFY_FEISHU_WEBHOOK", "FEISHU_ALERT_WEBHOOK"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NOTIFY_FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("NOTIFY_FEISHU_APP_SECRET", "secret_test")
    monkeypatch.setenv("NOTIFY_FEISHU_OPEN_ID", "ou_test")
    monkeypatch.delenv("NOTIFY_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("NOTIFY_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("NOTIFY_DINGTALK_WEBHOOK", raising=False)
    monkeypatch.delenv("NOTIFY_WECOM_WEBHOOK", raising=False)

    # status（API 面向前端）反映 app 模式，且不回填 secret
    from notify import notify_status
    st = notify_status()
    assert st["channels"]["feishu"]["configured"] is True
    assert "secret_test" not in str(st)
    # 内部 config 才带 secret，仅供发送逻辑用
    from notify import channel_config
    cfg = channel_config()
    assert cfg["feishu"]["mode"] == "app"

    # 模拟 token + 消息两步；token 仅调一次（有缓存）
    class TokenResp:
        status_code = 200
        text = "token"
        def json(self):
            return {"code": 0, "tenant_access_token": "t-token"}
    class MsgResp:
        status_code = 200
        text = "msg"
        def json(self):
            return {"code": 0}

    def fake_post(url, *args, **kwargs):
        if "tenant_access_token/internal" in url:
            return TokenResp()
        assert "im/v1/messages" in url
        assert kwargs["headers"]["Authorization"] == "Bearer t-token"
        # 不泄露 secret
        assert "secret_test" not in str(kwargs["json"])
        return MsgResp()

    with patch("requests.post", side_effect=fake_post) as mock_post:
        _send = __import__("notify")._send_feishu_app
        ok, code, reason = _send(
            {"app_id": "cli_test", "app_secret": "secret_test", "open_id": "ou_test"}, "你好"
        )
        assert ok is True
        assert mock_post.called
        # token + messages 两步
        assert mock_post.call_count == 2

        with app_module.get_db_connection(app_module.DB_PATH) as conn:
            result = dispatch(
                "body", title="试推", event="test", channels=["feishu"], conn=conn, force=True
            )
            conn.commit()
    assert result["sent"] is True


def test_feishu_app_requires_all_three_fields():
    from notify import _send_feishu_app
    ok, code, reason = _send_feishu_app({}, "hi")
    assert ok is False
    assert reason == "not_configured"
    ok2, _, reason2 = _send_feishu_app(
        {"app_id": "a", "app_secret": "b", "open_id": ""}, "hi"
    )
    assert ok2 is False
    assert reason2 == "not_configured"


def test_channel_credentials_db_beats_env(app_module, monkeypatch):
    from notify import channel_config, save_channel_credentials

    monkeypatch.setenv("NOTIFY_FEISHU_WEBHOOK", "https://example.com/from-env")
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_channel_credentials(conn, {"feishu_webhook": "https://example.com/from-db"})
        conn.commit()
        cfg = channel_config(conn)
        assert cfg["feishu"]["webhook"] == "https://example.com/from-db"
        assert cfg["feishu"]["source"] == "db"
