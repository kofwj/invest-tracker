"""分类自动补齐（新增/编辑/一次性回填）+ 一键全量导出（/maintenance/export-all）回归测试。

覆盖：
1. 手工新增不带 category 的交易 → 落库后有推断分类；
2. 显式传了 category → 不被覆盖；
3. backfill-category：只填空值、已有分类逐字段不变、updated/remaining 正确；
4. backfill 幂等；
5. export-all 的 zip 清单、invest.db 一致性、transactions.csv 表头与行数；
6. 导出不改数据。
"""
import csv
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from datetime import datetime

import pytest

EXPORT_MEMBERS = {
    "transactions.csv",
    "holdings.csv",
    "deposits.csv",
    "daily_snapshots.csv",
    "portfolio_cash_flows.csv",
    "cash_flows.csv",
    "invest.db",
    "README.txt",
}

TRANSACTION_INSERT = (
    "INSERT INTO transactions (date, code, name, category, account, direction, "
    "quantity, price, amount, fee, remark) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _connect(app_module):
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _insert_transaction(app_module, *, date, code, name, category, remark="legacy"):
    conn = _connect(app_module)
    cur = conn.execute(
        TRANSACTION_INSERT,
        (date, code, name, category, "华泰证券", "买入", 100, 10.0, 1000.0, 5.0, remark),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def _transaction_rows(app_module):
    conn = _connect(app_module)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM transactions ORDER BY id").fetchall()]
    finally:
        conn.close()


def _row(app_module, row_id):
    conn = _connect(app_module)
    try:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (row_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def _digest(rows):
    blob = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _columns(app_module, table):
    conn = _connect(app_module)
    try:
        return [str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    finally:
        conn.close()


def _seed_ledger(app_module, client):
    """造一点各表数据，供 export-all 断言。"""
    conn = _connect(app_module)
    try:
        conn.execute(
            "INSERT INTO holdings (code, name, category, quantity, avg_cost, diluted_cost, "
            "total_dividend, last_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("601288", "农业银行", "A股权益", 1000, 6.0, 5.9, 12.0, 6.2),
        )
        conn.execute(
            "INSERT INTO deposits (bank_name, amount, interest_rate, start_date, due_date, remark) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("工商银行", 50000.0, 0.025, "2026-01-01", "2027-01-01", "三年期"),
        )
        conn.execute(
            "INSERT INTO daily_snapshots (date, total_assets, total_market_value, bank_balance, "
            "securities_cash, pending_purchase, total_profit, lifetime_profit, holdings_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-05-18", 120000.0, 6200.0, 50000.0, 63800.0, 0.0, 1200.0, 1200.0, 1),
        )
        conn.execute(
            "INSERT INTO daily_snapshots (date, total_assets, total_market_value, bank_balance, "
            "securities_cash, pending_purchase, total_profit, lifetime_profit, holdings_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-05-19", 121000.0, 6300.0, 50000.0, 64700.0, 0.0, 1500.0, 1500.0, 1),
        )
        conn.execute(
            "INSERT INTO portfolio_cash_flows (date, flow_type, amount, source, remark) "
            "VALUES (?, ?, ?, ?, ?)",
            ("2026-05-19", "投入", 10000.0, "manual", "追加投入"),
        )
        conn.execute(
            "INSERT INTO cash_flows (date, account, flow_type, amount, balance_before, balance_after, remark) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-05-19", "华泰证券", "银证转入", 10000.0, 53800.0, 63800.0, "银证转入"),
        )
        conn.commit()
    finally:
        conn.close()
    for idx in range(3):
        client.post(
            "/transactions",
            json={
                "date": f"2026-05-1{7 + idx}",
                "code": "601288",
                "name": "农业银行",
                "category": "A股权益",
                "account": "华泰证券",
                "direction": "买入",
                "quantity": 100,
                "price": 6.0,
                "amount": 600.0,
                "fee": 5.0,
                "remark": f"seed-{idx}",
            },
        )


# --------------------------------------------------------------------------
# 1. 新增交易时自动推断分类
# --------------------------------------------------------------------------

def test_add_transaction_infers_category_when_blank(client, app_module):
    resp = client.post(
        "/transactions",
        json={
            "date": "2026-05-19",
            "code": "601288",
            "name": "农业银行",
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 1000,
            "price": 6.0,
            "amount": 6000.0,
            "fee": 5.0,
            "remark": "没有传分类",
        },
    )
    assert resp.status_code == 200, resp.text
    rows = _transaction_rows(app_module)
    assert len(rows) == 1
    assert rows[0]["category"] == "A股权益"

    # 纯空白分类同样按空处理；场外基金代码以 f 开头 → 债基
    resp = client.post(
        "/transactions",
        json={
            "date": "2026-05-19",
            "code": "f004388",
            "name": "鹏华丰享",
            "category": "   ",
            "account": "华泰证券",
            "direction": "申购待确认",
            "quantity": 0,
            "price": 0,
            "amount": 50000.0,
            "fee": 0,
            "remark": "空白分类",
        },
    )
    assert resp.status_code == 200, resp.text
    rows = _transaction_rows(app_module)
    assert {r["code"]: r["category"] for r in rows} == {
        "601288": "A股权益",
        "f004388": "债基",
    }


# --------------------------------------------------------------------------
# 2. 显式分类不被覆盖
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "code,name,category",
    [
        ("513530", "港股通ETF", "港股ETF"),
        ("601288", "农业银行", "自建分类"),
        ("159915", "创业板ETF", "A股ETF"),
    ],
)
def test_add_transaction_keeps_explicit_category(client, app_module, code, name, category):
    resp = client.post(
        "/transactions",
        json={
            "date": "2026-05-19",
            "code": code,
            "name": name,
            "category": category,
            "account": "华泰证券",
            "direction": "买入",
            "quantity": 100,
            "price": 10.0,
            "amount": 1000.0,
            "fee": 1.0,
        },
    )
    assert resp.status_code == 200, resp.text
    rows = _transaction_rows(app_module)
    assert len(rows) == 1
    assert rows[0]["category"] == category


