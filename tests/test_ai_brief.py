import json
from unittest.mock import patch

from ai_payload import ALLOWED_KEYS, validate_output


def _enable_brief(conn, *, shadow=True):
    from ai_client import save_ai_config

    save_ai_config(
        conn,
        {
            "enabled": True,
            "base_url": "https://api.x.com",
            "model": "demo",
            "api_key": "sk-abcdef1234",
            "shadow_mode": shadow,
            "features": {"brief": True, "alert_note": False, "nl_rule": False},
        },
    )
    conn.commit()


def _summary():
    return {
        "holdings_day": [
            {"code": "000651", "name": "格力", "change_pct": -2.1, "day_contrib": -5000},
            {"code": "601288", "name": "农行", "change_pct": 0.4, "day_contrib": 800},
        ],
        "indices": [{"code": "000300", "name": "沪深300", "change_pct": -0.72}],
        "signals": {},
    }


def _packed(**kwargs):
    data = {
        "reasons": [{"title": "农行人事公告", "kind": "notice", "code": "601288"}],
        "moves": [],
        "reason_coverage": {"matched": 1, "window_days": 2, "note": "x"},
    }
    data.update(kwargs)
    return data


def test_disabled_byte_identical(app_module):
    from portfolio_helpers import send_evening_brief

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("notify.notify_evening_brief", return_value={"sent": False, "reason": "skip"}):
            a = send_evening_brief(conn, notify=False)
            b = send_evening_brief(conn, notify=True)
        n = conn.execute("SELECT COUNT(*) FROM ai_call_log").fetchone()[0]
    assert a["text"] == b["text"]
    assert "（今日 AI 段未生成）" not in a["text"]
    assert n == 0


def test_assemble_brief_payload_whitelist(app_module):
    from ai_brief import assemble_brief_payload

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("ai_brief.build_market_summary", return_value=_summary()), \
             patch("ai_brief._holding_price_map", return_value={}), \
             patch("ai_brief._portfolio_day_pnl", return_value={"amount": -32150}), \
             patch(
                 "ai_brief.build_discipline_report",
                 return_value={
                     "breaches": [{"level": "warning"}, {"level": "ok"}],
                     "plans": [{"title": "减仓", "remaining_amount": 50000, "level": "warning"}],
                 },
             ), \
             patch("ai_brief.reasons_for_holdings", return_value=_packed()):
            payload = assemble_brief_payload(conn, as_of="2026-09-24")
    assert set(payload) == ALLOWED_KEYS["brief"]
    assert payload["day_pnl_amount_rounded"] % 1000 == 0
    blob = json.dumps(payload, ensure_ascii=False)
    assert "remaining_amount" not in blob
    assert "total_assets" not in blob
    assert "portfolio_pct" not in blob
    assert payload["benchmark"] == {"name": "沪深300", "change_pct": -0.72}
    assert payload["discipline_breach_count"] == 1
    assert payload["movers"][0]["code"] == "000651"
    assert "contribution" not in payload["movers"][0]


def test_old_notice_stays_out_of_payload(app_module):
    from ai_brief import assemble_brief_payload

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO holdings (code, name, category, quantity, avg_cost, last_price) "
            "VALUES ('000651', '格力', 'A股权益', 100, 10, 12)"
        )
        conn.execute(
            "INSERT INTO notice_cache (code, date, title) VALUES ('000651', '2026-08-01', '旧公告')"
        )
        conn.commit()
        with patch("ai_brief.build_market_summary", return_value=_summary()), \
             patch("ai_brief._holding_price_map", return_value={}), \
             patch("ai_brief._portfolio_day_pnl", return_value={"amount": 0}), \
             patch("ai_brief.build_discipline_report", return_value={"breaches": [], "plans": []}):
            payload = assemble_brief_payload(conn, as_of="2026-09-24")
    titles = [r.get("title") for r in payload["reasons"]]
    assert "旧公告" not in titles


def test_empty_reasons_short_circuit(app_module):
    from ai_brief import EMPTY_LINE
    from portfolio_helpers import send_evening_brief

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_brief(conn, shadow=False)
        empty = {
            "as_of": "2026-09-24",
            "day_pnl_amount_rounded": 0,
            "counts": {},
            "movers": [],
            "benchmark": {},
            "discipline_breach_count": 0,
            "plans": [],
            "reasons": [],
            "moves": [],
            "reason_coverage": {},
        }
        with patch("ai_brief.assemble_brief_payload", return_value=empty), \
             patch("ai_brief.call_ai") as mock_ai, \
             patch("notify.notify_evening_brief", return_value={"sent": False}):
            result = send_evening_brief(conn, notify=True)
        assert mock_ai.call_count == 0
        assert EMPTY_LINE in result["text"]
        assert result["ai_brief"]["mode"] == "empty"


