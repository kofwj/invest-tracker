import sqlite3


def test_alert_rule_crud_and_check_triggers(client, app_module, monkeypatch):
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
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE holdings SET last_price = 12 WHERE code = '600000'")
    conn.commit()
    conn.close()

    def fake_quotes(codes, secid_map=None, use_cache=True):
        out = {}
        for c in codes:
            code = str(c).strip()
            if code == "600000":
                out[code] = {
                    "price": 12.5,
                    "change_pct": 1.2,
                    "name": "浦发银行",
                    "prev_close": 12.35,
                }
            elif code == "000300":
                out[code] = {"price": 3800.0, "change_pct": -0.5, "name": "沪深300", "prev_close": 3819}
            elif code == "000001":
                out[code] = {"price": 3100.0, "change_pct": -0.3, "name": "上证指数"}
            else:
                out[code] = {"price": 100.0, "change_pct": 0.0, "name": code}
        return out

    monkeypatch.setattr("market.fetch_eastmoney_quotes", fake_quotes)
    monkeypatch.setattr("price_sync.fetch_eastmoney_quotes", fake_quotes)

    bad = client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "condition": "sideways",
            "threshold": 12,
        },
    )
    assert bad.status_code == 400

    created = client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "name": "浦发银行",
            "condition": "above",
            "threshold": 12.0,
            "enabled": True,
        },
    )
    assert created.status_code == 200
    rule = created.json()["rule"]
    assert rule["code"] == "600000"
    rule_id = rule["id"]

    listed = client.get("/market/alert-rules")
    assert listed.status_code == 200
    assert any(r["id"] == rule_id for r in listed.json())

    checked = client.post("/market/alerts/check", json={"notify": False})
    assert checked.status_code == 200
    body = checked.json()
    assert body["checked_count"] == 1
    assert body["trigger_count"] == 1
    assert body["triggered"][0]["code"] == "600000"
    assert "昨收" in (body["triggered"][0].get("message") or "") or body["triggered"][0].get("prev_close") is not None

    # cooldown: second check should skip recording
    checked_cd = client.post("/market/alerts/check", json={"notify": False, "respect_cooldown": True})
    assert checked_cd.status_code == 200
    assert checked_cd.json()["trigger_count"] == 0
    assert len(checked_cd.json().get("skipped_cooldown") or []) >= 1

    # force without cooldown
    checked_force = client.post("/market/alerts/check", json={"notify": False, "respect_cooldown": False})
    assert checked_force.json()["trigger_count"] == 1

    events = client.get("/market/alert-events?limit=10")
    assert events.status_code == 200
    rows = events.json()
    assert len(rows) >= 2

    events_code = client.get("/market/alert-events?code=600000")
    assert events_code.status_code == 200
    assert all(r["target_code"] == "600000" for r in events_code.json())

    export = client.get("/market/alert-events/export?code=600000")
    assert export.status_code == 200
    assert b"target_code" in export.content or b"triggered_price" in export.content or "target_code" in export.text

    updated = client.put(
        f"/market/alert-rules/{rule_id}",
        json={"threshold": 20.0},
    )
    assert updated.status_code == 200
    checked2 = client.post("/market/alerts/check", json={"respect_cooldown": False})
    assert checked2.json()["trigger_count"] == 0

    summary = client.get("/market/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert "indices" in data
    assert "signals" in data
    assert "today_highlights" in data["signals"]
    assert "quote_cache_seconds" in data
    assert any(i["code"] == "000300" for i in data["indices"])
    assert any(h["code"] == "600000" for h in data.get("holdings_day") or [])

    # watchlist
    wl = client.put("/market/watchlist", json={"items": [{"code": "000300", "name": "沪深300", "secid": "1.000300"}]})
    assert wl.status_code == 200
    assert len(wl.json()["items"]) == 1
    summary2 = client.get("/market/summary")
    assert any(x["code"] == "000300" for x in summary2.json().get("watchlist") or [])

    cleared = client.post("/market/alert-events/clear", json={"code": "600000"})
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] >= 1

    deleted = client.delete(f"/market/alert-rules/{rule_id}")
    assert deleted.status_code == 200
    assert client.get("/market/alert-rules").json() == []


