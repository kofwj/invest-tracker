"""A4 价格预警附言（`alert_note`）的测试。

覆盖细则 §2.8 的 10 条，外加一条注入点集成测试：**附言只是附加**，AI 关着时推送文本
必须与改动前的模板逐字节一致（这条是 A4 的红线，因为它碰的是预警主链路）。
"""
import json
import sqlite3
from contextlib import contextmanager
from unittest.mock import patch

from ai_payload import ALLOWED_KEYS


def _enable(conn, *, shadow=False, features=None):
    from ai_client import save_ai_config

    save_ai_config(
        conn,
        {
            "enabled": True,
            "base_url": "https://api.x.com",
            "model": "demo",
            "api_key": "sk-abcdef1234",
            "shadow_mode": shadow,
            "features": features if features is not None else {"alert_note": True},
        },
    )
    conn.commit()


def _trigger(rule_id=1, **over):
    item = {
        "rule_id": rule_id,
        "rule_type": "change_pct",
        "target_type": "holding",
        "code": "000651",
        "name": "格力电器",
        "condition": "below",
        "threshold": -2.0,
        "price": 60.0,
        "value": -2.1,
        "change_pct": -2.1,
        "prev_close": 61.0,
        "message": "格力电器(000651) 现价 60.0000 跌破阈值 -2.0000，涨跌 -2.10%",
        "trigger_time": "2026-09-26 10:00:00",
    }
    item.update(over)
    return item


def _ok(text):
    return {"ok": True, "text": text, "audit_id": 1, "duration_ms": 5, "status": 200}


@contextmanager
def _offline():
    """隔离行情与原因缓存：测试里不打网络、不依赖当日真实数据。"""
    with patch("ai_alert._holding_price_map", return_value={}), \
        patch("ai_alert._portfolio_day_pnl", return_value={"amount": -32000, "change_pct": -1.2}), \
        patch(
            "ai_alert.build_market_summary",
            return_value={"indices": [{"code": "000300", "change_pct": -0.72}]},
        ), \
        patch("ai_alert.reasons_for_holdings", return_value={"reasons": [], "moves": []}), \
        patch("ai_alert._reason_holding_codes", return_value=[]):
        yield


def _payload_from(call) -> dict:
    """从 mock 的调用参数里取出真正发给模型的那份 payload。"""
    messages = call.args[3]
    return json.loads(messages[1]["content"])


def test_switch_off_skips_call(app_module):
    """关总开关 / 关 alert_note → 空附言且不发请求。"""
    from ai_alert import build_alert_note
    from ai_client import save_ai_config

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_ai_config(conn, {"enabled": True, "features": {"alert_note": False}})
        conn.commit()
        with patch("ai_alert.call_ai") as mock_call:
            assert build_alert_note(conn, [_trigger()]) == ""
            assert mock_call.call_count == 0

        save_ai_config(conn, {"enabled": False, "features": {"alert_note": True}})
        conn.commit()
        with patch("ai_alert.call_ai") as mock_call:
            assert build_alert_note(conn, [_trigger()]) == ""
            assert mock_call.call_count == 0


def test_note_returned_and_payload_whitelist(app_module):
    """正常出附言；payload 键集合 == 白名单，且不含金额/组合百分比/持仓数值。"""
    from ai_alert import build_alert_note

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_alert.call_ai", return_value=_ok("格力电器今天跌幅超过阈值。")) as mock_call:
            note = build_alert_note(conn, [_trigger()])
        assert mock_call.call_count == 1
        payload = _payload_from(mock_call.call_args)

    assert note == "格力电器今天跌幅超过阈值。"
    assert set(payload) == ALLOWED_KEYS["alert_note"]
    dumped = json.dumps(payload, ensure_ascii=False)
    for leaked in ("day_pnl", "total_assets", "portfolio_pct", "quantity", "avg_cost", "-32000"):
        assert leaked not in dumped
    # 组合只给方向词，不给数字
    assert payload["portfolio_direction"] == "down"
    assert payload["trigger"]["rule"] == "change_pct"


