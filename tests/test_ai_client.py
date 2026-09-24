from unittest.mock import patch

from ai_client import (
    AiConfig,
    ai_available,
    ai_budget_ok,
    call_ai,
    chat,
    load_ai_config,
    mask_key,
    normalize_chat_url,
    save_ai_config,
)


def _cfg(**kwargs):
    data = dict(
        enabled=True,
        base_url="https://api.x.com",
        api_key="sk-abcdef1234",
        model="demo",
        timeout_seconds=8,
        shadow_mode=True,
        daily_call_cap=30,
        features={"brief": False, "alert_note": False, "nl_rule": False},
    )
    data.update(kwargs)
    return AiConfig(**data)


def test_ai_available_false_when_unconfigured():
    cfg = load_ai_config(None)
    assert ai_available(cfg) is False


def test_call_ai_unconfigured_does_not_request(app_module):
    cfg = _cfg(enabled=False, api_key="", base_url="", model="")
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("ai_client._post_chat") as mock_post:
            result = call_ai(conn, cfg, "brief", [{"role": "user", "content": "hi"}])
            assert mock_post.call_count == 0
        assert result["ok"] is False
        assert result["reason"] == "disabled"
        n = conn.execute("SELECT COUNT(*) FROM ai_call_log").fetchone()[0]
        assert n == 0


def test_normalize_chat_url_forms():
    cases = [
        ("https://api.x.com", "https://api.x.com/v1/chat/completions"),
        ("https://api.x.com/v1", "https://api.x.com/v1/chat/completions"),
        ("https://api.x.com/v1/", "https://api.x.com/v1/chat/completions"),
        ("https://api.x.com/v1/chat/completions", "https://api.x.com/v1/chat/completions"),
        ("https://api.x.com/openai/v1", "https://api.x.com/openai/v1/chat/completions"),
    ]
    for raw, expected in cases:
        assert normalize_chat_url(raw) == expected


def test_chat_error_shapes_never_raise():
    cfg = _cfg()
    g = chat.__globals__
    with patch.dict(g, {"_post_chat": lambda *a, **k: (400, "bad")}):
        r = chat(cfg, [{"role": "user", "content": "x"}])
        assert r["ok"] is False and r["status"] == 400
    with patch.dict(g, {"_post_chat": lambda *a, **k: (500, "err")}):
        r = chat(cfg, [{"role": "user", "content": "x"}])
        assert r["ok"] is False and r["status"] == 500

    def _timeout(*a, **k):
        raise TimeoutError("t")

    with patch.dict(g, {"_post_chat": _timeout}):
        r = chat(cfg, [{"role": "user", "content": "x"}])
        assert r["ok"] is False and r["reason"] == "timeout"
    with patch.dict(g, {"_post_chat": lambda *a, **k: (200, "not-json")}):
        r = chat(cfg, [{"role": "user", "content": "x"}])
        assert r["ok"] is False and r["reason"] == "invalid_json"
    with patch.dict(g, {"_post_chat": lambda *a, **k: (200, '{"choices":[]}')}):
        r = chat(cfg, [{"role": "user", "content": "x"}])
        assert r["ok"] is False and r["reason"] == "empty_choices"


def test_mask_key():
    assert mask_key("") == ""
    assert mask_key("short") == "****"
    assert mask_key("sk-abcdef1234") == "sk-****1234"
    assert "abcd" not in mask_key("sk-abcdef1234")


def test_save_ai_config_empty_key_keeps_existing(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_ai_config(conn, {"api_key": "sk-secret9999", "model": "m1", "base_url": "https://api.x.com"})
        conn.commit()
        save_ai_config(conn, {"api_key": "", "model": "m2"})
        conn.commit()
        cfg = load_ai_config(conn)
        assert cfg.api_key == "sk-secret9999"
        assert cfg.model == "m2"


def test_ai_budget_ok(app_module):
    from database import local_today_iso

    cfg = _cfg(daily_call_cap=1)
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        assert ai_budget_ok(conn, cfg) is True
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) VALUES (?, 'brief', 1)",
            (local_today_iso() + " 12:00:00",),
        )
        conn.commit()
        assert ai_budget_ok(conn, cfg) is False

