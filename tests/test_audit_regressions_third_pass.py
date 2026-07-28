"""Third-pass audit regressions for correction and restore invariants."""
import io
import sqlite3


def _tx(date, direction, *, code, quantity=100, price=10):
    return {
        "date": date,
        "code": code,
        "name": "三审标的",
        "category": "A股权益",
        "account": "华泰证券",
        "direction": direction,
        "quantity": quantity,
        "price": price,
        "amount": quantity * price,
        "fee": 0,
        "remark": "third audit",
    }


def test_future_correction_does_not_fund_earlier_sell(client):
    correction = client.post(
        "/holding-corrections",
        json={
            "date": "2026-05-01",
            "code": "FUTCOR",
            "name": "三审标的",
            "category": "A股权益",
            "actual_quantity": 100,
            "actual_avg_cost": 10,
            "actual_total_dividend": 0,
        },
    )
    assert correction.status_code == 200, correction.text

    sell = client.post(
        "/transactions",
        json=_tx("2026-04-01", "卖出", code="FUTCOR"),
    )
    assert sell.status_code == 400
    assert "持仓" in sell.text


def test_restore_rejects_core_tables_with_wrong_columns_and_keeps_live_db(client, tmp_path):
    created = client.post("/deposits", json={"bank_name": "保留数据", "amount": 1000})
    assert created.status_code == 200, created.text

    malformed = tmp_path / "malformed.db"
    conn = sqlite3.connect(malformed)
    conn.execute("CREATE TABLE transactions(x TEXT)")
    conn.execute("CREATE TABLE holdings(x TEXT)")
    conn.execute("CREATE TABLE deposits(x TEXT)")
    conn.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO settings(key, value) VALUES ('schema_version', '9')")
    conn.commit()
    conn.close()

    response = client.post(
        "/maintenance/restore-upload",
        files={"file": ("malformed.db", io.BytesIO(malformed.read_bytes()), "application/octet-stream")},
    )
    assert response.status_code == 400, response.text
    deposits = client.get("/deposits")
    assert deposits.status_code == 200, deposits.text
    assert any(row["bank_name"] == "保留数据" for row in deposits.json())


def test_broker_reconcile_rejects_negative_dividend(client):
    response = client.post(
        "/broker-reconcile/apply",
        json={
            "items": [
                {
                    "date": "2026-07-01",
                    "code": "BRKNEG",
                    "name": "三审标的",
                    "category": "A股权益",
                    "actual_quantity": 100,
                    "actual_avg_cost": 10,
                    "actual_total_dividend": -500,
                }
            ]
        },
    )
    assert response.status_code == 400
    assert "分红" in response.text


def test_broker_reconcile_cannot_make_later_sell_oversold(client):
    code = "BRKHIS"
    assert client.post("/transactions", json=_tx("2026-01-01", "买入", code=code)).status_code == 200
    assert client.post("/transactions", json=_tx("2026-06-01", "卖出", code=code)).status_code == 200

    response = client.post(
        "/broker-reconcile/apply",
        json={
            "items": [
                {
                    "date": "2026-05-01",
                    "code": code,
                    "name": "三审标的",
                    "category": "A股权益",
                    "actual_quantity": 50,
                    "actual_avg_cost": 10,
                    "actual_total_dividend": 0,
                }
            ]
        },
    )
    assert response.status_code == 400
    assert "持仓" in response.text