def test_payload_peers_benchmark_and_direction(app_module):
    from ai_alert import assemble_alert_payload

    holding_map = {
        "000651": {"code": "000651", "name": "格力电器", "change_pct": -2.1},
        "513530": {"code": "513530", "name": "港股通红利ETF", "change_pct": -2.6},
        "510880": {"code": "510880", "name": "红利ETF华泰柏瑞", "change_pct": -1.84},
        "600028": {"code": "600028", "name": "中国石化", "change_pct": None},
    }
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with _offline(), patch("ai_alert._holding_price_map", return_value=holding_map), \
            patch("ai_alert._portfolio_day_pnl", return_value={"amount": -32000, "change_pct": 0.0}):
            payload = assemble_alert_payload(conn, _trigger())

    # 排除自己、缺涨跌幅的跳过、按 |涨跌幅| 降序、最多 3 个
    assert [p["code"] for p in payload["peers"]] == ["513530", "510880"]
    assert payload["benchmark"] == {"name": "沪深300", "change_pct": -0.72}
    assert payload["portfolio_direction"] == "flat"


def test_same_rule_same_day_calls_once(app_module):
    from ai_alert import build_alert_note

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_alert.call_ai", return_value=_ok("格力电器今天跌幅超过阈值。")) as mock_call:
            first = build_alert_note(conn, [_trigger()])
            second = build_alert_note(conn, [_trigger()])

    assert mock_call.call_count == 1
    assert first == second == "格力电器今天跌幅超过阈值。"


def test_shadow_mode_audits_but_returns_empty(app_module):
    """影子模式：真调模型、真写审计，但**不进推送**。"""
    from ai_alert import build_alert_note

    provider = '{"choices":[{"message":{"content":"格力电器今天跌幅超过阈值。"}}],"usage":{"total_tokens":9}}'
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn, shadow=True)
        with _offline(), patch("ai_client._post_chat", return_value=(200, provider)) as mock_post:
            note = build_alert_note(conn, [_trigger()])
        rows = conn.execute(
            "SELECT feature, shadow, ok FROM ai_call_log WHERE feature = 'alert_note'"
        ).fetchall()

    assert note == ""  # 影子模式不附言
    assert mock_post.call_count == 1  # 但确实调用过
    assert len(rows) == 1 and rows[0][1] == 1 and rows[0][2] == 1


def test_failure_and_timeout_return_empty_and_cached(app_module):
    from ai_alert import build_alert_note

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch(
            "ai_alert.call_ai", return_value={"ok": False, "reason": "timeout", "status": None}
        ):
            assert build_alert_note(conn, [_trigger()]) == ""
        # 失败当天也落缓存：同一条规则同日不再戳第二次（保护额度与推送延迟）
        with _offline(), patch("ai_alert.call_ai") as mock_call:
            assert build_alert_note(conn, [_trigger()]) == ""
            assert mock_call.call_count == 0


def test_per_run_limit(app_module):
    from ai_alert import build_alert_note

    triggers = [_trigger(rule_id=i, code="00000%d" % i, name="标的%d" % i) for i in (1, 2, 3)]
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_alert.call_ai", return_value=_ok("标的今天跌幅超过阈值。")) as mock_call:
            note = build_alert_note(conn, triggers)
        assert mock_call.call_count == 3
        assert len(note.split("\n")) == 3

    # 换成另一批规则号：同一天同一规则命中上面的缓存就不再调用（这本身也是要的行为）
    more = [_trigger(rule_id=i, code="00000%d" % i, name="标的%d" % i) for i in (4, 5, 6)]
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_alert.NOTE_PER_RUN_LIMIT", 2), patch(
            "ai_alert.call_ai", return_value=_ok("标的今天跌幅超过阈值。")
        ) as mock_call:
            note = build_alert_note(conn, more)
        assert mock_call.call_count == 2
        assert len(note.split("\n")) == 2


def test_daily_limit_stops_calls(app_module):
    from ai_alert import NOTE_DAILY_LIMIT, build_alert_note
    from database import local_today_iso

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        stamp = local_today_iso() + " 09:00:00"
        for _ in range(NOTE_DAILY_LIMIT):
            conn.execute(
                "INSERT INTO ai_call_log (created_at, feature, ok) VALUES (?, 'alert_note', 1)",
                (stamp,),
            )
        conn.commit()
        with _offline(), patch("ai_alert.call_ai") as mock_call:
            assert build_alert_note(conn, [_trigger()]) == ""
            assert mock_call.call_count == 0


