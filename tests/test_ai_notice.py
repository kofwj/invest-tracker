"""N4 公告要点分类（feature 键 `notice_class`）的测试。

覆盖细则 §2.6 五条验收 + 复核细节（引用可溯 / 标签三值 / 禁用词 / 缓存 / 不进推送）。

两个硬约定（N1、N2 各踩过一次）：
1. 每个用例**在函数内** `import ai_notice`：conftest 每个用例都会重载后端模块，
   顶层导入拿到的是过期模块对象，打桩会打在旧对象上。
2. `notice_items` 被隔离掉，测试不打网络、不依赖当日真实公告；缓存的\"过期\"判断走
   `ai_notice._now_local()` 相对时间，所以要 patch 它，不能靠真实时钟。
"""
import json
import pathlib
import re
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

import pytest

from ai_payload import ALLOWED_KEYS

TITLE = "农业银行:关于非执行董事任职的公告"
TITLE2 = "农业银行:关于召开2026年第一次临时股东大会的通知"
DAY = "2026-09-25"


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
            "features": features if features is not None else {"notice_class": True},
        },
    )
    conn.commit()


def _items(*titles, extra=None):
    """构造公告条目；`extra` 用来塞\"不该进 payload\"的字段（数量/成本/链接）。"""
    picked = titles or (TITLE,)
    out = []
    for idx, title in enumerate(picked):
        row = {
            "kind": "notice",
            "notice_type": "高管人员任职变动",
            "title": title,
            "date": "2026-09-%02d" % (24 - idx),
        }
        row.update(extra or {})
        out.append(row)
    return out


@contextmanager
def _offline(items=None, *, name="农业银行"):
    with patch("ai_notice.notice_items", return_value=(name, items if items is not None else _items())):
        yield


def _ok(results):
    text = results if isinstance(results, str) else json.dumps({"results": results}, ensure_ascii=False)
    return {"ok": True, "text": text, "audit_id": 7, "duration_ms": 5, "status": 200}


def _row(title=TITLE, label="无法判断", why="仅人事任免，与股价无直接对应"):
    return {"title": title, "label": label, "why": why}


def test_payload_whitelist_has_three_labels_and_no_amounts():
    """细则 §2.2：只投喂标题/类型/日期，labels 由代码写死，数量成本一律不进 payload。"""
    import ai_notice

    payload = ai_notice.assemble_notice_payload(
        "601288",
        "农业银行",
        _items(extra={"quantity": 1200, "cost": 3.45, "amount": 41400, "url": "http://x"}),
    )

    assert set(payload) == ALLOWED_KEYS["notice_class"]
    assert payload["labels"] == ["相关", "无关", "无法判断"]
    assert set(payload["items"][0]) == {"kind", "notice_type", "title", "date"}
    dumped = json.dumps(payload, ensure_ascii=False)
    for leak in ("1200", "3.45", "41400", "http://x"):
        assert leak not in dumped


def test_no_notice_never_calls_model(app_module):
    """验收 1：窗口内没公告 → 空结果且不调模型（省额度，也不编\"没有公告所以是技术性下跌\"）。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline([]), patch("ai_notice.call_ai") as mock_call:
            rec = ai_notice.classify_notice_points(conn, "601288")
            assert mock_call.call_count == 0

    assert rec["mode"] == "empty"
    assert rec["results"] == [] and rec["items_count"] == 0


def test_title_must_match_input_exactly(app_module):
    """验收 4：引用可溯 —— 模型改写/新增的标题一律不采信，但同批里合法的条目照留。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(_items(TITLE, TITLE2)), patch(
            "ai_notice.call_ai",
            return_value=_ok([_row(title="农业银行董事任职公告（改写版）"), _row(title=TITLE2, label="无关")]),
        ):
            rec = ai_notice.classify_notice_points(conn, "601288")

    assert rec["mode"] == "ok"
    assert [row["title"] for row in rec["results"]] == [TITLE2]
    assert set(rec["results"][0]) == {"title", "label", "why"}  # 输出侧白名单：不套文本校验器就得自己保证
    assert any("来源不可溯" in w for w in rec["warnings"])


