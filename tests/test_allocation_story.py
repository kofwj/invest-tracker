import sqlite3

from allocation_analysis import build_allocation_story
from discipline import build_discipline_report


def _seed_gree_heavy_portfolio(client, app_module, cash_base=200000, deposit=50000, qty=2000, price=40):
    conn = sqlite3.connect(app_module.DB_PATH)
    app_module.set_setting(conn, "securities_cash_base", cash_base)
    app_module.set_setting(conn, "securities_cash", cash_base)
    conn.execute(
        "INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark) VALUES (?,?,?,?,?)",
        ("测试银行", deposit, 2.0, "2027-01-01", "t"),
    )
    conn.commit()
    conn.close()

    r = client.post(
        "/transactions",
        json={
            "date": "2026-01-02",
            "code": "000651",
            "name": "格力电器",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": qty,
            "price": price,
            "amount": qty * price,
            "fee": 0,
            "remark": "",
        },
    )
    assert r.status_code == 200, r.text

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE holdings SET last_price = ? WHERE code = '000651'", (price,))
    conn.commit()
    conn.close()


def test_allocation_story_endpoint_shape(client, app_module):
    _seed_gree_heavy_portfolio(client, app_module)
    r = client.get("/allocation/story")
    assert r.status_code == 200, r.text
    data = r.json()
    for key in (
        "headline",
        "severity",
        "bullets",
        "policy",
        "snapshot",
        "gaps",
        "health",
        "issues",
        "concentration",
        "homogeneity",
        "profit_dependency",
        "liquidity",
        "scenarios",
    ):
        assert key in data, key
    assert isinstance(data["bullets"], list)
    assert isinstance(data["health"], list)
    assert len(data["scenarios"]) == 3


def test_story_snapshot_matches_discipline(client, app_module):
    _seed_gree_heavy_portfolio(client, app_module)
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    report = build_discipline_report(conn)
    story = build_allocation_story(conn)
    conn.close()
    for k in ("equity_pct", "fixed_income_pct", "deposit_pct", "defensive_pct", "total_assets"):
        assert story["snapshot"][k] == report["snapshot"][k], k


def test_story_health_uses_policy_bounds(client, app_module):
    _seed_gree_heavy_portfolio(client, app_module, cash_base=50000, deposit=10000, qty=5000, price=40)
    # Force tight equity max so health shows 偏高
    saved = client.put("/discipline/policy", json={"equity_max_pct": 10, "equity_min_pct": 5})
    assert saved.status_code == 200, saved.text

    r = client.get("/allocation/story")
    assert r.status_code == 200
    data = r.json()
    equity_health = next(h for h in data["health"] if h["code"] == "equity_band")
    assert equity_health["status"] == "偏高"
    assert equity_health["level"] == "warning"
    assert data["policy"]["equity_max_pct"] == 10


def test_story_scenarios_equity_shock_formula(client, app_module):
    _seed_gree_heavy_portfolio(client, app_module)
    r = client.get("/allocation/story")
    data = r.json()
    eq_mv = float(data["snapshot"]["equity_mv"])
    total = float(data["snapshot"]["total_assets"])
    sc10 = next(s for s in data["scenarios"] if s["equity_shock_pct"] == -10)
    assert sc10["estimated_pnl"] == round(eq_mv * -0.10, 2)
    assert sc10["estimated_total_assets"] == round(total + sc10["estimated_pnl"], 2)
    assert "假设" in sc10["assumption"] or "非预测" in sc10["assumption"]


def test_story_gaps_amount_from_pct(client, app_module):
    _seed_gree_heavy_portfolio(client, app_module)
    r = client.get("/allocation/story")
    data = r.json()
    total = float(data["snapshot"]["total_assets"])
    assert data["gaps"]["equity_amount"] == round(total * data["gaps"]["equity_pct"] / 100.0, 2)


def test_story_liquidity_counts_near_due_deposit(client, app_module):
    from database import local_today_iso
    from datetime import datetime, timedelta

    today = local_today_iso()
    near = (datetime.strptime(today, "%Y-%m-%d").date() + timedelta(days=10)).isoformat()
    conn = sqlite3.connect(app_module.DB_PATH)
    app_module.set_setting(conn, "securities_cash_base", 10000)
    app_module.set_setting(conn, "securities_cash", 10000)
    conn.execute(
        "INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark) VALUES (?,?,?,?,?)",
        ("近端行", 8000, 2.0, near, "near"),
    )
    conn.execute(
        "INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark) VALUES (?,?,?,?,?)",
        ("远端行", 90000, 2.0, "2030-01-01", "far"),
    )
    conn.commit()
    conn.close()

    r = client.get("/allocation/story")
    data = r.json()
    assert data["liquidity"]["deposit_due_30d_amount"] == 8000
    assert data["liquidity"]["deposit_due_30d_count"] == 1
    assert data["liquidity"]["deployable_30d"] == 10000 + 8000