def test_duplicate_rule_and_missing_rule_id(app_module):
    from ai_alert import build_alert_note

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        dup = [_trigger(rule_id=7), _trigger(rule_id=7, code="600028", name="中国石化")]
        with _offline(), patch("ai_alert.call_ai", return_value=_ok("格力电器今天跌幅超过阈值。")) as mock_call:
            build_alert_note(conn, dup)
        assert mock_call.call_count == 1  # 同一 rule_id 只处理一次

        broken = _trigger()
        broken.pop("rule_id")
        with _offline(), patch("ai_alert.call_ai") as mock_call:
            assert build_alert_note(conn, [broken]) == ""
            assert mock_call.call_count == 0  # 缺 rule_id：不调 AI、不写缓存


def test_causal_sentence_blocked_in_strict_mode(app_module):
    from ai_alert import build_alert_note

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_alert.call_ai", return_value=_ok("因为格力发布公告，所以股价下跌。")):
            assert build_alert_note(conn, [_trigger()]) == ""

        # 影子模式下不拦，但要留下 warning（warnings 通过审计回写）
        _enable(conn, shadow=True)
        with _offline(), patch("ai_alert.call_ai", return_value=_ok("因为格力发布公告，所以股价下跌。")):
            assert build_alert_note(conn, [_trigger()]) == ""


def test_empty_reasons_yields_fixed_line(app_module):
    """窗口内没有条目时，模型给固定句就照用（空分支是合法输出）。"""
    from ai_alert import build_alert_note

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_alert.call_ai", return_value=_ok("同期未找到相关公告或新闻")):
            note = build_alert_note(conn, [_trigger()])

    assert note == "同期未找到相关公告或新闻。"


def test_check_alerts_injects_note_only_when_ai_on(app_module, client, monkeypatch):
    """注入点集成：AI 关着时推送文本逐字节不变；开着时附言追加在模板之后。"""
    import notify

    client.post(
        "/transactions",
        json={
            "date": "2026-01-02",
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
    raw = sqlite3.connect(app_module.DB_PATH)
    raw.execute("UPDATE holdings SET last_price = 9.7 WHERE code = '600000'")
    raw.commit()
    raw.close()

    def fake_quotes(codes, secid_map=None, use_cache=True):
        out = {}
        for code in codes:
            key = str(code).strip()
            if key == "600000":
                out[key] = {"price": 9.7, "prev_close": 10.0, "change_pct": -3.0, "name": "浦发银行"}
            elif key == "000300":
                out[key] = {"price": 3800.0, "prev_close": 3819.0, "change_pct": -0.5, "name": "沪深300"}
            else:
                out[key] = {"price": 100.0, "change_pct": 0.0, "name": key}
        return out

    monkeypatch.setattr("market.fetch_eastmoney_quotes", fake_quotes)
    monkeypatch.setattr("price_sync.fetch_eastmoney_quotes", fake_quotes)

    created = client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "name": "浦发银行",
            "condition": "below",
            "threshold": -2.0,
            "rule_type": "change_pct",
        },
    )
    assert created.status_code == 200

    sent = []
    monkeypatch.setattr(notify, "dispatch", lambda text, **kw: (sent.append(text), {"sent": True})[1])

    # ① AI 关着（默认）：推送文本 == 纯模板
    first = client.post("/market/alerts/check", json={"notify": True, "respect_cooldown": False}).json()
    assert first["trigger_count"] == 1
    template = notify.build_price_alert_text(first["triggered"])
    assert sent[-1] == template

    # ② 开 AI 用例：附言追加在模板之后（清掉升级式基线，让同一规则能再触发一次）
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        conn.execute("DELETE FROM alert_events")
        conn.commit()
    with patch("ai_alert.call_ai", return_value=_ok("浦发银行今天跌幅超过阈值。")) as mock_call:
        second = client.post("/market/alerts/check", json={"notify": True, "respect_cooldown": False}).json()
    assert second["trigger_count"] == 1
    assert mock_call.call_count == 1
    assert sent[-1] == template + "\n浦发银行今天跌幅超过阈值。"


