"""Tests for satellite progress + manual reconcile features."""
import sqlite3

from allocation_analysis import build_satellite_progress
from snapshots import latest_reconcile_with_gap, save_reconcile


def _conn_with_holdings(holdings):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE holdings (code TEXT, name TEXT, category TEXT, quantity REAL, "
        "last_price REAL, avg_cost REAL, diluted_cost REAL, total_dividend REAL)"
    )
    for h in holdings:
        conn.execute(
            "INSERT INTO holdings VALUES (?,?,?,?,?,?,?,?)",
            (h["code"], h["name"], h.get("category", "A股ETF"),
             h.get("quantity", 0), h.get("last_price", 0), 0, 0, 0),
        )
    return conn


def test_satellite_progress_empty():
    conn = _conn_with_holdings([])
    res = build_satellite_progress([], 1_000_000)
    assert len(res["rows"]) == 2
    total = sum(r["need_amount"] for r in res["rows"])
    assert abs(total - (60_000 + 40_000)) < 0.01  # 6% + 4% of 1M
    assert res["overall_progress_pct"] == 0
    conn.close()


def test_satellite_progress_partial():
    # 已持有 510880 约 3 万，总资产 100 万
    holdings = [{"code": "510880", "name": "上证红利ETF", "quantity": 1000, "last_price": 30.0}]
    conn = _conn_with_holdings(holdings)
    res = build_satellite_progress(
        [{"code": "510880", "name": "上证红利ETF", "market_value": 30000.0, "last_price": 30.0, "quantity": 1000}],
        1_000_000,
    )
    by_code = {r["code"]: r for r in res["rows"]}
    assert by_code["510880"]["pct"] == 3.0
    assert abs(by_code["510880"]["need_amount"] - 30000.0) < 0.01
    assert by_code["159201"]["pct"] == 0.0
    assert by_code["159201"]["need_amount"] > 0
    assert 0 < res["overall_progress_pct"] < 100
    conn.close()


def test_reconcile_roundtrip():
    conn = _conn_with_holdings([])
    conn.execute(
        "CREATE TABLE snapshot_reconcile (date TEXT PRIMARY KEY, manual_total_assets REAL, "
        "note TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "CREATE TABLE daily_snapshots (date TEXT, total_assets REAL)"
    )
    conn.execute("INSERT INTO daily_snapshots VALUES (?, ?)", ("2026-08-01", 1_000_000.0))

    save_reconcile(conn, "2026-08-01", 1_002_300.0, "对账")
    rec = latest_reconcile_with_gap(conn)
    assert rec["manual_total_assets"] == 1_002_300.0
    assert rec["calculated_total_assets"] == 1_000_000.0
    assert rec["gap"] == 2_300.0
    assert rec["gap_pct"] == 0.23
    conn.close()