def test_empty_unfound_passes_validator():
    from ai_payload import build_payload

    payload = build_payload("brief", reasons=[], moves=[])
    r = validate_output("brief", "未找到相关公告或新闻", payload)
    assert r["ok"] is True


def test_causal_wording_blocked():
    payload = {"reasons": [{"title": "农行人事公告"}], "moves": []}
    bad = validate_output("brief", "因为人事变动导致下跌", payload)
    assert bad["ok"] is False
    assert bad["reason"] == "causal_claim"
    good = validate_output("brief", "同期有这些信息 [农行人事公告]", payload)
    assert good["ok"] is True


def test_shadow_keeps_template(app_module):
    from portfolio_helpers import send_evening_brief

    payload = {
        "as_of": "2026-09-24",
        "day_pnl_amount_rounded": -32000,
        "counts": {"up": 1, "down": 1, "flat": 0, "holdings": 2},
        "movers": [{"code": "000651", "name": "格力", "change_pct": -2.1}],
        "benchmark": {"name": "沪深300", "change_pct": -0.72},
        "discipline_breach_count": 0,
        "plans": [],
        "reasons": [{"title": "农行人事公告"}],
        "moves": [],
        "reason_coverage": {"matched": 1, "window_days": 2, "note": "x"},
    }
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_brief(conn, shadow=True)
        with patch("ai_brief.assemble_brief_payload", return_value=payload), \
             patch(
                 "ai_client.chat",
                 return_value={"ok": True, "text": "同期有这些信息 [农行人事公告]", "status": 200},
             ), \
             patch("notify.notify_evening_brief", return_value={"sent": False}) as mock_send:
            result = send_evening_brief(conn, notify=True)
        body = mock_send.call_args[0][0] if mock_send.call_count else result["text"]
        assert "农行人事公告" not in result["text"]
        assert "农行人事公告" not in str(body)
        row = conn.execute(
            "SELECT output_text, warnings_json, feature, shadow FROM ai_call_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row[2] == "brief"
        assert int(row[3] or 0) == 1
        assert "农行人事公告" in (row[0] or "")
        assert row[1] is not None


def test_timeout_falls_back_to_template(app_module):
    from portfolio_helpers import send_evening_brief

    payload = {
        "as_of": "2026-09-24",
        "day_pnl_amount_rounded": 0,
        "counts": {},
        "movers": [],
        "benchmark": {},
        "discipline_breach_count": 0,
        "plans": [],
        "reasons": [{"title": "农行人事公告"}],
        "moves": [],
        "reason_coverage": {},
    }
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_brief(conn, shadow=False)
        with patch("ai_brief.assemble_brief_payload", return_value=payload), \
             patch("ai_brief.call_ai", return_value={"ok": False, "reason": "timeout"}), \
             patch("notify.notify_evening_brief", return_value={"sent": False}):
            enabled = send_evening_brief(conn, notify=True)
        conn.execute("DELETE FROM settings WHERE key LIKE 'ai_brief_%'")
        conn.commit()
        from ai_client import save_ai_config

        save_ai_config(conn, {"enabled": False, "features": {"brief": False, "alert_note": False, "nl_rule": False}})
        conn.commit()
        with patch("notify.notify_evening_brief", return_value={"sent": False}):
            baseline = send_evening_brief(conn, notify=True)
    assert enabled["text"] == baseline["text"]
    assert "农行人事公告" not in enabled["text"]


def test_reasons_exception_still_sends(app_module):
    from ai_brief import EMPTY_LINE
    from portfolio_helpers import send_evening_brief

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_brief(conn, shadow=False)
        with patch("ai_brief.build_market_summary", return_value=_summary()), \
             patch("ai_brief._holding_price_map", return_value={}), \
             patch("ai_brief._portfolio_day_pnl", return_value={"amount": 0}), \
             patch("ai_brief.build_discipline_report", return_value={"breaches": [], "plans": []}), \
             patch("ai_brief.reasons_for_holdings", side_effect=RuntimeError("akshare down")), \
             patch("ai_brief.call_ai") as mock_ai, \
             patch("notify.notify_evening_brief", return_value={"sent": False}):
            result = send_evening_brief(conn, notify=True)
        assert mock_ai.call_count == 0
        assert EMPTY_LINE in result["text"]
        assert "【晚间简报】" in result["text"]


def test_preview_does_not_call_ai(app_module):
    from portfolio_helpers import send_evening_brief

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_brief(conn, shadow=False)
        with patch("ai_brief.call_ai") as mock_ai, \
             patch("ai_brief.assemble_brief_payload") as mock_as:
            result = send_evening_brief(conn, notify=False)
        assert mock_ai.call_count == 0
        assert mock_as.call_count == 0
        assert "（今日 AI 段未生成）" in result["text"]


def test_audit_round_trip(app_module):
    from ai_brief import generate_brief_segment

    payload = {
        "as_of": "2026-09-24",
        "day_pnl_amount_rounded": -32000,
        "counts": {},
        "movers": [],
        "benchmark": {},
        "discipline_breach_count": 0,
        "plans": [],
        "reasons": [{"title": "农行人事公告"}],
        "moves": [],
        "reason_coverage": {"matched": 1, "window_days": 2, "note": "x"},
    }
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_brief(conn, shadow=True)
        with patch("ai_brief.assemble_brief_payload", return_value=payload), \
             patch(
                 "ai_client.chat",
                 return_value={"ok": True, "text": "同期有这些信息 [农行人事公告]", "status": 200},
             ):
            rec = generate_brief_segment(conn)
        assert rec["mode"] == "ok"
        cached = conn.execute(
            "SELECT value FROM settings WHERE key LIKE 'ai_brief_%'"
        ).fetchone()
        assert cached is not None
        data = json.loads(cached[0])
        assert data["mode"] == "ok"
        assert "农行人事公告" in data["text"]
        row = conn.execute(
            "SELECT payload_json, output_text, warnings_json, feature FROM ai_call_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row[3] == "brief"
        assert "农行人事公告" in (row[1] or "")
        assert row[2] is not None


def test_call_ai_timeout_override(app_module):
    from ai_client import AiConfig, call_ai

    cfg = AiConfig(
        enabled=True,
        base_url="https://api.x.com",
        api_key="sk-abcdef1234",
        model="demo",
        timeout_seconds=8,
        shadow_mode=True,
        daily_call_cap=30,
        features={"brief": True, "alert_note": False, "nl_rule": False},
    )
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("ai_client.chat", return_value={"ok": True, "text": "pong", "status": 200}) as mock_chat:
            call_ai(
                conn,
                cfg,
                "brief",
                [{"role": "user", "content": "hi"}],
                timeout_seconds=20,
            )
            used = mock_chat.call_args[0][0]
            assert used.timeout_seconds == 20


def test_clip_brief_text_sentence_boundary():
    from ai_brief import clip_brief_text

    over = "前一句。" + ("后" * 200)
    clipped = clip_brief_text(over)
    assert clipped.endswith("。")
    assert len(clipped) <= 200
    assert clip_brief_text("x" * 201) == ""


def test_corrupt_cache_preview_does_not_500(app_module):
    from cash import set_setting
    from database import local_today_iso
    from portfolio_helpers import send_evening_brief

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_brief(conn, shadow=False)
        set_setting(conn, "ai_brief_" + local_today_iso(), "{broken")
        conn.commit()
        with patch("ai_brief.call_ai") as mock_ai:
            result = send_evening_brief(conn, notify=False)
        assert mock_ai.call_count == 0
        assert "（今日 AI 段未生成）" in result["text"]
        assert "【晚间简报】" in result["text"]


def test_non_shadow_appends_segment(app_module):
    from portfolio_helpers import send_evening_brief

    payload = {
        "as_of": "2026-09-24",
        "day_pnl_amount_rounded": -32000,
        "counts": {},
        "movers": [],
        "benchmark": {},
        "discipline_breach_count": 0,
        "plans": [],
        "reasons": [{"title": "农行人事公告"}],
        "moves": [],
        "reason_coverage": {},
    }
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_brief(conn, shadow=False)
        with patch("ai_brief.assemble_brief_payload", return_value=payload), \
             patch(
                 "ai_client.chat",
                 return_value={"ok": True, "text": "同期有这些信息 [农行人事公告]", "status": 200},
             ), \
             patch("notify.notify_evening_brief", return_value={"sent": False}):
            result = send_evening_brief(conn, notify=True)
        assert "同期有这些信息 [农行人事公告]" in result["text"]
        assert "【晚间简报】" in result["text"]


def test_counts_use_full_holding_map_not_top20(app_module):
    from ai_brief import assemble_brief_payload

    holding_map = {}
    for i in range(25):
        code = "%06d" % i
        if i < 12:
            chg = 1.0
        elif i < 24:
            chg = -1.0
        else:
            chg = None
        holding_map[code] = {
            "code": code,
            "name": code,
            "change_pct": chg,
            "quantity": 100,
            "price": 10,
            "prev_close": 9,
        }
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("ai_brief.build_market_summary", return_value=_summary()), \
             patch("ai_brief._holding_price_map", return_value=holding_map), \
             patch("ai_brief._portfolio_day_pnl", return_value={"amount": 0}), \
             patch("ai_brief.build_discipline_report", return_value={"breaches": [], "plans": []}), \
             patch("ai_brief.reasons_for_holdings", return_value=_packed()):
            payload = assemble_brief_payload(conn, as_of="2026-09-24")
    assert payload["counts"]["holdings"] == 25
    assert payload["counts"]["up"] == 12
    assert payload["counts"]["down"] == 12
    assert payload["counts"]["flat"] == 0


def test_empty_cache_expired_semantics():
    from datetime import datetime

    from ai_brief import empty_cache_expired

    rec = {"mode": "empty", "generated_at": "2026-09-24 15:20:00"}
    assert empty_cache_expired(rec, now=datetime(2026, 9, 24, 15, 30)) is False
    assert empty_cache_expired(rec, now=datetime(2026, 9, 24, 16, 50)) is True
    rec2 = {"mode": "empty", "generated_at": "2026-09-24 16:45:00"}
    assert empty_cache_expired(rec2, now=datetime(2026, 9, 24, 17, 0)) is False
    rec3 = {"mode": "ok", "generated_at": "2026-09-24 15:20:00"}
    assert empty_cache_expired(rec3, now=datetime(2026, 9, 24, 16, 50)) is False


def test_empty_cache_regenerates_after_refill(app_module):
    from ai_brief import EMPTY_LINE, generate_brief_segment, write_brief_cache
    from database import local_today_iso

    payload = {
        "as_of": "2026-09-24",
        "day_pnl_amount_rounded": 0,
        "counts": {},
        "movers": [],
        "benchmark": {},
        "discipline_breach_count": 0,
        "plans": [],
        "reasons": [{"title": "农行人事公告"}],
        "moves": [],
        "reason_coverage": {},
    }
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_brief(conn, shadow=False)
        write_brief_cache(
            conn,
            {"mode": "empty", "text": EMPTY_LINE, "generated_at": "2026-09-24 15:20:00"},
            as_of=local_today_iso(),
        )
        conn.commit()
        with patch("ai_brief.empty_cache_expired", return_value=True), \
             patch("ai_brief.assemble_brief_payload", return_value=payload), \
             patch(
                 "ai_client.chat",
                 return_value={"ok": True, "text": "同期有这些信息 [农行人事公告]", "status": 200},
             ):
            rec = generate_brief_segment(conn)
        assert rec["mode"] == "ok"
        assert "农行人事公告" in rec["text"]


def test_shadow_preview_adds_hint(app_module):
    from ai_brief import SHADOW_HINT, write_brief_cache
    from database import local_today_iso
    from portfolio_helpers import send_evening_brief

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable_brief(conn, shadow=True)
        write_brief_cache(
            conn,
            {"mode": "ok", "text": "同期有这些信息 [农行人事公告]"},
            as_of=local_today_iso(),
        )
        conn.commit()
        result = send_evening_brief(conn, notify=False)
    assert SHADOW_HINT in result["text"]
    assert "农行人事公告" in result["text"]


def test_now_local_follows_app_timezone_not_container_tz(monkeypatch):
    import os
    import time
    from datetime import datetime

    from ai_brief import LOCAL_TZ, _now_local, _record, empty_cache_expired

    old_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "UTC")
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        expected = datetime.now(LOCAL_TZ).replace(tzinfo=None)
        local = _now_local()
        assert abs((local - expected).total_seconds()) < 1
        rec = _record(mode="empty")
        got = datetime.strptime(rec["generated_at"], "%Y-%m-%d %H:%M:%S")
        assert abs((got - expected).total_seconds()) < 2
        shanghai_1645 = datetime.now(LOCAL_TZ).replace(
            hour=16, minute=45, second=0, microsecond=0
        ).replace(tzinfo=None)
        empty = {
            "mode": "empty",
            "generated_at": shanghai_1645.replace(hour=15, minute=20).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }
        assert empty_cache_expired(empty, now=shanghai_1645) is True
        utc_naive = datetime.utcnow()
        assert empty_cache_expired(empty, now=utc_naive.replace(
            year=shanghai_1645.year, month=shanghai_1645.month, day=shanghai_1645.day,
            hour=8, minute=45, second=0, microsecond=0,
        )) is False
    finally:
        if old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_tz
        if hasattr(time, "tzset"):
            time.tzset()


def test_prompt_forbids_flat_when_counts_zero():
    from ai_brief import SYSTEM_PROMPT

    assert "缺行情不是平盘" in SYSTEM_PROMPT