def test_market_summary_graceful_when_quote_fails(client, app_module, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("network down")

    monkeypatch.setattr("market.fetch_eastmoney_quotes", boom)

    res = client.get("/market/summary")
    assert res.status_code == 200
    data = res.json()
    assert "indices" in data
    assert data.get("index_error")
    assert "signals" in data
    assert "today_highlights" in data["signals"]


def test_notify_feishu_skipped_without_webhook(client, app_module, monkeypatch):
    monkeypatch.delenv("FEISHU_ALERT_WEBHOOK", raising=False)

    def fake_quotes(codes, secid_map=None, use_cache=True):
        return {str(c): {"price": 10.0, "change_pct": 0, "name": str(c)} for c in codes}

    monkeypatch.setattr("market.fetch_eastmoney_quotes", fake_quotes)

    client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "999999",
            "condition": "above",
            "threshold": 1,
            "enabled": True,
        },
    )
    res = client.post("/market/alerts/check", json={"notify": True, "respect_cooldown": False})
    assert res.status_code == 200
    notify = res.json().get("notify") or {}
    assert "sent" in notify


def test_quote_cache_helper(monkeypatch):
    from price_sync import clear_quote_cache, fetch_eastmoney_quotes

    clear_quote_cache()
    calls = {"n": 0}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "diff": [
                        {"f12": "600000", "f14": "浦发银行", "f2": 10.5, "f3": 1.0, "f18": 10.4}
                    ]
                }
            }

    def fake_get(*_a, **_k):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setenv("MARKET_QUOTE_CACHE_SECONDS", "120")
    monkeypatch.setattr("price_sync.requests.get", fake_get)
    clear_quote_cache()
    q1 = fetch_eastmoney_quotes(["600000"], use_cache=False)
    assert q1["600000"]["price"] == 10.5
    assert calls["n"] == 1


def test_trading_calendar_helpers():
    from trading_calendar import is_a_share_trading_day, trading_day_status

    assert is_a_share_trading_day("2026-07-11") is False  # Saturday
    assert is_a_share_trading_day("2026-07-13") is True  # Monday, not holiday
    assert is_a_share_trading_day("2026-10-01") is False  # National Day
    st = trading_day_status("2026-10-01")
    assert st["is_trading_day"] is False
    assert st["reason"] == "holiday"


def test_snapshot_stores_lifetime_profit(client, app_module, monkeypatch):
    import database as db

    monkeypatch.setattr(db, "local_today_iso", lambda: "2026-07-14")
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
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute("UPDATE holdings SET last_price = 12 WHERE code = '600000'")
    # 测试造数据补真实前提：当天成功同步过一次价格（否则快照价格闸门会 409）
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('last_price_sync_at', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ("2026-07-14 15:20:00",),
    )
    conn.commit()
    conn.close()

    res = client.post("/snapshots")
    assert res.status_code == 200
    rows = client.get("/snapshots").json()
    assert rows
    assert "lifetime_profit" in rows[0]
    assert float(rows[0]["lifetime_profit"] or 0) != 0 or rows[0]["total_profit"] is not None


def _seed_holding(client, code, name, qty=100, price=10.0):
    """通过交易接口建一条持仓，返回后由调用方改 last_price。"""
    client.post(
        "/transactions",
        json={
            "date": "2026-01-02",
            "code": code,
            "name": name,
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


def _patch_quotes(monkeypatch, table, seen=None):
    """table: {code: (price, prev_close)}；seen 会记录被请求过的 code。"""

    def fake_quotes(codes, secid_map=None, use_cache=True):
        out = {}
        for c in codes:
            code = str(c).strip()
            if seen is not None:
                seen.append(code)
            if code in table:
                price, prev = table[code]
                out[code] = {
                    "price": price,
                    "change_pct": round((price / prev - 1) * 100, 2) if prev else None,
                    "name": code,
                    "prev_close": prev,
                }
            else:
                out[code] = {"price": 100.0, "change_pct": 0.0, "name": code}
        return out

    monkeypatch.setattr("market.fetch_eastmoney_quotes", fake_quotes)
    monkeypatch.setattr("price_sync.fetch_eastmoney_quotes", fake_quotes)


def test_change_pct_rule_triggers_on_intraday_move(client, app_module, monkeypatch):
    """涨跌幅规则比的是日内涨跌（相对昨收），不是绝对价格。"""
    _seed_holding(client, "600000", "浦发银行", qty=100, price=10.0)
    # 现价 9.7 / 昨收 10.0 → 日内 -3.0%
    _patch_quotes(monkeypatch, {"600000": (9.7, 10.0)})

    # 价格规则不允许负阈值（回归护栏）
    bad = client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "condition": "below",
            "threshold": -2.0,
            "rule_type": "price",
        },
    )
    assert bad.status_code == 400

    created = client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "name": "浦发银行",
            "condition": "below",
            "threshold": -2.0,
            "rule_type": "change_pct",
        },
    )
    assert created.status_code == 200
    assert created.json()["rule"]["rule_type"] == "change_pct"

    body = client.post(
        "/market/alerts/check", json={"notify": False, "respect_cooldown": False}
    ).json()
    assert body["trigger_count"] == 1
    hit = body["triggered"][0]
    assert hit["rule_type"] == "change_pct"
    assert hit["value"] == -3.0
    assert "日内" in hit["message"]
    assert "阈值 -2.00%" in hit["message"]


