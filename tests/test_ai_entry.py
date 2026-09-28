import json
import re
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
            "features": features if features is not None else {"nl_entry": True},
        },
    )
    conn.commit()


def _seed(conn, *, code="510880", name="红利ETF华泰柏瑞"):
    conn.execute(
        "INSERT INTO holdings (code, name, category, quantity, avg_cost, last_price) VALUES (?,?,?,?,?,?)",
        (code, name, "ETF", 1000, 1.5, 1.8),
    )
    conn.commit()


def _mock_model(body):
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return {"ok": True, "text": text, "audit_id": 1, "duration_ms": 5, "status": 200}


def _draft_body(**over):
    body = {
        "code": "510880",
        "name": "红利ETF华泰柏瑞",
        "direction": "买入",
        "date": None,
        "quantity": 2000,
        "price": 1.85,
        "fee": None,
    }
    body.update(over)
    return body


def test_parse_ok_draft_and_never_writes(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        before = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body())):
            out = parse_entry_draft(conn, "昨天 1.85 买了 2000 份红利ETF华泰柏瑞", today="2026-09-26")
        after = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    assert out["ok"] is True
    assert out["mode"] == "ok"
    draft = out["draft"]
    assert draft["code"] == "510880"
    assert draft["name"] == "红利ETF华泰柏瑞"  # 名称以库内为准
    assert draft["direction"] == "买入"
    assert draft["date"] is None  # 原话没写日期 → 不猜"昨天"
    assert draft["quantity"] == 2000
    assert draft["price"] == 1.85
    assert draft["fee"] is None  # fee 不猜，交给前端自动估算
    # AI 从不写库
    assert before == after == 0


def test_unknown_code_rejected(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(code="600519", name="贵州茅台"))):
            out = parse_entry_draft(conn, "1.85 买了 2000 份贵州茅台", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "unknown_code"
    assert out["draft"] is None


def test_date_never_computed_by_model(app_module):
    """原话只有"昨天"，模型硬给日期 → 归一为 null（不让模型算日期）。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(date="2026-09-25"))):
            out = parse_entry_draft(conn, "昨天 1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["draft"]["date"] is None
    assert any("date" in w for w in out["warnings"])


def test_explicit_date_in_utterance_is_used(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(date=None))):
            out = parse_entry_draft(conn, "9月25日 1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["draft"]["date"] == "2026-09-25"


def test_future_date_dropped(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body())):
            out = parse_entry_draft(conn, "2026-12-31 1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["draft"]["date"] is None


def test_invalid_direction_rejected(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(direction="抄底"))):
            out = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "invalid_direction"


def test_invalid_value_rejected(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        for body, utterance in (
            (_draft_body(quantity=0), "1.85 买了 0 份红利ETF"),
            (_draft_body(price=-1), "1.85 买了 2000 份红利ETF"),
            (_draft_body(quantity=None), "1.85 买了 2000 份红利ETF"),
        ):
            with patch("ai_entry.call_ai", return_value=_mock_model(body)):
                out = parse_entry_draft(conn, utterance, today="2026-09-26")
            assert out["ok"] is False
            assert out["mode"] == "invalid_value"


def test_untraceable_number_rejected(app_module):
    """模型给的原话里没有的数字 → 拒绝，不预填来源不明的价格。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(price=3.14))):
            out = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "untraceable_number"
    assert out["draft"] is None


def test_unparsable_output(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model("我听不懂你在说什么")):
            out = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "unparsable"


def test_shadow_mode_marks_preview(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn, shadow=True)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body())):
            out = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is True
    assert out["shadow"] is True
    assert "影子模式" in out["hint"]


