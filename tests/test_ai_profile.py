import importlib
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from ai_payload import ALLOWED_KEYS, build_payload, validate_output


def _profile():
    return importlib.import_module("ai_profile")


def _enable_profile(conn):
    from ai_client import save_ai_config

    save_ai_config(
        conn,
        {
            "enabled": True,
            "base_url": "https://api.x.com",
            "model": "demo",
            "api_key": "sk-abcdef1234",
            "shadow_mode": False,
            "features": {"profile_digest": True},
        },
    )
    conn.commit()


def _fundamental(period="2026-06-30"):
    return {
        "code": "600519",
        "report_period": period,
        "sections": [
            {"key": "profit", "label": "盈利", "items": [{"label": "ROE", "value": 12.3, "status": "ok"}]},
            {"key": "leverage", "label": "杠杆", "items": [{"label": "资产负债率", "value": 45.0, "status": "ok"}]},
            {"key": "cash", "label": "现金", "items": [{"label": "现金/净利润", "value": 1.2, "status": "ok"}]},
            {"key": "valuation", "label": "估值", "items": [{"label": "PE", "value": 20.0, "status": "ok"}]},
        ],
    }


def _extras():
    return {
        "profile": {"name": "测试公司", "industry": "制造业"},
        "dividends": [{"report": "2025-12", "desc": "10派10元", "ex_date": "2026-06-10"}],
        "dividend_summary": {"per10_12m": 10, "count": 1, "newest": "2026-06-10"},
    }


def _snapshot(period="2026-06-30", asset_kind="a_share_equity"):
    return {
        **_fundamental(period),
        "asset_kind": asset_kind,
        "period_kind": "report_period" if period else "as_of",
        "as_of": "2026-09-26",
        "information_complete": True,
        "metrics": [{"label": "ROE", "value": 12.3}],
        "profile": {},
        "dividends": [],
        "dividend_summary": {},
    }


def _ai_result(text="盈利能力和现金质量较稳定。"):
    return {"ok": True, "text": text, "audit_id": None, "tokens": 5}


def test_profile_payload_exact_keys_and_advice_validation():
    payload = build_payload(
        "profile_digest",
        code="600519",
        asset_kind="a_share_equity",
        report_period="2026-06-30",
        period_kind="report_period",
        as_of="2026-09-26",
        metrics=[{"label": "ROE", "value": 12.3, "secret": "drop"}],
        profile={"name": "测试", "market_value": 100000000},
        information_complete=True,
    )
    assert set(payload) == ALLOWED_KEYS["profile_digest"]
    assert "market_value" not in json.dumps(payload, ensure_ascii=False)
    assert validate_output("profile_digest", "建议买入", payload)["ok"] is False


def test_report_period_and_as_of_fallback(app_module):
    mod = _profile()
    with patch.object(mod, "build_fundamental_check", return_value=_fundamental("2026-06-30")), patch.object(
        mod, "build_company_extras", return_value=_extras()
    ):
        snap = mod.build_profile_snapshot("600519", asset_kind="stock")
    assert snap["report_period"] == "2026-06-30"
    assert snap["period_kind"] == "report_period"

    with patch.object(mod, "build_fundamental_check", return_value=_fundamental(None)), patch.object(
        mod, "build_company_extras", return_value=_extras()
    ), patch.object(mod, "local_today_iso", return_value="2026-09-26"):
        snap = mod.build_profile_snapshot("600519", asset_kind="stock")
    assert snap["report_period"] == "2026-09-26"
    assert snap["period_kind"] == "as_of"


def test_disabled_does_not_call_sources_or_model(app_module):
    mod = _profile()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch.object(mod, "build_profile_snapshot") as snapshot, patch.object(mod, "call_ai") as call:
            result = mod.generate_profile_digest(conn, "600519")
    assert result["mode"] == "feature_disabled"
    assert snapshot.call_count == 0
    assert call.call_count == 0


def test_empty_data_fixed_text_no_model_or_success_cache(app_module):
    mod = _profile()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_profile(conn)
        with patch.object(mod, "build_profile_snapshot", return_value=None), patch.object(mod, "call_ai") as call:
            result = mod.generate_profile_digest(conn, "600519")
        assert result["mode"] == "empty"
        assert result["text"] == mod.INSUFFICIENT_TEXT
        assert call.call_count == 0
        rows = conn.execute("SELECT key FROM settings WHERE key LIKE 'ai_profile_digest_%'").fetchall()
    assert rows == []


