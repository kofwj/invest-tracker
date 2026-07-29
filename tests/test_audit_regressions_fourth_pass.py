"""Fourth-pass deep audit regressions for sibling writers and restore compatibility."""
import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor


def _tx(date, direction, *, code="DEEP", quantity=100, price=10):
    return {
        "date": date,
        "code": code,
        "name": "深审标的",
        "category": "A股权益",
        "account": "华泰证券",
        "direction": direction,
        "quantity": quantity,
        "price": price,
        "amount": quantity * price,
        "fee": 0,
        "remark": "fourth audit",
    }


def _create_restore_candidate(path, *, schema_version="9", broken_discipline=False):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, date TEXT, code TEXT, name TEXT, direction TEXT, quantity REAL, price REAL, amount REAL, fee REAL)")
    conn.execute("CREATE TABLE holdings (id INTEGER PRIMARY KEY, code TEXT, name TEXT, quantity REAL, avg_cost REAL, diluted_cost REAL, total_dividend REAL, last_price REAL)")
    conn.execute("CREATE TABLE deposits (id INTEGER PRIMARY KEY, bank_name TEXT, amount REAL, interest_rate REAL, due_date TEXT)")
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO settings(key, value) VALUES ('schema_version', ?)", (schema_version,))
    if broken_discipline:
        conn.execute("CREATE TABLE discipline_drafts (id INTEGER PRIMARY KEY, wrong TEXT)")
    conn.commit()
    conn.close()


def test_discipline_confirm_rejects_backdated_sell_that_breaks_later_history(client):
    code = "DRFTHIST"
    assert client.post("/transactions", json=_tx("2026-01-01", "买入", code=code)).status_code == 200
    assert client.post("/transactions", json=_tx("2026-06-01", "卖出", code=code)).status_code == 200
    assert client.post("/transactions", json=_tx("2026-07-01", "买入", code=code)).status_code == 200

    created = client.post(
        "/discipline/drafts",
        json={"actions": [{
            "side": "sell", "code": code, "name": "深审标的", "category": "A股权益",
            "account": "华泰证券", "quantity": 100, "price": 10, "amount": 1000,
        }]},
    )
    assert created.status_code == 200, created.text
    draft_id = created.json()["created"][0]["id"]
    assert client.put(f"/discipline/drafts/{draft_id}", json={"date": "2026-05-01"}).status_code == 200

    response = client.post(f"/discipline/drafts/{draft_id}/confirm")
    assert response.status_code == 400, response.text
    rows = client.get(f"/transactions?code={code}").json()["items"]
    assert len(rows) == 3


def test_portfolio_cash_flow_rejects_non_finite_amount(client):
    response = client.post(
        "/portfolio-cash-flows",
        content='{"date":"2026-07-01","flow_type":"投入","amount":NaN}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code in (400, 422), response.text
    assert client.get("/portfolio-cash-flows").json() == []


def test_securities_cash_rejects_non_finite_amount(client):
    response = client.put(
        "/securities-cash",
        content='{"amount":NaN}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code in (400, 422), response.text


def test_manual_cash_flow_rejects_non_finite_amount(client):
    response = client.post(
        "/cash-flows",
        content='{"date":"2026-07-01","flow_type":"银证转入","amount":NaN}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code in (400, 422), response.text
    assert client.get("/cash-flows").json() == []


def test_dividend_csv_rejects_non_finite_amount_and_fee(client):
    csv_data = (
        "date,code,name,amount,fee\n"
        "2026-07-01,600001,深审标的,nan,0\n"
        "2026-07-02,600001,深审标的,100,nan\n"
    ).encode()
    response = client.post(
        "/dividends/import",
        files={"file": ("dividends.csv", io.BytesIO(csv_data), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 0
    assert response.json()["failed"] == 2


def test_restore_rejects_future_schema_version_and_keeps_live_data(client, tmp_path):
    assert client.post("/deposits", json={"bank_name": "保留数据", "amount": 1000}).status_code == 200
    candidate = tmp_path / "future.db"
    _create_restore_candidate(candidate, schema_version="999")

    response = client.post(
        "/maintenance/restore-upload",
        files={"file": ("future.db", io.BytesIO(candidate.read_bytes()), "application/octet-stream")},
    )
    assert response.status_code == 400, response.text
    assert any(row["bank_name"] == "保留数据" for row in client.get("/deposits").json())


def test_restore_dry_runs_full_schema_before_replacing_live_db(client, tmp_path):
    assert client.post("/deposits", json={"bank_name": "恢复失败也保留", "amount": 1000}).status_code == 200
    candidate = tmp_path / "broken-aux.db"
    _create_restore_candidate(candidate, schema_version="0", broken_discipline=True)

    response = client.post(
        "/maintenance/restore-upload",
        files={"file": ("broken-aux.db", io.BytesIO(candidate.read_bytes()), "application/octet-stream")},
    )
    assert response.status_code == 400, response.text
    deposits = client.get("/deposits")
    assert deposits.status_code == 200, deposits.text
    assert any(row["bank_name"] == "恢复失败也保留" for row in deposits.json())


def test_future_transaction_is_rejected_before_it_changes_today(client):
    response = client.post("/transactions", json=_tx("2099-01-01", "买入", code="FUTURE"))
    assert response.status_code in (400, 422), response.text


def test_future_portfolio_flow_is_rejected(client):
    response = client.post(
        "/portfolio-cash-flows",
        json={"date": "2099-01-01", "flow_type": "投入", "amount": 1000},
    )
    assert response.status_code in (400, 422), response.text


def test_pending_purchase_fee_reduces_total_assets(client):
    assert client.put("/securities-cash", json={"amount": 0}).status_code == 200
    payload = _tx("2026-07-01", "申购待确认", code="PENDING", quantity=0, price=0)
    payload.update(amount=1000, fee=10)
    assert client.post("/transactions", json=payload).status_code == 200
    dashboard = client.get("/dashboard").json()
    assert dashboard["pending_purchase"] == 1000
    assert dashboard["securities_cash"] == -1010
    assert dashboard["total_assets"] == -10


def test_restore_rejects_malformed_schema_version(client, tmp_path):
    candidate = tmp_path / "malformed.db"
    _create_restore_candidate(candidate, schema_version="garbage")
    response = client.post(
        "/maintenance/restore-upload",
        files={"file": ("malformed.db", io.BytesIO(candidate.read_bytes()), "application/octet-stream")},
    )
    assert response.status_code == 400, response.text


def test_concurrent_safety_backups_use_unique_paths(app_module):
    import csv_utils

    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda _: csv_utils.create_safety_backup("race"), range(8)))
    assert len(set(paths)) == len(paths)
    for path in paths:
        with sqlite3.connect(path) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
