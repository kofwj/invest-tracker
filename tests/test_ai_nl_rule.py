"""A5 自然语言建规则（`nl_rule`）的测试。

覆盖细则 §3.8 的 10 条，外加两条：影子模式**不影响**本例（草稿照常返回），
以及"AI 从不写 alert_rules"。
"""
import json
import re
from unittest.mock import patch

from ai_payload import ALLOWED_KEYS

DRAFT_KEYS = {"target_type", "code", "name", "rule_type", "condition", "threshold"}


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
            "features": features if features is not None else {"nl_rule": True},
        },
    )
    conn.commit()


def _seed(conn, code="000651", name="格力电器"):
    conn.execute(
        "INSERT INTO holdings (code, name, category, quantity, avg_cost, last_price) VALUES (?,?,?,?,?,?)",
        (code, name, "A股权益", 1000, 55.0, 60.5),
    )
    conn.commit()


def _draft_body(**over):
    body = {
        "target_type": "holding",
        "code": "000651",
        "name": "格力电器",
        "rule_type": "price",
        "condition": "below",
        "threshold": 60,
    }
    body.update(over)
    return body


def _mock_model(body):
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return {"ok": True, "text": text, "audit_id": 1, "duration_ms": 5, "status": 200}


def test_parse_ok_price_rule(app_module):
    from ai_nl_rule import parse_rule_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_nl_rule.call_ai", return_value=_mock_model(_draft_body())):
            out = parse_rule_draft(conn, "格力跌到 60 块提醒我")

    assert out["ok"] is True, out
    assert out["draft"]["target_type"] == "holding"
    assert out["draft"]["code"] == "000651"
    assert out["draft"]["rule_type"] == "price"
    assert out["draft"]["condition"] == "below"
    # price 的阈值是价格水平、不能为负（market 的硬约束）
    assert out["draft"]["threshold"] == 60.0


def test_unknown_rule_type_rejected(app_module):
    from ai_nl_rule import parse_rule_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_nl_rule.call_ai", return_value=_mock_model(_draft_body(rule_type="volume"))):
            out = parse_rule_draft(conn, "格力放量提醒我")

    assert out["ok"] is False
    assert out["mode"] == "invalid_rule"
    assert "规则类型" in out["detail"]


def test_code_outside_whitelist_rejected(app_module):
    from ai_nl_rule import parse_rule_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_nl_rule.call_ai", return_value=_mock_model(_draft_body(code="999999", name="不存在"))):
            out = parse_rule_draft(conn, "999999 跌到 10 块提醒我")

    assert out["ok"] is False
    assert out["mode"] == "unknown_code"
    assert out["draft"] is None


def test_portfolio_normalized_and_signed(app_module):
    """target_type=portfolio + change_pct → 归一为 portfolio_pnl，阈值符号按 condition。"""
    from ai_nl_rule import parse_rule_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch(
            "ai_nl_rule.call_ai",
            return_value=_mock_model(
                {"target_type": "portfolio", "rule_type": "change_pct", "condition": "below", "threshold": 2}
            ),
        ):
            down = parse_rule_draft(conn, "组合跌 2% 提醒我")
        with patch(
            "ai_nl_rule.call_ai",
            return_value=_mock_model(
                {"target_type": "holding", "code": "000651", "rule_type": "change_pct", "condition": "above", "threshold": 3}
            ),
        ):
            up = parse_rule_draft(conn, "格力涨 3% 提醒我")

    assert down["ok"] is True, down
    assert down["draft"]["rule_type"] == "portfolio_pnl"
    assert down["draft"]["target_type"] == "portfolio"
    assert down["draft"]["code"] == "PORTFOLIO"
    assert down["draft"]["threshold"] == -2.0  # below → 负
    assert any("归一" in w for w in down["warnings"])

    assert up["ok"] is True, up
    assert up["draft"]["threshold"] == 3.0  # above → 正


def test_percent_threshold_out_of_range_rejected(app_module):
    from ai_nl_rule import parse_rule_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch(
            "ai_nl_rule.call_ai",
            return_value=_mock_model(_draft_body(rule_type="change_pct", threshold=35)),
        ):
            out = parse_rule_draft(conn, "格力跌 35% 提醒我")

    assert out["ok"] is False
    assert out["mode"] == "invalid_rule"
    assert "20" in out["detail"]  # 人话里带上限