def test_payload_whitelist_and_no_ledger_values(app_module):
    from ai_entry import assemble_entry_payload

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        conn.execute(
            "INSERT INTO transactions (date, code, name, direction, quantity, price, amount, fee) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("2026-01-05", "600028", "中国石化", "买入", 700, 6.2, 4340, 5),
        )
        conn.commit()
        payload = assemble_entry_payload(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert set(payload) == ALLOWED_KEYS["nl_entry"]
    dumped = json.dumps(payload, ensure_ascii=False)
    # 账本数值一个都不进：持仓数量/成本、交易数量/金额都不许出现
    for leaked in ("1000", "1.5", "4340", "6.2", "700"):
        assert leaked not in dumped
    assert set(payload["available_codes"]) == {"510880 红利ETF华泰柏瑞", "600028 中国石化"}
    # 结构性断言（比字面量黑名单硬）：候选清单只能是 "代码 名称" 两段，别的一律不许有
    assert all(re.match(r"^\S+ \S", item) for item in payload["available_codes"])
    assert payload["today"] == "2026-09-26"
    assert payload["utterance"] == "1.85 买了 2000 份红利ETF"


def test_feature_disabled_skips_call(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn, features={"nl_entry": False})
        with patch("ai_entry.call_ai") as mock_call:
            out = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")
        assert mock_call.call_count == 0

    assert out["mode"] == "feature_disabled"
    assert out["draft"] is None


def test_master_switch_off_skips_call(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        from ai_client import save_ai_config

        save_ai_config(conn, {"enabled": False, "features": {"nl_entry": True}})
        conn.commit()
        with patch("ai_entry.call_ai") as mock_call:
            out = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")
        assert mock_call.call_count == 0

    assert out["mode"] == "disabled"


def test_timeout_returns_no_draft(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value={"ok": False, "reason": "timeout", "status": None}):
            out = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["mode"] == "timeout"
    assert out["draft"] is None


def test_available_assets_none_when_every_source_fails():
    from ai_entry import available_assets

    class _BoomConn:
        def execute(self, *args, **kwargs):
            raise RuntimeError("boom")

    with patch("ai_entry.get_watchlist", side_effect=RuntimeError("boom")):
        assert available_assets(_BoomConn()) is None


def test_available_assets_keeps_sold_codes(app_module):
    from ai_entry import available_assets

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO transactions (date, code, name, direction, quantity, price, amount, fee) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("2026-02-02", "159915", "创业板ETF", "卖出", 100, 2.0, 200, 0),
        )
        conn.commit()
        assets = available_assets(conn)

    assert "159915 创业板ETF" in assets


def test_endpoint_ok(app_module, client):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
    with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body())):
        res = client.post("/ai/nl-entry", json={"utterance": "1.85 买了 2000 份红利ETF"})

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["draft"]["code"] == "510880"


def test_endpoint_rejects_long_utterance_without_calling_model(app_module, client):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
    with patch("ai_entry.call_ai") as mock_call:
        res = client.post("/ai/nl-entry", json={"utterance": "买" * 201})
        assert mock_call.call_count == 0

    assert res.status_code == 400


def test_endpoint_rejects_empty_utterance(app_module, client):
    with patch("ai_entry.call_ai") as mock_call:
        res = client.post("/ai/nl-entry", json={"utterance": "   "})
        assert mock_call.call_count == 0

    assert res.status_code == 400


