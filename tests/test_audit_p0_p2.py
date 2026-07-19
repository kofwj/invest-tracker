"""Regression for structural audit fixes (P0–P2)."""
from datetime import date


def test_portfolio_cash_flow_normalizes_and_rejects_bad_type(client):
    bad = client.post(
        "/portfolio-cash-flows",
        json={"date": "2026-07-01", "flow_type": "银证转入", "amount": 1000},
    )
    assert bad.status_code == 400

    zero = client.post(
        "/portfolio-cash-flows",
        json={"date": "2026-07-01", "flow_type": "投入", "amount": 0},
    )
    assert zero.status_code == 400

    ok = client.post(
        "/portfolio-cash-flows",
        json={"date": "2026-07-01", "flow_type": "投入", "amount": -50000},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["amount"] == 50000
    assert body["flow_type"] == "投入"

    rows = client.get("/portfolio-cash-flows").json()
    assert len(rows) == 1
    assert rows[0]["amount"] == 50000

    fid = rows[0]["id"]
    upd = client.put(
        f"/portfolio-cash-flows/{fid}",
        json={"flow_type": "取出", "amount": -2000},
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["flow_type"] == "取出"
    assert upd.json()["amount"] == 2000


def test_evening_brief_get_never_pushes_even_with_query(client, monkeypatch):
    """GET /evening-brief 永不推送；POST /evening-brief/notify 才推送。"""
    # 先触发一次 import，再 patch 已加载的 portfolio_helpers
    warm = client.get("/evening-brief")
    assert warm.status_code == 200, warm.text

    import sys

    flags = []

    def fake_send(conn, *, webhook=None, notify=True):
        flags.append(bool(notify))
        return {
            "text": "【晚间简报】测试",
            "headline": "测试",
            "notify": {"sent": bool(notify), "reason": "test"},
        }

    patched = False
    for name, mod in list(sys.modules.items()):
        if not mod or not hasattr(mod, "send_evening_brief"):
            continue
        if name.endswith("portfolio_helpers") or getattr(mod, "__name__", "").endswith(
            "portfolio_helpers"
        ):
            monkeypatch.setattr(mod, "send_evening_brief", fake_send)
            patched = True
    assert patched, "portfolio_helpers not loaded"

    g = client.get("/evening-brief?notify=true")
    assert g.status_code == 200, g.text
    assert flags and flags[-1] is False

    p = client.post("/evening-brief/notify")
    assert p.status_code == 200, p.text
    assert flags[-1] is True


def test_add_transaction_default_backup_flag(client, tmp_path, monkeypatch):
    # 先触发路由模块加载
    client.get("/transactions")
    called = {"n": 0}

    def fake_backup(label):
        called["n"] += 1
        return str(tmp_path / f"{label}.bak")

    import sys

    patched = False
    for name, mod in list(sys.modules.items()):
        if not mod or not hasattr(mod, "create_safety_backup"):
            continue
        if name.endswith("routers_transactions") or getattr(mod, "__name__", "").endswith(
            "routers_transactions"
        ):
            monkeypatch.setattr(mod, "create_safety_backup", fake_backup)
            patched = True
    assert patched

    res = client.post(
        "/transactions?backup=true",
        json={
            "date": date.today().isoformat(),
            "code": "601288",
            "name": "农业银行",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 100,
            "price": 6.0,
            "amount": 600,
            "fee": 0,
            "remark": "audit",
        },
    )
    assert res.status_code == 200, res.text
    assert called["n"] == 1
    assert res.json().get("backup")

    res2 = client.post(
        "/transactions?backup=false",
        json={
            "date": date.today().isoformat(),
            "code": "601288",
            "name": "农业银行",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 100,
            "price": 6.0,
            "amount": 600,
            "fee": 0,
            "remark": "audit2",
        },
    )
    assert res2.status_code == 200, res2.text
    assert called["n"] == 1