def test_ai_status_hides_plaintext_key(client, app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_ai_config(conn, {"api_key": "sk-supersecret9999", "enabled": True, "base_url": "https://api.x.com", "model": "m"})
        conn.commit()
    res = client.get("/ai/status")
    assert res.status_code == 200
    body = res.json()
    dumped = str(body)
    assert "sk-supersecret9999" not in dumped
    assert "api_key_masked" in body
    assert body.get("api_key") in (None, body.get("api_key_masked"))


def test_call_ai_disabled_skips_audit(app_module):
    cfg = _cfg(enabled=False)
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("ai_client._post_chat") as mock_post:
            r = call_ai(conn, cfg, "brief", [{"role": "user", "content": "hi"}])
            assert mock_post.call_count == 0
        assert r == {"ok": False, "reason": "disabled", "status": None}
        assert conn.execute("SELECT COUNT(*) FROM ai_call_log").fetchone()[0] == 0


def test_ai_test_echoes_request_url(client, app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_ai_config(conn, {
            "enabled": True,
            "base_url": "https://api.x.com",
            "model": "demo",
            "api_key": "sk-abcdef1234",
        })
        conn.commit()
    with patch("ai_client._post_chat", return_value=(200, '{"choices":[{"message":{"content":"pong"}}],"usage":{"total_tokens":3}}')):
        res = client.post("/ai/test")
    assert res.status_code == 200
    data = res.json()
    assert data["request_url"] == "https://api.x.com/v1/chat/completions"
    assert data["ok"] is True
    assert data["model"] == "demo"


def test_call_ai_feature_disabled(app_module):
    cfg = _cfg(enabled=True)
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("ai_client._post_chat") as mock_post:
            r = call_ai(conn, cfg, "brief", [{"role": "user", "content": "hi"}])
            assert mock_post.call_count == 0
        assert r["ok"] is False
        assert r["reason"] == "feature_disabled"
        assert conn.execute("SELECT COUNT(*) FROM ai_call_log").fetchone()[0] == 0


def test_call_ai_test_skips_feature_flag(app_module):
    from ai_client import call_ai as call_ai_now

    cfg = _cfg(enabled=True)
    payload = '{"choices":[{"message":{"content":"pong"}}],"usage":{"total_tokens":1}}'
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("ai_client._post_chat", return_value=(200, payload)) as mock_post:
            r = call_ai_now(conn, cfg, "test", [{"role": "user", "content": "ping"}])
            assert mock_post.call_count == 1
        assert r["ok"] is True


def test_ai_budget_ignores_test_and_failures(app_module):
    from database import local_today_iso

    cfg = _cfg(daily_call_cap=1)
    day = local_today_iso() + " 12:00:00"
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) VALUES (?, 'test', 1)",
            (day,),
        )
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) VALUES (?, 'brief', 0)",
            (day,),
        )
        conn.commit()
        assert ai_budget_ok(conn, cfg) is True
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) VALUES (?, 'brief', 1)",
            (day,),
        )
        conn.commit()
        assert ai_budget_ok(conn, cfg) is False


def test_call_ai_budget_writes_audit(app_module):
    from database import local_today_iso

    cfg = _cfg(
        daily_call_cap=1,
        features={"brief": True, "alert_note": False, "nl_rule": False},
    )
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) VALUES (?, 'brief', 1)",
            (local_today_iso() + " 12:00:00",),
        )
        conn.commit()
        with patch("ai_client._post_chat") as mock_post:
            r = call_ai(conn, cfg, "brief", [{"role": "user", "content": "hi"}])
            assert mock_post.call_count == 0
        assert r["reason"] == "budget"
        n = conn.execute(
            "SELECT COUNT(*) FROM ai_call_log WHERE reason = 'budget'"
        ).fetchone()[0]
        assert n == 1


def test_save_ai_config_clear_api_key(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_ai_config(conn, {"api_key": "sk-secret9999", "model": "m1"})
        conn.commit()
        save_ai_config(conn, {"clear_api_key": True})
        conn.commit()
        cfg = load_ai_config(conn)
        assert cfg.api_key == ""



def test_save_ai_config_clear_api_key_ignores_env(app_module, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "sk-fromenv-9999")
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_ai_config(conn, {"api_key": "sk-inui-8888"})
        conn.commit()
        save_ai_config(conn, {"clear_api_key": True})
        conn.commit()
        cfg = load_ai_config(conn)
        assert cfg.api_key == ""


def test_ai_status_today_used_matches_budget(client, app_module):
    from database import local_today_iso

    day = local_today_iso() + " 12:00:00"
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) VALUES (?, 'test', 1)",
            (day,),
        )
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) VALUES (?, 'brief', 0)",
            (day,),
        )
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) VALUES (?, 'brief', 1)",
            (day,),
        )
        conn.commit()
    body = client.get("/ai/status").json()
    assert body["today_calls"] == 3
    assert body["today_used"] == 1



def test_ai_status_get_does_not_purge_old_log(client, app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) "
            "VALUES ('2026-01-01 12:00:00', 'brief', 1)"
        )
        conn.commit()
    assert client.get("/ai/status").status_code == 200
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        n = conn.execute("SELECT COUNT(*) FROM ai_call_log").fetchone()[0]
        assert n == 1


def test_purge_ai_call_log_needs_commit(app_module):
    from ai_client import purge_ai_call_log
    from database import db_session

    with db_session() as conn:
        conn.execute(
            "INSERT INTO ai_call_log (created_at, feature, ok) "
            "VALUES ('2026-01-01 12:00:00', 'brief', 1)"
        )
        conn.commit()
    with db_session() as conn:
        purge_ai_call_log(conn, as_of="2026-09-24")
    with db_session() as conn:
        n = conn.execute("SELECT COUNT(*) FROM ai_call_log").fetchone()[0]
        assert n == 1
        purge_ai_call_log(conn, as_of="2026-09-24")
        conn.commit()
    with db_session() as conn:
        n = conn.execute("SELECT COUNT(*) FROM ai_call_log").fetchone()[0]
        assert n == 0



