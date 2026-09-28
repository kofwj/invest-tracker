"""A6 用量统计与审计导出的测试（细则 §4.5 六条）。"""
import json
from datetime import date, timedelta

import ai_usage
from database import local_today_iso


def _stamp(offset_days: int = 0) -> str:
    day = date.fromisoformat(local_today_iso()) - timedelta(days=offset_days)
    return day.isoformat() + " 09:00:00"


def _log(conn, *, ok=1, feature="brief", reason=None, duration_ms=None, tokens=None, offset_days=0):
    conn.execute(
        "INSERT INTO ai_call_log (created_at, feature, model, ok, reason, duration_ms, tokens) "
        "VALUES (?, ?, 'demo', ?, ?, ?, ?)",
        (_stamp(offset_days), feature, ok, reason, duration_ms, tokens),
    )
    conn.commit()


def _seed_holding(conn, code="000651", name="格力电器", qty=1000):
    conn.execute(
        "INSERT INTO holdings (code, name, category, quantity, avg_cost, last_price) VALUES (?,?,?,?,?,?)",
        (code, name, "A股权益", qty, 55.0, 60.5),
    )
    conn.commit()


def _notice(conn, code, day_offset=0):
    conn.execute(
        "INSERT OR IGNORE INTO notice_cache (code, date, title, name, notice_type, url) VALUES (?,?,?,?,?,?)",
        (code, _stamp(day_offset)[:10], "某公告", code, "其他", ""),
    )
    conn.commit()


def _market_news(conn, day_offset=0, title="电报"):
    day = _stamp(day_offset)[:10]
    conn.execute(
        "INSERT OR IGNORE INTO market_news_cache (date, published_at, title, content) VALUES (?,?,?,?)",
        (day, day + " 08:00:00", title, ""),
    )
    conn.commit()


