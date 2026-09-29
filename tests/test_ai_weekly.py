"""N2 周报 AI 段的测试（细则 §2.8 九条 + 区间口径防回归）。

注意两件事：
1. 每个用例**在函数内** `import ai_weekly` —— conftest 每个用例都会重载后端模块，
   顶层导入拿到的是过期模块对象，打桩会打在旧对象上（N1 踩过同一个坑）。
2. `run_weekly_brief` / cron 端点内部会自己算"本周"（依赖真实今天），所以那些用例
   要打桩 `ai_weekly.week_bounds`，否则断言会随后端跑在哪一天而变。
"""
import json
import pathlib
from contextlib import contextmanager
from unittest.mock import patch

from ai_payload import ALLOWED_KEYS

START = "2026-09-28"
END = "2026-10-02"


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
            "features": features if features is not None else {"weekly": True},
        },
    )
    conn.commit()


def _summary(*, period_gain=-12345, flow=20000):
    """故意把全期字段塞成很显眼的值：一旦有人用错字段，断言会立刻炸。"""
    return {
        "period_gain": period_gain,
        "period_net_contribution": flow,
        "total_gain": 999999,
        "net_contribution": 888888,
    }


def _packed(reasons=None, moves=None):
    return {
        "reasons": reasons if reasons is not None else [],
        "moves": moves if moves is not None else [],
        "reason_coverage": {"matched": len(reasons or []), "window_days": 2, "note": ""},
    }


def _one_notice():
    return [{"title": "某公告", "kind": "notice", "code": "000651"}]


def _ok(text="同期有这些信息 [某公告]。"):
    return {"ok": True, "text": text, "audit_id": 1, "duration_ms": 5, "status": 200}


@contextmanager
def _offline(*, summary=None, packed=None, due=None, breaches=None, plans=None):
    """隔离四个数据源：测试不打网络、不依赖当日真实持仓/公告。"""
    due = due if due is not None else {"overdue": [], "d0": [], "d7": [{"id": 1}], "d30": [{"id": 2}, {"id": 3}]}
    with patch("ai_weekly.build_performance_summary", return_value=summary or _summary()), \
        patch("ai_weekly.build_discipline_report", return_value={"breaches": breaches or [], "plans": plans or []}), \
        patch("ai_weekly.check_deposit_due", return_value={"buckets": due, "count": 3}), \
        patch("ai_weekly.reasons_for_holdings", return_value=packed if packed is not None else _packed()), \
        patch("ai_weekly._reason_holding_codes", return_value=["000651"]):
        yield


def test_week_bounds_covers_the_just_finished_trading_week():
    import ai_weekly
    from datetime import date

    assert ai_weekly.week_bounds("2026-09-28") == ("2026-09-28", "2026-09-28")  # 周一当天
    assert ai_weekly.week_bounds("2026-09-30") == ("2026-09-28", "2026-09-30")  # 周三：本周至今
    assert ai_weekly.week_bounds("2026-10-03") == ("2026-09-28", "2026-10-02")  # 周六：刚收完那一周
    assert ai_weekly.week_bounds("2026-10-04") == ("2026-09-28", "2026-10-02")  # 周日同上一周
    assert ai_weekly.week_bounds("2026-10-05") == ("2026-10-05", "2026-10-05")  # 新的一周重新起算
    assert ai_weekly.week_bounds("2026-12-31") == ("2026-12-28", "2026-12-31")  # 跨年
    # 周标签可逆：缓存键靠它按周去重
    year, week = ai_weekly.week_tag(START).split("-W")
    assert date.fromisocalendar(int(year), int(week), 1).isoformat() == START


def test_payload_uses_interval_fields_and_whitelist(app_module):
    """金额必须取**区间**口径：用错字段会把"开户以来总收益"当成"这周赚了多少"。"""
    import ai_weekly

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with _offline():
            payload, _context = ai_weekly.assemble_weekly_payload(conn, start=START, end=END)

    assert set(payload) == ALLOWED_KEYS["weekly"]
    assert payload["window_start"] == START and payload["window_end"] == END
    assert payload["net_gain_rounded"] == -12000  # -12345 → 取整到千位
    assert payload["external_flow_rounded"] == 20000
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "999999" not in dumped and "888888" not in dumped  # 全期口径一个都不许进来
    # 存款只给条数，不给金额/银行名
    assert payload["deposits_due"] == {"overdue": 0, "d0": 0, "d7": 1, "d30": 2}


