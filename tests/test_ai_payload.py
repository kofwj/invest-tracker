import json

from ai_payload import ALLOWED_KEYS, build_payload, round_amount, validate_output


def _walk_values(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_values(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_values(v, out)
    else:
        out.append(obj)


def test_allowed_keys_exact():
    brief = build_payload(
        "brief",
        as_of="2026-09-24",
        day_pnl_amount=-32150,
        counts={"up": 2, "down": 6},
        movers=[{"code": "000651", "name": "格力", "contribution": -3, "change_pct": -2.1}],
        benchmark={"name": "沪深300", "change_pct": -1.2},
        discipline_breach_count=1,
        plans=[{"title": "减仓"}],
        reasons=[{"title": "某标题"}],
        moves=[],
        reason_coverage={"matched": 1, "window_days": 2, "note": "x"},
    )
    assert set(brief) == ALLOWED_KEYS["brief"]

    alert = build_payload(
        "alert_note",
        trigger={"code": "000651", "change_pct": -2.1},
        portfolio_direction="down",
        peers=[],
        benchmark={"change_pct": -1.2},
        reasons=[],
        moves=[],
    )
    assert set(alert) == ALLOWED_KEYS["alert_note"]

    nl = build_payload("nl_rule", utterance="把格力减到 10%", available_codes=["000651"])
    assert set(nl) == ALLOWED_KEYS["nl_rule"]


def test_portfolio_pct_cannot_appear():
    portfolio_pct = -1.83
    payload = build_payload(
        "brief",
        as_of="2026-09-24",
        day_pnl_amount=-32000,
        counts={},
        movers=[],
        benchmark={"change_pct": -1.2},
        portfolio_pct=portfolio_pct,
        day_pnl_pct=portfolio_pct,
    )
    values = []
    _walk_values(payload, values)
    assert portfolio_pct not in values
    assert "portfolio_pct" not in payload
    assert "day_pnl_pct" not in payload


def test_amount_rounded_to_thousand():
    payload = build_payload("brief", day_pnl_amount=-32150)
    assert payload["day_pnl_amount_rounded"] % 1000 == 0
    assert payload["day_pnl_amount_rounded"] == round_amount(-32150)


def test_forbidden_holding_numbers_absent():
    holdings = {
        "code": "000651",
        "quantity": 8000,
        "avg_cost": 38.25,
        "diluted_cost": 36.1,
        "market_value": 292000,
        "total_assets": 1750000,
    }
    payload = build_payload(
        "brief",
        as_of="2026-09-24",
        day_pnl_amount=-32000,
        movers=[{"code": "000651", "name": "格力", "contribution": -2, "market_value": 292000, "quantity": 8000}],
        counts=holdings,
        total_assets=1750000,
    )
    blob = json.dumps(payload, ensure_ascii=False)
    for n in (8000, 38.25, 36.1, 292000, 1750000):
        assert str(n) not in blob


def test_movers_sorted_by_contribution():
    payload = build_payload(
        "brief",
        movers=[
            {"code": "a", "name": "A", "contribution": -1},
            {"code": "b", "name": "B", "contribution": -5},
            {"code": "c", "name": "C", "contribution": -2},
        ],
    )
    assert [m["code"] for m in payload["movers"]] == ["b", "c", "a"]
    assert all("contribution" not in m for m in payload["movers"])


def test_source_must_match_title():
    payload = {"reasons": [{"title": "农行人事公告"}], "moves": []}
    bad = validate_output("brief", "受此影响 [并不存在的标题]", payload)
    assert bad["ok"] is False
    good = validate_output("brief", "今日无新增公告 [农行人事公告]", payload)
    assert good["ok"] is True


def test_numbers_must_trace():
    payload = build_payload("brief", day_pnl_amount=-32000)
    ok = validate_output("brief", "今天亏了 3.2 万", payload)
    assert ok["ok"] is True
    bad = validate_output("brief", "今天亏了 5 万", payload)
    assert bad["ok"] is False


def test_speculation_wording():
    payload = {"reasons": [{"title": "某标题"}], "moves": []}
    bad = validate_output("brief", "可能受市场情绪影响", payload)
    assert bad["ok"] is False
    good = validate_output("brief", "今日无新增公告 [某标题]", payload)
    assert good["ok"] is True


def test_causal_wording():
    payload = {"reasons": [{"title": "农行人事公告"}], "moves": []}
    bad = validate_output("brief", "因为人事变动导致下跌", payload)
    assert bad["ok"] is False
    assert bad["reason"] == "causal_claim"
    cited = validate_output("brief", "同期有这些信息 [农行人事公告]", payload)
    assert cited["ok"] is True
    dup = validate_output("brief", "因为人事变动导致下跌", payload)
    assert dup["warnings"].count(dup["warnings"][0]) == 1


def test_empty_reasons_unfound_is_ok():
    payload = build_payload("brief", reasons=[], moves=[])
    r = validate_output("brief", "未找到相关公告", payload)
    assert r["ok"] is True


def test_zero_counts_do_not_mean_all_flat():
    payload = build_payload(
        "brief",
        counts={"up": 0, "down": 0, "flat": 0, "holdings": 8},
    )
    bad = validate_output("brief", "今天持仓全部持平", payload)
    assert bad["ok"] is False
    assert bad["reason"] == "unsupported_flat"
    good = validate_output("brief", "未找到相关公告或新闻", payload)
    assert good["ok"] is True


def test_plan_extra_keys_dropped():
    payload = build_payload(
        "brief",
        plans=[
            {
                "title": "减仓",
                "level": "warning",
                "remaining_amount": 50000,
                "current_pct": 12.3,
                "target_pct": 8,
                "symbol": "000651",
                "code": "000651",
            }
        ],
        counts={"up": 1, "down": 2, "quantity": 8000, "market_value": 292000},
    )
    blob = json.dumps(payload, ensure_ascii=False)
    assert "remaining_amount" not in blob
    assert "current_pct" not in blob
    assert "target_pct" not in blob
    assert "50000" not in blob
    assert "12.3" not in blob
    assert payload["plans"][0]["code"] == "000651"
    assert payload["plans"][0]["title"] == "减仓"
    assert payload["plans"][0]["level"] == "warning"


def test_invented_and_six_digit_amounts_rejected():
    payload = build_payload("brief", day_pnl_amount=-32000)
    small = validate_output("brief", "今天亏了 900 元", payload)
    assert small["ok"] is False
    six = validate_output("brief", "今天亏了 123456", payload)
    assert six["ok"] is False