def test_update_transaction_infers_category_when_cleared(client, app_module):
    row_id = _insert_transaction(
        app_module, date="2026-05-19", code="159915", name="创业板ETF", category="自建分类"
    )
    resp = client.put(f"/transactions/{row_id}", json={"category": ""})
    assert resp.status_code == 200, resp.text
    assert _row(app_module, row_id)["category"] == "A股ETF"


def test_update_transaction_keeps_explicit_category(client, app_module):
    row_id = _insert_transaction(
        app_module, date="2026-05-19", code="601288", name="农业银行", category=None
    )
    resp = client.put(f"/transactions/{row_id}", json={"remark": "改备注", "category": "黄金"})
    assert resp.status_code == 200, resp.text
    after = _row(app_module, row_id)
    assert after["category"] == "黄金"
    assert after["remark"] == "改备注"


# --------------------------------------------------------------------------
# 3+4. 一次性回填
# --------------------------------------------------------------------------

def test_backfill_category_fills_blanks_only(client, app_module):
    blank_ids = [
        _insert_transaction(app_module, date="2026-04-01", code="601288", name="农业银行", category=None),
        _insert_transaction(app_module, date="2026-04-02", code="f004388", name="鹏华丰享", category=""),
        _insert_transaction(app_module, date="2026-04-03", code="159915", name="创业板ETF", category="   "),
    ]
    # 已有分类：故意给一个与推断结果不同的值，验证不会被覆盖
    existing_id = _insert_transaction(
        app_module, date="2026-04-04", code="601288", name="农业银行", category="黄金"
    )
    before = _row(app_module, existing_id)

    resp = client.post("/transactions/backfill-category")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["updated"] == 3
    assert body["remaining"] == 0

    assert _row(app_module, blank_ids[0])["category"] == "A股权益"
    assert _row(app_module, blank_ids[1])["category"] == "债基"
    assert _row(app_module, blank_ids[2])["category"] == "A股ETF"

    after = _row(app_module, existing_id)
    assert after == before
    for key in before:
        assert after[key] == before[key], f"字段 {key} 被回填改动"