def test_header_is_deterministic_and_never_fakes_a_number():
    import ai_weekly

    header = ai_weekly.build_weekly_header(
        {"period_gain": -12345, "period_net_contribution": 20000},
        start=START,
        end=END,
        breaches=2,
        due={"overdue": [], "d0": [], "d7": [{"id": 1}], "d30": []},
    )
    assert "【周报 09-28 ~ 10-02】" in header
    assert "区间收益 -¥12,345" in header and "净投入 +¥20,000" in header
    assert "纪律破线 2 条" in header and "存款到期 1 笔" in header

    # 没有基准快照时不能编 0：那等于告诉用户"这周没盈亏"
    no_basis = ai_weekly.build_weekly_header(
        {"period_gain": None, "period_net_contribution": 20000}, start=START, end=END, breaches=0, due={}
    )
    assert "算不出" in no_basis


def test_same_week_calls_model_once(app_module):
    import ai_weekly

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(packed=_packed(reasons=_one_notice())), patch(
            "ai_weekly.call_ai", return_value=_ok()
        ) as mock_call:
            first = ai_weekly.generate_weekly_segment(conn, start=START, end=END)
            second = ai_weekly.generate_weekly_segment(conn, start=START, end=END)

    assert mock_call.call_count == 1
    assert first["mode"] == second["mode"] == "ok"
    assert first["text"] == second["text"]


def test_empty_week_skips_model_but_keeps_header(app_module):
    import ai_weekly

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(packed=_packed()), patch("ai_weekly.call_ai") as mock_call:
            rec = ai_weekly.generate_weekly_segment(conn, start=START, end=END)
            assert mock_call.call_count == 0

    assert rec["mode"] == "empty"
    assert rec["text"] == ai_weekly.WEEKLY_EMPTY_LINE
    assert "【周报" in rec["header"]  # 空数据周也要有数字（抬头是代码算的）


def test_shadow_mode_generates_and_audits_but_never_pushes(app_module):
    import ai_weekly

    provider = '{"choices":[{"message":{"content":"同期有这些信息 [某公告]。"}}],"usage":{"total_tokens":9}}'
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn, shadow=True)
        with _offline(packed=_packed(reasons=_one_notice())), \
            patch("ai_weekly.week_bounds", return_value=(START, END)), \
            patch("ai_client._post_chat", return_value=(200, provider)) as mock_post, \
            patch("ai_weekly.notify_weekly_brief") as mock_send:
            out = ai_weekly.run_weekly_brief(conn, notify=True)
        rows = conn.execute("SELECT feature, ok FROM ai_call_log WHERE feature = 'weekly'").fetchall()

    assert mock_post.call_count == 1  # 真的调用过
    assert rows and rows[0][1] == 1  # 审计有记录
    assert mock_send.call_count == 0  # 但不进推送
    assert out["sent"] is False and out["reason"] == "shadow"


def test_failure_still_pushes_the_deterministic_header(app_module):
    import ai_weekly

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(packed=_packed(reasons=_one_notice())), \
            patch("ai_weekly.week_bounds", return_value=(START, END)), \
            patch("ai_weekly.call_ai", return_value={"ok": False, "reason": "timeout", "status": None}), \
            patch("ai_weekly.notify_weekly_brief", return_value={"sent": True}) as mock_send:
            out = ai_weekly.run_weekly_brief(conn, notify=True)

    assert out["mode"] == "timeout"
    assert mock_send.call_count == 1
    sent_text = mock_send.call_args[0][0]
    assert "【周报" in sent_text and "区间收益" in sent_text  # 抬头照发
    assert out["sent"] is True


def test_switch_off_does_not_call_or_push(app_module):
    import ai_weekly
    from ai_client import save_ai_config

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        # ① 关用例
        save_ai_config(conn, {"enabled": True, "features": {"weekly": False}})
        conn.commit()
        with _offline(packed=_packed(reasons=_one_notice())), \
            patch("ai_weekly.week_bounds", return_value=(START, END)), \
            patch("ai_weekly.call_ai") as mock_call, \
            patch("ai_weekly.notify_weekly_brief") as mock_send:
            off = ai_weekly.run_weekly_brief(conn, notify=True)
            assert mock_call.call_count == 0
            assert mock_send.call_count == 0
        assert off["mode"] == "disabled" and off["sent"] is False

        # ② 关总开关
        save_ai_config(conn, {"enabled": False, "features": {"weekly": True}})
        conn.commit()
        with _offline(packed=_packed(reasons=_one_notice())), \
            patch("ai_weekly.week_bounds", return_value=(START, END)), \
            patch("ai_weekly.call_ai") as mock_call, \
            patch("ai_weekly.notify_weekly_brief") as mock_send:
            disabled = ai_weekly.run_weekly_brief(conn, notify=True)
            assert mock_call.call_count == 0
            assert mock_send.call_count == 0
        assert disabled["mode"] == "disabled"