def test_change_pct_rule_not_triggered_when_move_small(client, app_module, monkeypatch):
    """日内只跌 1% 时，-2% 的阈值不该报。"""
    _seed_holding(client, "600000", "浦发银行", qty=100, price=10.0)
    _patch_quotes(monkeypatch, {"600000": (9.9, 10.0)})
    client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "condition": "below",
            "threshold": -2.0,
            "rule_type": "change_pct",
        },
    )
    body = client.post(
        "/market/alerts/check", json={"notify": False, "respect_cooldown": False}
    ).json()
    assert body["trigger_count"] == 0


def test_portfolio_pnl_rule_uses_weighted_move(client, app_module, monkeypatch):
    """组合规则按 (现价-昨收)*数量 汇总，且不拿 PORTFOLIO 去请求行情。"""
    _seed_holding(client, "600000", "浦发银行", qty=100, price=10.0)
    _seed_holding(client, "600001", "邯郸钢铁", qty=100, price=10.0)
    seen = []
    # A: 9.8/10.0 ×100 = -20；B: 9.9/10.0 ×100 = -10 → 合计 -30 / 基准 2000 = -1.5%
    _patch_quotes(monkeypatch, {"600000": (9.8, 10.0), "600001": (9.9, 10.0)}, seen=seen)

    created = client.post(
        "/market/alert-rules",
        json={
            "target_type": "portfolio",
            "code": "",
            "condition": "below",
            "threshold": -1.0,
            "rule_type": "portfolio_pnl",
        },
    )
    assert created.status_code == 200
    rule = created.json()["rule"]
    assert rule["code"] == "PORTFOLIO"
    assert rule["rule_type"] == "portfolio_pnl"

    body = client.post(
        "/market/alerts/check", json={"notify": False, "respect_cooldown": False}
    ).json()
    assert body["trigger_count"] == 1
    hit = body["triggered"][0]
    assert hit["code"] == "PORTFOLIO"
    assert hit["name"] == "组合当日盈亏"
    assert hit["value"] == -1.5
    assert "组合当日盈亏 -1.50%" in hit["message"]
    assert "-30" in hit["message"]

    # 组合规则不该把哨兵当代码去查行情
    assert "PORTFOLIO" not in seen


def test_portfolio_pnl_skips_holdings_without_prev_close(client, app_module, monkeypatch):
    """缺昨收的持仓跳过：取不到就不猜，宁可少算也不错算。"""
    _seed_holding(client, "600000", "浦发银行", qty=100, price=10.0)
    _seed_holding(client, "600001", "邯郸钢铁", qty=100, price=10.0)

    def fake_quotes(codes, secid_map=None, use_cache=True):
        out = {}
        for c in codes:
            code = str(c).strip()
            if code == "600000":
                out[code] = {
                    "price": 9.0,
                    "change_pct": -10.0,
                    "name": code,
                    "prev_close": 10.0,
                }
            else:
                # 没有昨收 → 应被 _portfolio_day_pnl 跳过
                out[code] = {
                    "price": 20.0,
                    "change_pct": None,
                    "name": code,
                    "prev_close": None,
                }
        return out

    monkeypatch.setattr("market.fetch_eastmoney_quotes", fake_quotes)
    monkeypatch.setattr("price_sync.fetch_eastmoney_quotes", fake_quotes)

    client.post(
        "/market/alert-rules",
        json={
            "target_type": "portfolio",
            "code": "",
            "condition": "below",
            "threshold": -5.0,
            "rule_type": "portfolio_pnl",
        },
    )
    body = client.post(
        "/market/alerts/check", json={"notify": False, "respect_cooldown": False}
    ).json()
    # 只算得到昨收的那只：-100/1000 = -10%
    assert body["trigger_count"] == 1
    assert body["triggered"][0]["value"] == -10.0