def test_end_to_end_through_call_ai_writes_audit(app_module, client):
    """真走 call_ai（只把供应方请求打桩）：审计有记录，且实际发出的 payload 不含账本数值。

    上面那些用例都 patch 掉了 ai_entry.call_ai，等于绕过了审计与真实 payload，所以「白名单」
    在那些用例里只断言了构造函数，没有断言真正发出去的东西 —— 这条补上。

    这里必须按名字 patch ai_client：前提是 ai_entry 在 conftest 的 reload 清单里
    （否则它会跨用例握着上一次导入的 ai_client 对象，打桩落空、真的发网络请求，
    表现为 http_404 而不是干净的打桩失败）。
    """
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
    model_body = json.dumps(_draft_body(), ensure_ascii=False)
    provider = '{"choices":[{"message":{"content":%s}}],"usage":{"total_tokens":42}}' % json.dumps(model_body)
    with patch("ai_client._post_chat", return_value=(200, provider)) as mock_post:
        res = client.post("/ai/nl-entry", json={"utterance": "1.85 买了 2000 份红利ETF"})

    body = res.json()
    assert body.get("ok") is True, {k: body.get(k) for k in ("mode", "reason", "warnings")}
    assert body["draft"]["code"] == "510880"

    # 断言**真正发出去的那个请求体**（审计里 message 被截到 500 字符，只信它不够硬）。
    # _post_chat(url, api_key, payload, timeout) → args[2] 就是 payload。
    assert mock_post.call_count == 1
    request_payload = mock_post.call_args.args[2]
    sent = json.dumps(request_payload, ensure_ascii=False)
    assert set(request_payload) == {"model", "messages", "max_tokens", "temperature"}
    user_content = request_payload["messages"][1]["content"]
    sent_user = json.loads(user_content)
    assert set(sent_user) == ALLOWED_KEYS["nl_entry"]
    # 持仓数量(1000) / 成本(1.5) 一个都不许出现在真正发出去的请求里
    assert "1000" not in sent
    assert "1.5" not in sent
    assert "510880 红利ETF华泰柏瑞" in sent  # 候选清单在

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        row = conn.execute(
            "SELECT feature, ok, output_text FROM ai_call_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
    # 测试里的连接没有 Row 工厂，按下标取（与其它用例一致）
    assert row is not None
    feature, ok, output_text = row
    assert feature == "nl_entry"
    assert ok == 1
    assert str(output_text or "").strip()  # 审计留了原始输出，便于复盘


def test_direction_conflict_rejected(app_module):
    """原话明说"卖了"，模型给"买入" → 拒绝（买反了会直接写错账）。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(direction="买入"))):
            out = parse_entry_draft(conn, "1.85 卖了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "direction_conflict"


def test_direction_conflict_reverse_rejected(app_module):
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(direction="卖出"))):
            out = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "direction_conflict"


def test_monetary_number_not_used_as_share_count(app_module):
    """「3700 元」是金额位置，不能被当成股数。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(quantity=3700, price=1.85))):
            out = parse_entry_draft(conn, "3700 元买了 2000 份红利ETF，单价 1.85", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "unit_conflict"


def test_share_count_not_used_as_unit_price(app_module):
    """「2000 份」是数量位置，不能被当成单价。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(quantity=1.85, price=2000))):
            out = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "unit_conflict"


def test_spend_total_mismatch_rejected(app_module):
    """「花了 3700 元买了 2000 份」而模型把 3700 当单价 → 与总额对不上，拒绝。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(quantity=2000, price=3700))):
            out = parse_entry_draft(conn, "花了 3700 元买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "amount_mismatch"


def test_spend_total_consistent_is_accepted(app_module):
    """同一句话里给了总额也给了单价、且能对上 → 必须正常出草稿（别误杀）。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(quantity=2000, price=1.85))):
            out = parse_entry_draft(conn, "花了 3700 元买了 2000 份红利ETF，单价 1.85", today="2026-09-26")

    assert out["ok"] is True, out
    assert out["draft"]["price"] == 1.85


def test_fullwidth_digits_and_punctuation(app_module):
    """中文输入法下的全角数字/句点/连字符也要能对上（"１．８５" → 1.85）。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body())):
            out = parse_entry_draft(conn, "２０２６－０９－２５ １．８５ 买了 ２０００ 份红利ETF", today="2026-09-26")

    assert out["ok"] is True, out
    assert out["draft"]["quantity"] == 2000
    assert out["draft"]["price"] == 1.85
    assert out["draft"]["date"] == "2026-09-25"