def test_same_period_cache_seven_days_and_refresh(app_module):
    mod = _profile()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_profile(conn)
        with patch.object(mod, "build_profile_snapshot", return_value=_snapshot()), patch.object(
            mod, "call_ai", return_value=_ai_result()
        ) as call:
            first = mod.generate_profile_digest(conn, "600519", asset_kind="stock")
            second = mod.generate_profile_digest(conn, "600519", asset_kind="stock")
            assert first["mode"] == "ok"
            assert second.get("cached") is True
            assert call.call_count == 1
            refreshed = mod.generate_profile_digest(conn, "600519", asset_kind="stock", refresh=True)
            assert refreshed["mode"] == "ok"
            assert call.call_count == 2

        key = mod.profile_cache_key("600519", "2026-06-30", "stock")
        raw = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()[0]
        record = json.loads(raw)
        assert {"code", "report_period", "period_kind", "as_of", "text", "mode", "created_at"}.issubset(record)


def test_cache_expired_after_seven_days(app_module):
    mod = _profile()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_profile(conn)
        with patch.object(mod, "build_profile_snapshot", return_value=_snapshot()), patch.object(
            mod, "call_ai", return_value=_ai_result()
        ) as call:
            mod.generate_profile_digest(conn, "600519")
            key = mod.profile_cache_key("600519", "2026-06-30", "a_share_equity")
            old = json.loads(conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()[0])
            old["created_at"] = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps(old), key))
            mod.generate_profile_digest(conn, "600519")
    assert call.call_count == 2


def test_same_code_different_asset_kind_not_shared(app_module):
    mod = _profile()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_profile(conn)
        with patch.object(mod, "build_profile_snapshot", side_effect=lambda code, asset_kind=None: _snapshot(asset_kind=asset_kind)), patch.object(
            mod, "call_ai", return_value=_ai_result()
        ) as call:
            mod.generate_profile_digest(conn, "600519", asset_kind="stock")
            mod.generate_profile_digest(conn, "600519", asset_kind="fund")
    assert call.call_count == 2
    assert mod.profile_cache_key("600519", "2026-06-30", "stock") != mod.profile_cache_key("600519", "2026-06-30", "fund")


def test_timeout_is_not_cached(app_module):
    mod = _profile()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_profile(conn)
        with patch.object(mod, "build_profile_snapshot", return_value=_snapshot()), patch.object(
            mod, "call_ai", return_value={"ok": False, "reason": "timeout", "text": ""}
        ) as call:
            first = mod.generate_profile_digest(conn, "600519")
            second = mod.generate_profile_digest(conn, "600519")
        assert first["mode"] == "timeout"
        assert second["mode"] == "timeout"
        assert call.call_count == 2
        rows = conn.execute("SELECT key FROM settings WHERE key LIKE 'ai\\_profile\\_digest\\_%' ESCAPE '\\'").fetchall()
    assert rows == []


def test_blocked_cache_expires_in_ten_minutes(app_module):
    mod = _profile()
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_profile(conn)
        with patch.object(mod, "build_profile_snapshot", return_value=_snapshot()), patch.object(
            mod, "call_ai", return_value={"ok": False, "reason": "provider", "text": ""}
        ) as call:
            first = mod.generate_profile_digest(conn, "600519")
            second = mod.generate_profile_digest(conn, "600519")
            assert first["mode"] == "blocked"
            assert second.get("cached") is True
            assert call.call_count == 1
            key = mod.profile_cache_key("600519", "2026-06-30", "a_share_equity")
            old = json.loads(conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()[0])
            old["created_at"] = (datetime.now() - timedelta(minutes=11)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps(old), key))
            mod.generate_profile_digest(conn, "600519")
    assert call.call_count == 2


def test_system_prompt_uses_shared_advice_terms(app_module):
    from ai_payload import TRADE_ADVICE_TERMS

    mod = _profile()
    for term in TRADE_ADVICE_TERMS:
        assert term in mod.SYSTEM_PROMPT
    assert not hasattr(mod, "TRADE_ADVICE_TERMS")