def test_feishu_alias_path_also_gets_note(app_module, monkeypatch):
    """第二个推送出口（webhook/legacy 分支）也必须带上附言。"""
    import notify
    from market import notify_feishu_alerts

    sent = []
    monkeypatch.setattr(notify, "dispatch", lambda text, **kw: (sent.append(text), {"sent": True})[1])

    notify_feishu_alerts([_trigger()], note="格力电器今天跌幅超过阈值。")

    assert sent, "应当走 dispatch 出口"
    assert sent[-1].endswith("格力电器今天跌幅超过阈值。")
    assert "格力电器(000651)" in sent[-1]  # 原模板仍在前面


def test_note_cache_purge_actually_deletes_old_keys(app_module):
    """LIKE 少了 ESCAPE 就一行都匹配不到、清理永不生效（settings 会无限长）。"""
    from datetime import date, timedelta

    from ai_alert import note_cache_key, write_note_cache
    from database import local_today_iso

    today = local_today_iso()
    old = (date.fromisoformat(today) - timedelta(days=31)).isoformat()

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        write_note_cache(conn, {"mode": "ok", "text": "旧附言。"}, as_of=old, rule_id=1)
        conn.commit()
        before = conn.execute(
            "SELECT COUNT(*) FROM settings WHERE key = ?", (note_cache_key(old, 1),)
        ).fetchone()[0]
        # 再写一条今天的 → 触发清理，31 天前那条必须被删掉
        write_note_cache(conn, {"mode": "ok", "text": "新附言。"}, as_of=today, rule_id=2)
        conn.commit()
        after = conn.execute(
            "SELECT COUNT(*) FROM settings WHERE key = ?", (note_cache_key(old, 1),)
        ).fetchone()[0]
        fresh = conn.execute(
            "SELECT COUNT(*) FROM settings WHERE key = ?", (note_cache_key(today, 2),)
        ).fetchone()[0]

    assert before == 1
    assert after == 0
    assert fresh == 1


def test_reasons_scoped_to_the_trigger_holding(app_module):
    """附言只投喂这条预警那**一个**标的的原因条目，别拿别的持仓的公告解释它。"""
    from ai_alert import assemble_alert_payload

    captured = {}

    def _fake_reasons(conn, codes, *, as_of):
        captured["codes"] = list(codes)
        return {"reasons": [], "moves": []}

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with _offline(), patch("ai_alert.reasons_for_holdings", side_effect=_fake_reasons):
            assemble_alert_payload(conn, _trigger(code="000651"))
        assert captured["codes"] == ["000651"]

        # 组合规则没有单一标的 → "整个持仓"才是相关范围
        with _offline(), patch("ai_alert._reason_holding_codes", return_value=["000651", "600028"]), patch(
            "ai_alert.reasons_for_holdings", side_effect=_fake_reasons
        ):
            assemble_alert_payload(
                conn,
                _trigger(code="PORTFOLIO", rule_type="portfolio_pnl", target_type="portfolio"),
            )
        assert captured["codes"] == ["000651", "600028"]


def test_run_budget_stops_generating(app_module):
    """一轮检查给附言的总预算：超了就停；已有缓存的条目仍然要贴上（缓存是"免费"的）。"""
    from ai_alert import build_alert_note, write_note_cache
    from database import local_today_iso

    triggers = [_trigger(rule_id=1), _trigger(rule_id=2, code="600028", name="中国石化")]
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_alert.NOTE_RUN_BUDGET_S", 0), patch("ai_alert.call_ai") as mock_call:
            assert build_alert_note(conn, triggers) == ""
            assert mock_call.call_count == 0

        write_note_cache(
            conn,
            {"mode": "ok", "text": "格力电器今天跌幅超过阈值。"},
            as_of=local_today_iso(),
            rule_id=1,
        )
        conn.commit()
        with _offline(), patch("ai_alert.NOTE_RUN_BUDGET_S", 0), patch("ai_alert.call_ai") as mock_call:
            note = build_alert_note(conn, triggers)
            assert mock_call.call_count == 0

    assert note == "格力电器今天跌幅超过阈值。"
