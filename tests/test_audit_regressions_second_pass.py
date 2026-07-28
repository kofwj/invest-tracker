"""Second-pass audit regressions for cross-record invariants."""
import io


def tx(date, direction, *, code="AUDIT02", quantity=100, price=10, amount=None):
    return {
        "date": date,
        "code": code,
        "name": "审计标的",
        "category": "A股权益",
        "account": "华泰证券",
        "direction": direction,
        "quantity": quantity,
        "price": price,
        "amount": quantity * price if amount is None else amount,
        "fee": 0,
        "remark": "second audit",
    }


def _seed_round_trip(client, code):
    buy = client.post("/transactions", json=tx("2026-01-01", "买入", code=code))
    assert buy.status_code == 200, buy.text
    rows_response = client.get("/transactions", params={"legacy": True, "code": code})
    assert rows_response.status_code == 200, rows_response.text
    rows = rows_response.json()
    buy_id = next(row["id"] for row in rows if row["direction"] == "买入")
    sell = client.post("/transactions", json=tx("2026-02-01", "卖出", code=code))
    assert sell.status_code == 200, sell.text
    return buy_id


def test_update_earlier_buy_cannot_make_later_sell_oversold(client):
    buy_id = _seed_round_trip(client, "AUDUPD")
    response = client.put(
        f"/transactions/{buy_id}",
        json={"quantity": 50, "amount": 500},
    )
    assert response.status_code == 400
    assert "后续" in response.text or "超卖" in response.text or "持仓" in response.text


def test_delete_earlier_buy_cannot_make_later_sell_oversold(client):
    buy_id = _seed_round_trip(client, "AUDDEL")
    response = client.delete(f"/transactions/{buy_id}")
    assert response.status_code == 400
    assert "后续" in response.text or "超卖" in response.text or "持仓" in response.text


def test_deposit_partial_update_validates_merged_date_order(client):
    created = client.post(
        "/deposits",
        json={
            "bank_name": "审计存款",
            "amount": 1000,
            "start_date": "2026-01-01",
            "due_date": "2026-12-31",
        },
    )
    assert created.status_code == 200, created.text
    response = client.put(
        f"/deposits/{created.json()['id']}",
        json={"start_date": "2027-01-01"},
    )
    assert response.status_code == 422


def test_holding_correction_cannot_make_later_sell_oversold(client):
    _seed_round_trip(client, "AUDCOR")
    response = client.post(
        "/holding-corrections",
        json={
            "date": "2026-01-15",
            "code": "AUDCOR",
            "name": "审计标的",
            "category": "A股权益",
            "actual_quantity": 50,
            "actual_avg_cost": 10,
            "actual_total_dividend": 0,
        },
    )
    assert response.status_code == 400
    assert "持仓" in response.text


def test_add_historical_sell_cannot_make_later_sell_oversold(client):
    code = "AUDADD"
    assert client.post("/transactions", json=tx("2026-01-01", "买入", code=code)).status_code == 200
    assert client.post(
        "/transactions",
        json=tx("2026-03-01", "卖出", code=code, quantity=60, amount=600),
    ).status_code == 200
    response = client.post(
        "/transactions",
        json=tx("2026-02-01", "卖出", code=code, quantity=50, amount=500),
    )
    assert response.status_code == 400
    assert "持仓" in response.text


def test_import_historical_sell_rolls_back_invalid_row(client):
    code = "AUDCSV"
    assert client.post("/transactions", json=tx("2026-01-01", "买入", code=code)).status_code == 200
    assert client.post(
        "/transactions",
        json=tx("2026-03-01", "卖出", code=code, quantity=60, amount=600),
    ).status_code == 200
    csv_data = (
        "日期,代码,名称,类别,账户,方向,数量,价格,金额,手续费,备注\n"
        f"2026-02-01,{code},审计标的,A股权益,华泰证券,卖出,50,10,500,0,invalid\n"
    ).encode("utf-8-sig")
    response = client.post(
        "/transactions/import",
        files={"file": ("transactions.csv", io.BytesIO(csv_data), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 0
    rows = client.get("/transactions", params={"legacy": True, "code": code}).json()
    assert len(rows) == 2


def test_restore_valid_backup_replaces_live_data_and_stays_healthy(client):
    backup_response = client.post("/maintenance/backups")
    assert backup_response.status_code == 200, backup_response.text
    filename = backup_response.json()["filename"]
    created = client.post(
        "/deposits",
        json={"bank_name": "恢复前新增", "amount": 1000},
    )
    assert created.status_code == 200, created.text
    assert any(row["bank_name"] == "恢复前新增" for row in client.get("/deposits").json())

    restored = client.post("/maintenance/restore", json={"filename": filename})
    assert restored.status_code == 200, restored.text
    assert not any(row["bank_name"] == "恢复前新增" for row in client.get("/deposits").json())
    assert client.get("/health").status_code == 200