def test_backfill_category_is_idempotent(client, app_module):
    _insert_transaction(app_module, date="2026-04-01", code="601288", name="农业银行", category=None)
    _insert_transaction(app_module, date="2026-04-02", code="518880", name="黄金ETF", category=None)

    first = client.post("/transactions/backfill-category")
    assert first.status_code == 200, first.text
    assert first.json()["updated"] == 2
    assert first.json()["remaining"] == 0
    snapshot = _digest(_transaction_rows(app_module))

    second = client.post("/transactions/backfill-category")
    assert second.status_code == 200, second.text
    assert second.json()["updated"] == 0
    assert second.json()["remaining"] == 0
    assert _digest(_transaction_rows(app_module)) == snapshot


def test_backfill_category_leaves_uninferable_rows(client, app_module):
    """代码和名称都为空时推不出分类：保持空值并在 remaining 里如实体现。"""
    stuck_id = _insert_transaction(app_module, date="2026-04-01", code="", name="", category=None)
    filled_id = _insert_transaction(app_module, date="2026-04-02", code="513530", name="", category=None)

    resp = client.post("/transactions/backfill-category")
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == 1
    assert resp.json()["remaining"] == 1

    assert _row(app_module, filled_id)["category"] == "港股ETF"
    stuck = _row(app_module, stuck_id)
    assert stuck["category"] is None  # 没有被写成空字符串冒充"回填成功"


# --------------------------------------------------------------------------
# 5+6. 一键全量导出
# --------------------------------------------------------------------------

def test_export_all_zip_contents(client, app_module, tmp_path):
    _seed_ledger(app_module, client)
    expected_transactions = _transaction_rows(app_module)
    conn = _connect(app_module)
    try:
        expected_snapshots = conn.execute("SELECT COUNT(*) FROM daily_snapshots").fetchone()[0]
    finally:
        conn.close()

    resp = client.get("/maintenance/export-all")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/zip")
    disposition = resp.headers["content-disposition"]
    match = re.search(r"invest-tracker-export-(\d{8})\.zip", disposition)
    assert match, disposition
    import database  # conftest 已把 backend/ 放进 sys.path；时区取当前测试库配置
    assert match.group(1) == datetime.now(database.LOCAL_TZ).strftime("%Y%m%d")

    with zipfile.ZipFile(io.BytesIO(resp.content)) as bundle:
        assert EXPORT_MEMBERS.issubset(set(bundle.namelist()))
        assert bundle.testzip() is None

        # invest.db：能被 sqlite3 打开、完整性 ok、daily_snapshots 行数与主库一致
        snapshot_path = tmp_path / "invest.db"
        snapshot_path.write_bytes(bundle.read("invest.db"))
        snap = sqlite3.connect(str(snapshot_path))
        snap.row_factory = sqlite3.Row
        try:
            assert snap.execute("PRAGMA integrity_check").fetchone()[0].lower() == "ok"
            assert snap.execute("SELECT COUNT(*) FROM daily_snapshots").fetchone()[0] == expected_snapshots
            assert snap.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == len(expected_transactions)
        finally:
            snap.close()

        # transactions.csv：utf-8-sig、首行表头、行数与主库一致
        raw = bundle.read("transactions.csv")
        assert raw.startswith(b"\xef\xbb\xbf")
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
        header = next(reader)
        assert header == _columns(app_module, "transactions")
        assert len(list(reader)) == len(expected_transactions)

        # README.txt：导出时间 + 逐列说明 + 恢复走备份/恢复功能
        readme = bundle.read("README.txt").decode("utf-8")
        assert "transactions.csv" in readme
        assert "category" in readme
        assert "大类分类" in readme
        assert "恢复请用设置页的备份/恢复功能" in readme
        export_date = f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
        assert export_date in readme


def test_export_all_does_not_modify_data(client, app_module):
    _seed_ledger(app_module, client)
    before_rows = _transaction_rows(app_module)
    conn = _connect(app_module)
    try:
        before_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "transactions",
                "holdings",
                "deposits",
                "daily_snapshots",
                "portfolio_cash_flows",
                "cash_flows",
            )
        }
    finally:
        conn.close()

    resp = client.get("/maintenance/export-all")
    assert resp.status_code == 200, resp.text

    after_rows = _transaction_rows(app_module)
    assert len(after_rows) == len(before_rows)
    assert _digest(after_rows) == _digest(before_rows)
    conn = _connect(app_module)
    try:
        after_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before_counts
        }
    finally:
        conn.close()
    assert after_counts == before_counts
