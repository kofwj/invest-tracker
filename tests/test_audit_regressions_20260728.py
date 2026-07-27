import io
import math
import sqlite3
from pathlib import Path


def tx(date, direction, *, code="TEST01", quantity=100, price=10, amount=1000, fee=0):
    return {
        "date": date,
        "code": code,
        "name": "测试资产",
        "category": "A股权益",
        "account": "华泰证券",
        "direction": direction,
        "quantity": quantity,
        "price": price,
        "amount": amount,
        "fee": fee,
        "remark": "regression",
    }


def test_transaction_rejects_inconsistent_or_zero_trade_amount(client):
    assert client.post("/transactions", json=tx("2026-07-01", "买入", amount=1)).status_code == 400
    assert client.post("/transactions", json=tx("2026-07-01", "买入", price=0, amount=0)).status_code == 400

    ok = client.post("/transactions", json=tx("2026-07-01", "买入"))
    assert ok.status_code == 200, ok.text
    assert client.post("/transactions", json=tx("2026-07-02", "卖出", amount=1)).status_code == 400


def test_transaction_rejects_historical_oversell(client):
    assert client.post("/transactions", json=tx("2026-05-01", "买入")).status_code == 200
    bad = client.post("/transactions", json=tx("2026-04-01", "卖出"))
    assert bad.status_code == 400
    assert "历史" in bad.text or "持仓" in bad.text


def test_transaction_validator_rejects_non_finite(app_module):
    import holding_calculator

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    for value in (math.nan, math.inf, -math.inf):
        try:
            holding_calculator.validate_transaction_payload(
                conn,
                direction="买入",
                code="TEST01",
                quantity=100,
                price=10,
                amount=value,
                fee=0,
                transaction_date="2026-07-01",
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"non-finite amount accepted: {value}")
    conn.close()


def test_deposit_rejects_bad_amount_rate_and_dates(client):
    assert client.post("/deposits", json={"bank_name": "坏本金", "amount": -1}).status_code == 422
    assert client.post("/deposits", json={"bank_name": "坏利率", "amount": 100, "interest_rate": -1}).status_code == 422
    assert client.post(
        "/deposits",
        json={"bank_name": "坏日期", "amount": 100, "start_date": "bad", "due_date": "2026-12-01"},
    ).status_code == 422
    assert client.post(
        "/deposits",
        json={"bank_name": "倒序", "amount": 100, "start_date": "2026-12-02", "due_date": "2026-12-01"},
    ).status_code == 422


def test_restore_rejects_unrelated_sqlite_and_keeps_live_db(client, app_module, tmp_path):
    unrelated = tmp_path / "unrelated.db"
    conn = sqlite3.connect(unrelated)
    conn.execute("CREATE TABLE unrelated(x TEXT)")
    conn.commit()
    conn.close()

    response = client.post(
        "/maintenance/restore-upload",
        files={"file": ("unrelated.db", unrelated.read_bytes(), "application/octet-stream")},
    )
    assert response.status_code == 400, response.text
    assert client.get("/dashboard").status_code == 200


def test_safety_backups_never_overwrite_same_second(app_module):
    from csv_utils import create_safety_backup

    first = Path(create_safety_backup("same_action"))
    second = Path(create_safety_backup("same_action"))
    assert first != second
    assert first.exists() and second.exists()


def test_discipline_draft_update_rejects_duplicate_open_side(client):
    actions = [
        {"side": "buy", "code": "159352", "name": "A500", "amount": 1000},
        {"side": "sell", "code": "159352", "name": "A500", "amount": 1000, "quantity": 10, "price": 100},
    ]
    created = client.post("/discipline/drafts", json={"actions": actions})
    assert created.status_code == 200, created.text
    drafts = client.get("/discipline/drafts").json()
    buy = next(d for d in drafts if d["side"] == "buy")
    sell = next(d for d in drafts if d["side"] == "sell")
    response = client.put(f"/discipline/drafts/{sell['id']}", json={"side": "buy"})
    assert response.status_code == 400
    assert client.get(f"/discipline/drafts").status_code == 200


def test_discipline_draft_rejects_invalid_date(client):
    created = client.post(
        "/discipline/drafts",
        json={"actions": [{"side": "buy", "code": "159352", "name": "A500", "amount": 1000}]},
    ).json()
    draft_id = (created.get("created") or created.get("updated"))[0]["id"]
    assert client.put(f"/discipline/drafts/{draft_id}", json={"date": "not-a-date"}).status_code == 422


def test_health_returns_503_when_database_is_degraded(client, monkeypatch):
    import sys

    patched = False
    for mod in list(sys.modules.values()):
        if mod and hasattr(mod, "check_database_health") and hasattr(mod, "health_payload"):
            monkeypatch.setattr(mod, "check_database_health", lambda: "degraded")
            patched = True
    assert patched
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