def test_cn_year_rollback_only_at_year_end():
    """只有"年末说月初"才回退到去年；其余未来日期一律不猜。"""
    from ai_entry import explicit_date_in_text

    assert explicit_date_in_text("12月30日 买了", today="2026-01-05") == "2025-12-30"
    assert explicit_date_in_text("12月30日 买了", today="2026-12-31") == "2026-12-30"
    assert explicit_date_in_text("10月8日 买了", today="2026-09-26") is None
    assert explicit_date_in_text("9月25日 买了", today="2026-09-26") == "2026-09-25"


def test_holdings_read_failure_returns_none():
    """持仓是主源：它读失败必须整体判失败，不能拿空清单冒充"库里没数据"。"""
    from ai_entry import available_assets

    class _EmptyResult:
        def fetchall(self):
            return []

    class _HoldingsBoom:
        def execute(self, sql, *args, **kwargs):
            if "holdings" in sql:
                raise RuntimeError("boom")
            return _EmptyResult()

    with patch("ai_entry.get_watchlist", return_value=[]):
        assert available_assets(_HoldingsBoom()) is None


def test_default_today_follows_app_timezone_not_container_tz(monkeypatch, app_module):
    """容器 TZ 与 APP_TIMEZONE 不一致时，"今天"仍按应用时区算（细则 §1.9-3）。"""
    import os
    import time
    from datetime import datetime

    from ai_entry import assemble_entry_payload
    from database import LOCAL_TZ, local_today_iso

    old_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "UTC")
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        with app_module.get_db_connection(app_module.DB_PATH) as conn:
            _seed(conn)
            payload = assemble_entry_payload(conn, "1.85 买了 2000 份红利ETF")
        shanghai_today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
        assert payload["today"] == local_today_iso() == shanghai_today
    finally:
        if old_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", old_tz)
        if hasattr(time, "tzset"):
            time.tzset()


def test_date_component_not_accepted_as_price(app_module):
    """「9月25日」里的 25 不是价格：日期分量与证券代码不算数字来源。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(price=25))):
            out = parse_entry_draft(conn, "9月25日 1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "untraceable_number"


def test_date_year_not_accepted_as_quantity(app_module):
    """ISO 日期的年份 2026 也不是数量。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(quantity=2026))):
            out = parse_entry_draft(conn, "2026-09-25 买了 2000 份红利ETF，1.85", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "untraceable_number"


def test_code_digits_not_accepted_as_quantity(app_module):
    """原话里出现的证券代码 510880 不是数量（否则会记成 51 万份）。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(quantity=510880))):
            out = parse_entry_draft(conn, "1.85 买了 2000 份 510880", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "untraceable_number"


def test_quantity_must_come_from_share_position(app_module):
    """原话写了「2000 份」，数量就不许取别的数字（哪怕那个数字确实在原话里）。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(quantity=1.85, price=1.85))):
            out = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "unit_conflict"


def test_spend_marker_is_a_word_not_a_single_char(app_module):
    """标的名称里带"花""共"（梅花生物 / 共进股份）不能被当成"花了…元"的总额。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn, code="600873", name="梅花生物")
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(code="600873", price=12.5))):
            out = parse_entry_draft(conn, "买了 2000 份梅花生物 12.5 元", today="2026-09-26")

    assert out["ok"] is True, out
    assert out["draft"]["price"] == 12.5


def test_unit_position_tolerates_spaces():
    """数字与单位之间的多个空格不能让单位识别失效。"""
    from ai_entry import _number_positions, _spend_total_in_text

    assert _number_positions("买了 2000  份红利ETF") == ([2000.0], [])
    assert _number_positions("花了 3700  元") == ([], [3700.0])
    assert _spend_total_in_text("花了 3700  元买了 2000 份") == 3700.0


def test_local_reasons_get_their_own_mode(app_module):
    """本地就能确定的原因要给具体 mode —— 前端是按 mode 查人话表的。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)  # 没有任何持仓/交易 → 空清单
        with patch("ai_entry.call_ai") as mock_call:
            empty = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")
        assert mock_call.call_count == 0
    assert empty["mode"] == "empty_universe"

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.available_assets", return_value=None), patch("ai_entry.call_ai") as mock_call:
            broken = parse_entry_draft(conn, "1.85 买了 2000 份红利ETF", today="2026-09-26")
        assert mock_call.call_count == 0
    assert broken["mode"] == "assets_unavailable"