def test_label_must_be_one_of_three(app_module):
    """验收 2/3 的前置：label 只能取三个值之一，别的值丢该条。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(_items(TITLE, TITLE2)), patch(
            "ai_notice.call_ai", return_value=_ok([_row(label="重要"), _row(title=TITLE2)])
        ):
            rec = ai_notice.classify_notice_points(conn, "601288")

    assert [row["title"] for row in rec["results"]] == [TITLE2]
    assert any("标签非法" in w for w in rec["warnings"])


@pytest.mark.parametrize(
    "why, hint",
    [("利好兑现，目标价上调", "投资建议词"), ("因为人事任免导致股价波动", "因果措辞")],
)
def test_banned_why_drops_item_in_strict_mode(app_module, why, hint):
    """验收 3：命中投资建议词 / 因果措辞 → 记 warnings，非影子模式整条丢弃。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_notice.call_ai", return_value=_ok([_row(why=why)])):
            rec = ai_notice.classify_notice_points(conn, "601288")

    assert rec["results"] == []
    assert rec["mode"] == "blocked"
    assert any(hint in w for w in rec["warnings"])


def test_shadow_mode_keeps_item_but_records_warnings(app_module):
    """影子模式：结论照常返回（站内本来就要人看），只是 warnings 落到审计上。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn, shadow=True)
        with _offline(), patch("ai_notice.call_ai", return_value=_ok([_row(why="利好兑现，目标价上调")])), patch(
            "ai_notice.stamp_ai_warnings"
        ) as mock_stamp:
            rec = ai_notice.classify_notice_points(conn, "601288")

    assert len(rec["results"]) == 1 and rec["mode"] == "ok"
    assert mock_stamp.call_count == 1
    assert mock_stamp.call_args.args[2] and "投资建议词" in mock_stamp.call_args.args[2][0]


def test_why_too_long_is_truncated(app_module):
    """why ≤20 字：超长截断该条并记 warning，不整批丢。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_notice.call_ai", return_value=_ok([_row(why="人" * 30)])):
            rec = ai_notice.classify_notice_points(conn, "601288")

    assert rec["mode"] == "ok"
    assert len(rec["results"][0]["why"]) == ai_notice.NOTICE_WHY_MAX_CHARS
    assert any("超长已截断" in w for w in rec["warnings"])


def test_same_day_same_code_calls_model_once(app_module):
    """细则 §2.4：每天一次 —— 同一天同一标的第二次直接用缓存。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_notice.call_ai", return_value=_ok([_row()])) as mock_call:
            first = ai_notice.classify_notice_points(conn, "601288")
            second = ai_notice.classify_notice_points(conn, "601288")

    assert mock_call.call_count == 1
    assert first["cached"] is False and second["cached"] is True
    assert first["results"] == second["results"]


def test_refresh_bypasses_cache(app_module):
    """弹窗里的「刷新」= refresh=True：跳过缓存读重跑一次。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch("ai_notice.call_ai", return_value=_ok([_row()])) as mock_call:
            ai_notice.classify_notice_points(conn, "601288")
            again = ai_notice.classify_notice_points(conn, "601288", refresh=True)

    assert mock_call.call_count == 2
    assert again["cached"] is False


def test_empty_cache_is_recomputed_after_refill(app_module):
    """空结果当天有效，但 16:40 公告补抓之后要重算（照 A3 的 EMPTY_RETRY_AFTER）。"""
    import ai_notice

    with patch("ai_notice._now_local", return_value=datetime(2026, 9, 25, 10, 0, 0)):
        rec = ai_notice._record(code="601288", day=DAY, mode="empty")
        assert ai_notice._cache_usable(rec, day=DAY) is True  # 补抓前：认这个空
    with patch("ai_notice._now_local", return_value=datetime(2026, 9, 25, 17, 0, 0)):
        assert ai_notice._cache_usable(rec, day=DAY) is False  # 补抓后：重算

    # 非空结果不受补抓影响：一整天都算数
    with patch("ai_notice._now_local", return_value=datetime(2026, 9, 25, 17, 0, 0)):
        ok_rec = ai_notice._record(code="601288", day=DAY, mode="ok", results=[_row()])
        assert ai_notice._cache_usable(ok_rec, day=DAY) is True


def test_switch_off_never_calls_model(app_module):
    """关用例 / 关总开关都要在取数之前返回，别白花额度。"""
    import ai_notice
    from ai_client import save_ai_config

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_ai_config(conn, {"enabled": True, "features": {"notice_class": False}})
        conn.commit()
        with _offline(), patch("ai_notice.call_ai") as mock_call:
            off = ai_notice.classify_notice_points(conn, "601288")
            assert mock_call.call_count == 0
        assert off["mode"] == "feature_disabled"

        save_ai_config(conn, {"enabled": False, "features": {"notice_class": True}})
        conn.commit()
        with _offline(), patch("ai_notice.call_ai") as mock_call:
            disabled = ai_notice.classify_notice_points(conn, "601288")
            assert mock_call.call_count == 0
        assert disabled["mode"] == "disabled"