def test_existing_price_rules_default_to_price_type(client, app_module, monkeypatch):
    """老调用方不传 rule_type 时落到 price，行为与以前一致。"""
    _seed_holding(client, "600000", "浦发银行", qty=100, price=10.0)
    _patch_quotes(monkeypatch, {"600000": (12.5, 12.35)})

    created = client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "condition": "above",
            "threshold": 12.0,
        },
    )
    assert created.status_code == 200
    assert created.json()["rule"]["rule_type"] == "price"

    body = client.post(
        "/market/alerts/check", json={"notify": False, "respect_cooldown": False}
    ).json()
    assert body["trigger_count"] == 1
    hit = body["triggered"][0]
    assert hit["rule_type"] == "price"
    assert hit["price"] == 12.5
    assert hit["value"] == 12.5


def test_rule_type_validation_rejects_unknown(client, app_module):
    bad = client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "condition": "above",
            "threshold": 12.0,
            "rule_type": "moon_phase",
        },
    )
    assert bad.status_code == 400


def _mute_notifier(monkeypatch):
    """把真正的推送换掉：上限测试只关心"记了几条"，不该真发消息。"""
    import notify

    monkeypatch.setattr(
        notify,
        "notify_price_alerts",
        lambda triggered, conn=None: {"sent": False, "reason": "muted", "count": len(triggered)},
    )


def test_daily_cap_limits_scheduled_pushes(client, app_module, monkeypatch):
    """每日上限只约束定时推送：超过上限的规则进 skipped_daily_cap，不再记录。"""
    import sqlite3 as _sqlite3

    _mute_notifier(monkeypatch)
    _seed_holding(client, "600000", "浦发银行", qty=100, price=10.0)
    _seed_holding(client, "600001", "邯郸钢铁", qty=100, price=10.0)
    # 两只都 -10%，各建一条 -5% 的规则 → 都会命中
    _patch_quotes(monkeypatch, {"600000": (9.0, 10.0), "600001": (9.0, 10.0)})
    for code in ("600000", "600001"):
        client.post(
            "/market/alert-rules",
            json={
                "target_type": "holding",
                "code": code,
                "condition": "below",
                "threshold": -5.0,
                "rule_type": "change_pct",
            },
        )

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('alert_daily_cap', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()

    body = client.post(
        "/market/alerts/check", json={"notify": True, "respect_cooldown": False}
    ).json()
    assert body["daily_cap"] == 1
    assert body["trigger_count"] == 1
    assert len(body["skipped_daily_cap"]) == 1

    # 记录也确实只落了一条
    conn = _sqlite3.connect(app_module.DB_PATH)
    n = conn.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0]
    conn.close()
    assert n == 1


def test_daily_cap_does_not_block_manual_check(client, app_module, monkeypatch):
    """手动「立即检查」（notify=False）不受上限约束，否则会以为规则坏了。"""
    _mute_notifier(monkeypatch)
    _seed_holding(client, "600000", "浦发银行", qty=100, price=10.0)
    _patch_quotes(monkeypatch, {"600000": (9.0, 10.0)})
    client.post(
        "/market/alert-rules",
        json={
            "target_type": "holding",
            "code": "600000",
            "condition": "below",
            "threshold": -5.0,
            "rule_type": "change_pct",
        },
    )
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('alert_daily_cap', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()

    body = client.post(
        "/market/alerts/check", json={"notify": False, "respect_cooldown": False}
    ).json()
    assert body["skipped_daily_cap"] == []
    assert body["trigger_count"] == 1