def test_cjk_date_with_year_keeps_that_year(app_module):
    """「2025年9月25日」必须按原话的年份记，不能被"今天"的年份顶掉。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body())):
            out = parse_entry_draft(conn, "2025年9月25日 1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is True, out
    assert out["draft"]["date"] == "2025-09-25"


def test_cjk_date_with_year_is_not_rolled_back(app_module):
    """带年日期不做跨年回退：今天是 2026-01-05，"2024年12月30日"就该记 2024-12-30。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body())):
            out = parse_entry_draft(conn, "2024年12月30日 1.85 买了 2000 份红利ETF", today="2026-01-05")

    assert out["ok"] is True, out
    assert out["draft"]["date"] == "2024-12-30"


def test_year_in_cjk_date_not_usable_as_price(app_module):
    """「2026年9月25日」里的 2026 不是价格（整段日期都要从可溯数字里抹掉）。"""
    from ai_entry import parse_entry_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_entry.call_ai", return_value=_mock_model(_draft_body(price=2026))):
            out = parse_entry_draft(conn, "2026年9月25日 1.85 买了 2000 份红利ETF", today="2026-09-26")

    assert out["ok"] is False
    assert out["mode"] == "untraceable_number"


def test_date_writing_variants():
    """几种常见写法都要认；但"12月买了 3000 份"里的 3000 不能被当成年月日。"""
    from ai_entry import explicit_date_in_text

    today = "2026-09-26"
    assert explicit_date_in_text("9月25日 买了", today=today) == "2026-09-25"
    assert explicit_date_in_text("9月25 买了", today=today) == "2026-09-25"
    assert explicit_date_in_text("2026/09/25 买了", today=today) == "2026-09-25"
    assert explicit_date_in_text("2026.09.25 买了", today=today) == "2026-09-25"
    assert explicit_date_in_text("2025年9月25日 买了", today=today) == "2025-09-25"
    assert explicit_date_in_text("12月买了 3000 份", today=today) is None
    assert explicit_date_in_text("12月 3000 份", today=today) is None
    assert explicit_date_in_text("昨天买了 2000 份", today=today) is None


def test_date_day_boundary_does_not_eat_price_or_amount():
    """日的边界不能只看数字：不能让"9月1.85"把价格的前半截当日期抹掉、让"9月25块"吃掉金额。"""
    from ai_entry import _number_positions, _numbers_in_text, explicit_date_in_text

    today = "2026-09-26"
    # 正常写法照认（含省略"日"的、句末句点的）
    assert explicit_date_in_text("9月25 买了 2000 份", today=today) == "2026-09-25"
    assert explicit_date_in_text("9月25. 买了", today=today) == "2026-09-25"
    assert explicit_date_in_text("2026-09-25. 买了", today=today) == "2026-09-25"
    # 紧贴小数点/金额单位的不能当日期，且那些数字必须原样可用
    assert explicit_date_in_text("9月1.85 买了 2000 份", today=today) is None
    assert any(abs(n - 1.85) < 1e-9 for n in _numbers_in_text("9月1.85 买了 2000 份"))
    assert explicit_date_in_text("2025年9月1.85 买了", today=today) is None
    assert explicit_date_in_text("2026-09-1.85 买了", today=today) is None
    assert any(abs(n - 1.85) < 1e-9 for n in _numbers_in_text("2026-09-1.85 买了"))
    assert explicit_date_in_text("9月25块", today=today) is None
    assert _number_positions("9月25块") == ([], [25.0])
    # 数字紧贴的情况仍然不认（"12月买了 3000 份"）
    assert explicit_date_in_text("12月买了 3000 份", today=today) is None