def test_post_chat_sends_real_user_agent(monkeypatch):
    """供应方前面常挂 Cloudflare：默认 UA `Python-urllib/x.y` 会被 CF 1010 判 403。"""
    import ai_client

    seen = {}

    class _Resp:
        status = 200

        def read(self):
            return b'{"choices":[]}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _Resp()

    monkeypatch.setattr(ai_client.urllib.request, "urlopen", fake_urlopen)
    status, _raw = ai_client._post_chat(
        "https://api.x.com/v1/chat/completions", "sk-abcdef1234", {"model": "m"}, 8
    )
    assert status == 200
    assert seen["headers"]["user-agent"] == ai_client.USER_AGENT
    assert "urllib" not in seen["headers"]["user-agent"].lower()
    assert seen["headers"]["accept"] == "application/json"


def test_provider_error_shapes():
    import ai_client

    assert ai_client._provider_error('{"error":{"message":"Model not found","type":"x"}}') == "Model not found"
    assert ai_client._provider_error('{"error":"Service temporarily unavailable"}') == "Service temporarily unavailable"
    assert ai_client._provider_error("error code: 1010") == "error code: 1010"
    assert ai_client._provider_error("<html><h1>403 Forbidden</h1></html>") == "403 Forbidden"
    assert ai_client._provider_error("") == ""


def test_chat_surfaces_provider_error():
    import json as _json

    body = _json.dumps({"error": {"message": 'Model "Grok 4.6" is not supported', "type": "model_not_found"}})
    with patch.dict(chat.__globals__, {"_post_chat": lambda *a, **k: (404, body)}):
        r = chat(_cfg(), [{"role": "user", "content": "x"}])
    assert r["ok"] is False
    assert r["status"] == 404
    assert r["provider_error"] == 'Model "Grok 4.6" is not supported'
    assert r["reason"] == 'http_404: Model "Grok 4.6" is not supported'


def test_normalize_models_url():
    import ai_client

    assert ai_client.normalize_models_url("https://api.x.com") == "https://api.x.com/v1/models"
    assert ai_client.normalize_models_url("https://api.x.com/v1") == "https://api.x.com/v1/models"
    assert ai_client.normalize_models_url("https://api.x.com/v1/chat/completions") == "https://api.x.com/v1/models"
    assert ai_client.normalize_models_url("") == ""


def test_fetch_models_parses_ids():
    import ai_client

    body = '{"data":[{"id":"grok-4.6","display_name":"Grok 4.6"},{"id":"gpt-4o-mini"},{"no_id":1}]}'
    with patch("ai_client._get_raw", return_value=(200, body)):
        out = ai_client.fetch_models(_cfg())
    assert out["ok"] is True
    assert out["ids"] == ["gpt-4o-mini", "grok-4.6"]
    assert out["display"] == {"grok-4.6": "Grok 4.6"}
    assert out["request_url"] == "https://api.x.com/v1/models"


def test_fetch_models_error_paths():
    import ai_client

    with patch("ai_client._get_raw", return_value=(403, "error code: 1010")):
        out = ai_client.fetch_models(_cfg())
    assert out["ok"] is False and out["status"] == 403 and out["error"] == "error code: 1010"
    with patch("ai_client._get_raw", side_effect=TimeoutError("t")):
        assert ai_client.fetch_models(_cfg())["error"] == "timeout"
    with patch("ai_client._get_raw", side_effect=RuntimeError("boom")):
        assert ai_client.fetch_models(_cfg())["error"] == "boom"
    with patch("ai_client._get_raw", return_value=(200, "not-json")):
        assert ai_client.fetch_models(_cfg())["error"] == "invalid_json"
    assert ai_client.fetch_models(_cfg(base_url=""))["error"] == "base_url 未配置"
    assert ai_client.fetch_models(_cfg(api_key=""))["error"] == "api_key 未配置"


def test_ai_models_endpoint(client, app_module):
    with patch(
        "routers_ai.fetch_models",
        return_value={"ok": True, "request_url": "u", "status": 200,
                      "ids": ["grok-4.6"], "display": {}, "error": ""},
    ):
        res = client.get("/ai/models")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True and body["ids"] == ["grok-4.6"]


def test_ai_test_surfaces_provider_error(client, app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_ai_config(conn, {"enabled": True, "base_url": "https://api.x.com", "model": "m",
                              "api_key": "sk-abcdef1234"})
        conn.commit()
    with patch("ai_client._post_chat", return_value=(403, "error code: 1010")):
        res = client.post("/ai/test")
    body = res.json()
    assert body["ok"] is False
    assert body["status"] == 403
    assert body["provider_error"] == "error code: 1010"
    assert body["reason"].startswith("http_403")