def test_failure_is_cached_for_ten_minutes(app_module):
    """超时只钉 10 分钟：既不连环重试（每次打开弹窗都转 30 秒），也不把一次抖动钉一整天。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with _offline(), patch(
            "ai_notice.call_ai", return_value={"ok": False, "reason": "timeout", "status": None}
        ) as mock_call:
            first = ai_notice.classify_notice_points(conn, "601288")
            second = ai_notice.classify_notice_points(conn, "601288")

    assert mock_call.call_count == 1
    assert first["mode"] == second["mode"] == "timeout"
    assert second["cached"] is True


def test_endpoint_returns_empty_results_and_forwards_refresh(app_module, client):
    """端点本体：空公告 → 空 results；refresh 参数透传，越界拒绝。"""
    # 打桩目标用字符串：patch 会自己去 import routers_ai，这里不需要顶层导入

    with patch("routers_ai.classify_notice_points", return_value={"mode": "empty", "results": []}) as mock_fn:
        plain = client.get("/ai/notice-class/601288")
        refreshed = client.get("/ai/notice-class/601288?refresh=1")

    assert plain.status_code == 200 and plain.json()["results"] == []
    assert refreshed.status_code == 200
    assert mock_fn.call_args_list[1].args[1] == "601288"
    assert mock_fn.call_args_list[1].kwargs["refresh"] is True
    assert mock_fn.call_args_list[0].kwargs["refresh"] is False
    assert client.get("/ai/notice-class/601288?refresh=2").status_code == 422


def test_module_never_touches_push_channels():
    """验收 5 红线：这个用例只进站内 —— 不 import 通知模块、不注册任何通知事件。"""
    import ai_notice
    import notify

    assert not re.search(r"\bnotify", pathlib.Path(ai_notice.__file__).read_text(encoding="utf-8"))
    assert "notice_class" not in notify.EVENT_KEYS


def test_source_failure_is_blocked_not_empty(app_module):
    """取数失败 ≠ 窗口内没有公告：写成 empty 会被当天缓存钉到 16:40，一次抖动误一整天。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _enable(conn)
        with patch("ai_notice.notice_items", return_value=("农业银行", None)), patch("ai_notice.call_ai") as mock_call:
            first = ai_notice.classify_notice_points(conn, "601288")
            assert mock_call.call_count == 0  # 取数都没成功，更不许调模型
            second = ai_notice.classify_notice_points(conn, "601288")

    assert first["mode"] == "blocked" and first["results"] == []
    assert any("原因缓存读取失败" in w for w in first["warnings"])
    assert second["cached"] is True  # blocked 只钉 10 分钟（不是一整天）


def test_notice_items_turns_source_failure_into_none(app_module):
    """防漏检：`notice_items` 真抛异常时必须给出 None 哨兵，别静默退化成空列表。"""
    import ai_notice

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("ai_notice.reasons_for_holdings", side_effect=RuntimeError("boom")):
            name, items = ai_notice.notice_items(conn, "601288")

    assert items is None and name == ""


def test_notice_items_filters_to_notice_kind(app_module):
    """只做公告：新闻（kind=news）与其它类型不许混进来，重复标题去重、按日期倒序。"""
    import ai_notice

    packed = {
        "reasons": [
            {"kind": "news", "title": "某新闻", "date": "2026-09-25", "name": "农业银行"},
            {"kind": "notice", "title": "旧公告", "notice_type": "高管人员任职变动", "date": "2026-09-24"},
            {"kind": "notice", "title": "新公告", "notice_type": "股东大会", "date": "2026-09-25", "name": "农业银行"},
            {"kind": "notice", "title": "新公告", "notice_type": "股东大会", "date": "2026-09-25", "name": "农业银行"},
        ]
    }
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        with patch("ai_notice.reasons_for_holdings", return_value=packed):
            name, items = ai_notice.notice_items(conn, "601288")

    assert name == "农业银行"
    assert [row["title"] for row in items] == ["新公告", "旧公告"]
    assert all(row["kind"] == "notice" for row in items)