def test_empty_database_is_all_zeros(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        out = ai_usage.ai_usage_summary(conn, days=7)

    assert out["calls"] == {"attempted": 0, "ok": 0, "failed": 0, "fail_rate": 0.0}
    assert out["by_feature"] == []
    assert out["by_reason"] == []
    # 窗口内每一天都在（零调用也补 0），不是空数组
    assert len(out["daily"]) == 7
    assert all(row["ok"] == 0 and row["failed"] == 0 for row in out["daily"])
    assert out["reasons_hit"]["days_with_hits"] == 0
    # 不猜成本：不出现任何金额字段
    assert "cost" not in json.dumps(out, ensure_ascii=False)


def test_test_feature_excluded_and_avg_ms_only_for_ok(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _log(conn, ok=1, feature="brief", duration_ms=1000, tokens=120)
        _log(conn, ok=1, feature="brief", duration_ms=2000, tokens=80)
        _log(conn, ok=0, feature="brief", reason="timeout", duration_ms=30000)
        _log(conn, ok=1, feature="test", duration_ms=5)  # 试推不计

        out = ai_usage.ai_usage_summary(conn, days=7)

    assert out["calls"] == {"attempted": 3, "ok": 2, "failed": 1, "fail_rate": 1 / 3}
    assert out["by_feature"] == [{"feature": "brief", "ok": 2, "failed": 1, "tokens": 200, "avg_ms": 1500}]
    # 只有失败的行 → avg_ms 为 null（不把失败耗时算进平均）
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        only_fail = {"attempted": 0}
        conn.execute("DELETE FROM ai_call_log")
        _log(conn, ok=0, feature="profile_digest", reason="blocked", duration_ms=10)
        out2 = ai_usage.ai_usage_summary(conn, days=7)
    assert only_fail is not None
    assert out2["by_feature"] == [
        {"feature": "profile_digest", "ok": 0, "failed": 1, "tokens": 0, "avg_ms": None}
    ]


def test_reason_grouping_and_unknown(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _log(conn, ok=0, reason="timeout")
        _log(conn, ok=0, reason="timeout")
        _log(conn, ok=0, reason="http_503")
        _log(conn, ok=0, reason=None)  # 空 reason → unknown
        out = ai_usage.ai_usage_summary(conn, days=7)

    assert out["by_reason"] == [
        {"reason": "timeout", "count": 2},
        {"reason": "http_503", "count": 1},
        {"reason": "unknown", "count": 1},
    ]


def test_window_and_days_clamping(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _log(conn, ok=1, offset_days=0)
        _log(conn, ok=1, offset_days=3)
        same_day = ai_usage.ai_usage_summary(conn, days=1)
        week = ai_usage.ai_usage_summary(conn, days=7)
        clamped_low = ai_usage.ai_usage_summary(conn, days=0)
        clamped_high = ai_usage.ai_usage_summary(conn, days=99)

    assert same_day["calls"]["attempted"] == 1
    assert week["calls"]["attempted"] == 2
    assert clamped_low["days"] == 1
    assert clamped_high["days"] == 30
    assert clamped_high["since"] < week["since"]


def test_reasons_hit_only_counts_holdings_in_window(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _seed_holding(conn, code="000651", name="格力电器")
        _notice(conn, "000651", day_offset=0)  # 命中持仓
        _notice(conn, "600028", day_offset=0)  # 不在持仓里 → 不算
        _notice(conn, "000651", day_offset=10)  # 窗口外 → 不算
        _market_news(conn, day_offset=0)
        _market_news(conn, day_offset=0, title="电报2")

        out = ai_usage.ai_usage_summary(conn, days=7)

    hits = out["reasons_hit"]
    assert hits["by_source"] == {"news": 0, "notices": 1, "moves": 0, "market_news": 2}
    # 只有"命中持仓"的来源才计入天数：电报每天都有，进来就没意义了
    assert hits["days_with_hits"] == 1
    assert hits["holding_count"] == 1
    assert "market_news" in out["note"]


def test_audit_export_csv_and_json(app_module, client):
    from ai_client import save_ai_config

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        save_ai_config(
            conn,
            {
                "enabled": True,
                "base_url": "https://api.x.com",
                "model": "demo",
                "api_key": "sk-secret-should-not-export",
            },
        )
        conn.commit()
        _log(conn, ok=1, feature="brief")
        _log(conn, ok=0, feature="nl_entry", reason="timeout")
        _log(conn, ok=1, feature="test")  # 导出**要**含试推行（复盘要看全）

    csv_res = client.get("/ai/audit/export?days=7&format=csv")
    assert csv_res.status_code == 200
    assert "attachment" in csv_res.headers.get("content-disposition", "")
    assert csv_res.headers["content-disposition"].endswith('.csv"')
    body_lines = [line for line in csv_res.text.strip().splitlines() if line.strip()]
    assert len(body_lines) == 3 + 1  # 3 行数据 + 表头
    assert body_lines[0].startswith("id,created_at,feature")

    json_res = client.get("/ai/audit/export?days=7&format=json")
    payload = json.loads(json_res.text)
    assert payload["count"] == 3
    assert payload["days"] == 7
    assert len(payload["rows"]) == 3

    # 密钥绝不导出（两种格式都查）
    assert "sk-secret-should-not-export" not in csv_res.text
    assert "sk-secret-should-not-export" not in json_res.text

    bad = client.get("/ai/audit/export?format=xml")
    assert bad.status_code == 400


def test_usage_endpoint(app_module, client):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        _log(conn, ok=1, feature="brief", duration_ms=500)

    res = client.get("/ai/usage?days=7")
    assert res.status_code == 200
    body = res.json()
    assert body["calls"]["attempted"] == 1
    assert body["days"] == 7
    assert body["by_feature"][0]["feature"] == "brief"

    # 非数字 days：FastAPI 的类型校验（与其它端点一致）
    assert client.get("/ai/usage?days=abc").status_code == 422
