from broker_reconcile import compare_holdings, parse_broker_csv_text


def test_parse_simple_csv():
    text = "code,name,quantity,avg_cost,total_dividend\n600000,浦发银行,100,10.5,12\n"
    rows, meta = parse_broker_csv_text(text)
    assert meta.get("row_count") == 1
    assert rows[0]["code"] == "600000"
    assert rows[0]["quantity"] == 100
    assert abs(rows[0]["avg_cost"] - 10.5) < 1e-9


def test_parse_huatai_like_headers():
    text = "证券代码,证券名称,证券数量,成本价\n601288,农业银行,\"1,000\",6.230\n"
    rows, meta = parse_broker_csv_text(text)
    assert len(rows) == 1
    assert rows[0]["code"] == "601288"
    assert rows[0]["quantity"] == 1000
    assert abs(rows[0]["avg_cost"] - 6.23) < 1e-9


def test_compare_holdings_mismatch_and_only_sides():
    broker = [
        {"code": "600000", "name": "浦发", "quantity": 120, "avg_cost": 10.0, "total_dividend": 0},
        {"code": "601288", "name": "农行", "quantity": 100, "avg_cost": 6.0, "total_dividend": 0},
    ]
    app = [
        {"code": "600000", "name": "浦发", "quantity": 100, "avg_cost": 10.0, "total_dividend": 0, "category": "A股权益"},
        {"code": "000001", "name": "平安", "quantity": 50, "avg_cost": 12.0, "total_dividend": 0, "category": "A股权益"},
    ]
    result = compare_holdings(broker, app, as_of_date="2026-07-14")
    assert result["diff_count"] >= 2
    statuses = {d["code"]: d["status"] for d in result["diffs"]}
    assert statuses["600000"] == "mismatch"
    assert statuses["601288"] == "only_broker"
    assert statuses["000001"] == "only_app"
    codes = {s["code"] for s in result["suggestions"]}
    assert "600000" in codes and "601288" in codes and "000001" in codes
    zero = next(s for s in result["suggestions"] if s["code"] == "000001")
    assert zero["actual_quantity"] == 0


def test_broker_reconcile_preview_and_apply(client, app_module):
    client.post(
        "/transactions",
        json={
            "date": "2026-01-02",
            "code": "600000",
            "name": "浦发银行",
            "category": "A股权益",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 100,
            "price": 10,
            "amount": 1000,
            "fee": 0,
            "remark": "",
        },
    )
    csv_body = "证券代码,证券名称,证券数量,成本价\n600000,浦发银行,150,10.2\n"
    files = {"file": ("ht.csv", csv_body.encode("utf-8"), "text/csv")}
    data = {"as_of_date": "2026-07-14"}
    preview = client.post("/broker-reconcile/preview", files=files, data=data)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["diff_count"] >= 1
    assert body["suggestions"]
    sug = body["suggestions"][0]
    apply = client.post(
        "/broker-reconcile/apply",
        json={
            "items": [
                {
                    "date": sug["date"],
                    "code": sug["code"],
                    "name": sug["name"],
                    "category": sug.get("category") or "A股权益",
                    "actual_quantity": sug["actual_quantity"],
                    "actual_avg_cost": sug["actual_avg_cost"],
                    "actual_total_dividend": sug.get("actual_total_dividend") or 0,
                    "remark": sug.get("remark") or "test",
                }
            ]
        },
    )
    assert apply.status_code == 200, apply.text
    assert apply.json()["applied_count"] == 1
    holdings = client.get("/holdings").json()
    row = next(h for h in holdings if h["code"] == "600000")
    assert abs(float(row["quantity"]) - 150) < 1e-6