def test_unparsable_and_fenced_and_extra_keys(app_module):
    from ai_nl_rule import parse_rule_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        with patch("ai_nl_rule.call_ai", return_value=_mock_model("我听不懂")):
            bad = parse_rule_draft(conn, "随便说点什么")
        fenced = "```json\n%s\n```" % json.dumps(_draft_body(), ensure_ascii=False)
        with patch("ai_nl_rule.call_ai", return_value=_mock_model(fenced)):
            ok = parse_rule_draft(conn, "格力跌到 60 块提醒我")
        extra = _draft_body(confidence="high", note="跌到 60 元提醒")
        with patch("ai_nl_rule.call_ai", return_value=_mock_model(extra)):
            trimmed = parse_rule_draft(conn, "格力跌到 60 块提醒我")

    assert bad["mode"] == "unparsable" and bad["draft"] is None
    assert ok["ok"] is True
    assert trimmed["ok"] is True
    assert set(trimmed["draft"]) == DRAFT_KEYS  # 多余键被丢弃


def test_switch_off_skips_call(app_module):
    from ai_client import save_ai_config
    from ai_nl_rule import parse_rule_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        save_ai_config(conn, {"enabled": True, "features": {"nl_rule": False}})
        conn.commit()
        with patch("ai_nl_rule.call_ai") as mock_call:
            off = parse_rule_draft(conn, "格力跌到 60 块提醒我")
            assert mock_call.call_count == 0

        save_ai_config(conn, {"enabled": False, "features": {"nl_rule": True}})
        conn.commit()
        with patch("ai_nl_rule.call_ai") as mock_call:
            disabled = parse_rule_draft(conn, "格力跌到 60 块提醒我")
            assert mock_call.call_count == 0

    assert off["mode"] == "feature_disabled"
    assert disabled["mode"] == "disabled"


def test_payload_whitelist_and_no_ledger_values(app_module):
    from ai_nl_rule import assemble_rule_payload

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn, code="000651", name="格力电器")
        payload = assemble_rule_payload(conn, "格力跌到 60 块提醒我")

    assert set(payload) == ALLOWED_KEYS["nl_rule"]
    dumped = json.dumps(payload, ensure_ascii=False)
    for leaked in ("1000", "55.0", "60.5", "avg_cost", "quantity"):
        assert leaked not in dumped
    targets = payload["available_codes"]
    assert "000651 格力电器" in targets
    assert "000300 沪深300" in targets  # 指数是合法目标
    assert "PORTFOLIO 组合当日盈亏" in targets
    assert all(re.match(r"^\S+ \S", item) for item in targets)


def test_endpoint_never_writes_alert_rules(app_module, client):
    """AI 只产草稿：调用端点前后 alert_rules 行数不变。"""
    from market import ensure_alert_tables

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
        ensure_alert_tables(conn)
        before = conn.execute("SELECT COUNT(*) FROM alert_rules").fetchone()[0]

    with patch("ai_nl_rule.call_ai", return_value=_mock_model(_draft_body())):
        res = client.post("/ai/nl-rule", json={"utterance": "格力跌到 60 块提醒我"})

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        after = conn.execute("SELECT COUNT(*) FROM alert_rules").fetchone()[0]

    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert before == after == 0


def test_endpoint_rejects_long_utterance_without_calling_model(app_module, client):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn)
    with patch("ai_nl_rule.call_ai") as mock_call:
        res = client.post("/ai/nl-rule", json={"utterance": "设" * 201})
        assert mock_call.call_count == 0

    assert res.status_code == 400


def test_shadow_mode_still_returns_draft(app_module):
    """影子模式不影响本例（与 A4 有意的差异）：草稿本来就必须人工确认。"""
    from ai_nl_rule import parse_rule_draft

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed(conn)
        _enable(conn, shadow=True)
        with patch("ai_nl_rule.call_ai", return_value=_mock_model(_draft_body())) as mock_call:
            out = parse_rule_draft(conn, "格力跌到 60 块提醒我")

    assert mock_call.call_count == 1
    assert out["ok"] is True
    assert out["draft"]["threshold"] == 60.0