def test_notify_false_generates_without_sending(app_module):
    import ai_weekly

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(packed=_packed(reasons=_one_notice())), \
            patch("ai_weekly.week_bounds", return_value=(START, END)), \
            patch("ai_weekly.call_ai", return_value=_ok()), \
            patch("ai_weekly.notify_weekly_brief") as mock_send:
            out = ai_weekly.run_weekly_brief(conn, notify=False)

    assert out["mode"] == "ok"
    assert mock_send.call_count == 0
    assert out["window_start"] == START and out["window_end"] == END


def test_event_registered_everywhere():
    """事件名要在三处登记：notify 的事件表 / 默认通道 / 前端事件标签。"""
    import notify

    assert "weekly_brief" in notify.EVENT_KEYS
    assert notify.DEFAULT_EVENT_CHANNELS.get("weekly_brief")
    path = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "views" / "NotifyOpsTab.vue"
    assert "weekly_brief" in path.read_text(encoding="utf-8")


def test_cron_endpoint_requires_token(client, monkeypatch):
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    assert client.post("/cron/weekly-brief").status_code == 401
    assert client.post("/cron/weekly-brief", headers={"X-Cron-Token": "wrong"}).status_code == 401


def test_cron_endpoint_unconfigured_returns_503(client, monkeypatch):
    monkeypatch.delenv("CRON_API_TOKEN", raising=False)
    assert client.post("/cron/weekly-brief").status_code == 503


def test_cron_endpoint_with_token(app_module, client, monkeypatch):
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
    with _offline(packed=_packed(reasons=_one_notice())), \
        patch("ai_weekly.week_bounds", return_value=(START, END)), \
        patch("ai_weekly.call_ai", return_value=_ok()), \
        patch("ai_weekly.notify_weekly_brief", return_value={"sent": True}):
        res = client.post(
            "/cron/weekly-brief",
            headers={"X-Cron-Token": "correct-cron-token"},
            json={"notify": True},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["window_start"] == START and body["window_end"] == END
    assert body["sent"] is True


def test_only_success_and_empty_are_cached(app_module):
    """失败不许像成功一样钉住整周：周报一周只跑一次，钉住就等于这周再也不会重试。"""
    import ai_weekly

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        key = ai_weekly.weekly_cache_key(START)
        with _offline(packed=_packed(reasons=_one_notice())), \
            patch("ai_weekly.week_bounds", return_value=(START, END)), \
            patch(
                "ai_weekly.call_ai", return_value={"ok": False, "reason": "timeout", "status": None}
            ) as mock_call:
            first = ai_weekly.generate_weekly_segment(conn, start=START, end=END)
            second = ai_weekly.generate_weekly_segment(conn, start=START, end=END)

        assert mock_call.call_count == 2  # 没被缓存挡住，第二次真的重试了
        assert first["mode"] == second["mode"] == "timeout"
        assert conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone() is None

        # 空数据周相反：那是"确实没内容"，按成功缓存，不再重试
        with _offline(packed=_packed()), patch("ai_weekly.call_ai") as mock_call2:
            empty = ai_weekly.generate_weekly_segment(conn, start=START, end=END)
            assert mock_call2.call_count == 0
        assert empty["mode"] == "empty"
        assert conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone() is not None


def test_missing_baseline_snapshot_stays_null_in_payload(app_module):
    """缺基准快照时 payload 必须是 null：写成 0 等于告诉模型"这周没盈亏"。"""
    import ai_weekly

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with _offline(
            summary={
                "period_gain": None,
                "period_net_contribution": None,
                "total_gain": 999999,
                "net_contribution": 888888,
            }
        ):
            payload, _context = ai_weekly.assemble_weekly_payload(conn, start=START, end=END)

    assert payload["net_gain_rounded"] is None and payload["external_flow_rounded"] is None
    assert "999999" not in json.dumps(payload, ensure_ascii=False)


def test_trade_advice_words_block_the_weekly_segment(app_module):
    """投资建议词表原来只挂在档案摘要上；周报也是叙述性结论，strict 下要拦。"""
    import ai_weekly

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(packed=_packed(reasons=_one_notice())), \
            patch("ai_weekly.week_bounds", return_value=(START, END)), \
            patch("ai_weekly.call_ai", return_value=_ok("同期有这些信息 [某公告]，属利好。")), \
            patch("ai_weekly.notify_weekly_brief", return_value={"sent": True}) as mock_send:
            out = ai_weekly.run_weekly_brief(conn, notify=True)

    assert out["mode"] == "blocked"
    assert mock_send.call_count == 1  # AI 段被拦，抬头照发
