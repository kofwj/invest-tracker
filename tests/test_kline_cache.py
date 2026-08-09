"""K线缓存模块回归测试。"""
import os
import sys
import tempfile

import pytest

# Allow loading backend as top-level package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture()
def tmp_db(monkeypatch):
    """提供一个带临时 DB 的 database 模块 + 已建好 schema 的连接。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    import database as db_module
    import schema

    monkeypatch.setattr(db_module, "DB_PATH", path)
    monkeypatch.setattr(db_module, "APP_CONFIG", {"path": path})
    # 清掉可能存在的缓存连接
    try:
        db_module._db_conn.close()
    except Exception:
        pass

    with db_module.open_db() as conn:
        schema.ensure_app_schema(conn)
        conn.commit()

    yield db_module, path

    try:
        os.remove(path)
    except Exception:
        pass


def test_kline_cache_table_created_on_migration(tmp_db):
    """schema v10 应建出 kline_cache 表。"""
    db_module, _ = tmp_db
    with db_module.open_db() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(kline_cache)").fetchall()]
        assert "code" in cols
        assert "date" in cols
        assert "open" in cols
        assert "high" in cols
        assert "low" in cols
        assert "close" in cols
        assert "volume" in cols
        assert "amount" in cols

    # 唯一约束验证：绕过 upsert 直接 INSERT 重复 (code, date) 应报错
    from kline_cache import ensure_kline_cache_table
    with db_module.open_db() as conn:
        ensure_kline_cache_table(conn)
        conn.execute("INSERT INTO kline_cache (code, date, open, high, low, close, volume, amount) VALUES (?, ?, 0,0,0,0,0,0)", ("X", "2026-01-01"))
        with pytest.raises(Exception):
            conn.execute("INSERT INTO kline_cache (code, date, open, high, low, close, volume, amount) VALUES (?, ?, 0,0,0,0,0,0)", ("X", "2026-01-01"))


def test_upsert_klines_idempotent(tmp_db):
    """同一批重复 upsert 不应产生重复行。"""
    db_module, _ = tmp_db
    from kline_cache import ensure_kline_cache_table, upsert_klines
    with db_module.open_db() as conn:
        rows = [
            {"date": "2026-07-01", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1000, "amount": 10000},
            {"date": "2026-07-02", "open": 10.5, "high": 11.5, "low": 10, "close": 11, "volume": 2000, "amount": 22000},
        ]
        n1 = upsert_klines(conn, "TEST001", rows)
        conn.commit()
        assert n1 == 2
        n2 = upsert_klines(conn, "TEST001", rows)
        conn.commit()
        assert n2 == 2
        cnt = conn.execute("SELECT COUNT(*) FROM kline_cache WHERE code='TEST001'").fetchone()[0]
        assert cnt == 2


def test_sync_kline_for_code_skips_recent(tmp_db, monkeypatch):
    """updated_at 是今天时 force=False 不应发网络请求。"""
    db_module, _ = tmp_db
    import kline_cache
    from kline_cache import ensure_kline_cache_table, upsert_klines

    called = {"n": 0}
    monkeypatch.setattr(kline_cache, "fetch_tencent_kline_ohlc", lambda code, count=420: (called.__setitem__("n", called["n"] + 1), [])[1])

    with db_module.open_db() as conn:
        today_row = [{"date": "2026-07-30", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0, "amount": 0}]
        upsert_klines(conn, "600000", today_row)
        # 手动把 updated_at 设成当地的"今天"（让代码的 _local_today_iso 判断认为已同步）
        from kline_cache import _local_today_iso
        today = _local_today_iso()
        conn.execute("UPDATE kline_cache SET updated_at = ? WHERE code = '600000' AND date = '2026-07-30'", (today + " 10:00:00",))
        conn.commit()

        n = kline_cache.sync_kline_for_code(conn, "600000", force=False)
        assert n == 0
        assert called["n"] == 0


def test_get_cached_klines_returns_ascending(tmp_db):
    """get_cached_klines 应按日期升序返回。"""
    db_module, _ = tmp_db
    from kline_cache import ensure_kline_cache_table, upsert_klines, get_cached_klines
    with db_module.open_db() as conn:
        upsert_klines(conn, "000001", [
            {"date": "2026-07-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0, "amount": 0},
            {"date": "2026-07-03", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0, "amount": 0},
            {"date": "2026-07-02", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0, "amount": 0},
        ])
        conn.commit()
    rows = get_cached_klines("000001", days=10)
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)


def test_kline_api_otcfund_returns_is_fund(client):
    """场外开放式基金（f 开头，如 f002864 安泽短债）没有股票式 K 线。
    必须返回 is_fund 标记 + 空 rows，且不得把 f 剥掉当 A 股串台拉取。"""
    res = client.get("/klines/f002864?days=5")
    assert res.status_code == 200
    data = res.json()
    assert data.get("is_fund") is True
    assert data["rows"] == []
    assert data["count"] == 0


def test_sync_kline_skips_otcfund(tmp_db):
    """sync_kline_for_code 对 f 前缀基金直接跳过，不触发任何拉取。"""
    db_module, _ = tmp_db
    import kline_cache
    calls = {"n": 0}

    def _explode(code, count=420):
        calls["n"] += 1
        raise AssertionError("场外基金不该走股票K线接口")

    kline_cache.fetch_tencent_kline_ohlc = _explode
    kline_cache.fetch_eastmoney_kline_ohlc = _explode
    with db_module.open_db() as conn:
        n = kline_cache.sync_kline_for_code(conn, "f002864", force=True)
        conn.commit()
    assert n == 0
    assert calls["n"] == 0


def test_kline_api_endpoints(client, monkeypatch):
    """通过 API 测 /klines/{code} 与 /klines/sync 的契约。"""
    import kline_cache
    monkeypatch.setattr(kline_cache, "fetch_tencent_kline_ohlc", lambda code, count=420: [])
    monkeypatch.setattr(kline_cache, "fetch_eastmoney_kline_ohlc", lambda code, count=420: [])

    res = client.get("/klines/NONEXIST")
    assert res.status_code == 200
    data = res.json()
    assert "code" in data
    assert "rows" in data
    assert isinstance(data["rows"], list)

    res2 = client.post("/klines/sync", json={"force": False})
    assert res2.status_code == 200
    data2 = res2.json()
    assert "synced" in data2
    assert "skipped" in data2
    assert "failed" in data2
