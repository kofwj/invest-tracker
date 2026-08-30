"""Bug 修复回归测试（2026-08-30 审查批次）。

覆盖本轮代码审查确认的 5 个 bug：
1. price_sync 行情缓存按 secid 隔离（上证指数 1.000001 vs 平安银行 0.000001 不再串价）
2. return_sync.one_year_before 闰年 2/29 不再崩溃
3. routers_transactions.code 强制 trim + 非空（防止现金已扣、持仓不变的账实分离）
4. routers_fee_settings PUT 缺省 accounts 时不再静默重置自定义费率
5. auth 登录限速默认忽略伪造 X-Forwarded-For + 限流状态容量上限

注意：backend 模块一律在函数内 import（app_module fixture 会 reload 模块链）。
"""
import sqlite3
from datetime import date as dt_date
from unittest import mock


# ---------- 1. 行情缓存按 secid 隔离 ----------

def test_quote_cache_separates_index_and_stock_with_same_code(monkeypatch):
    """上证指数(1.000001)缓存后，同 code 的平安银行(0.000001)不得命中指数报价。"""
    import price_sync as ps

    ps.clear_quote_cache()
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append(params["secids"])
        secid = params["secids"]
        if secid == "1.000001":
            payload = {"data": {"diff": [
                {"f12": "000001", "f14": "上证指数", "f2": "3300.0", "f3": "0.5", "f18": "3283.0"},
            ]}}
        else:
            payload = {"data": {"diff": [
                {"f12": "000001", "f14": "平安银行", "f2": "11.5", "f3": "1.0", "f18": "11.38"},
            ]}}
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = payload
        return resp

    try:
        with mock.patch.object(ps, "requests") as mock_req, mock.patch.object(ps, "_CACHE_TTL", 300):
            mock_req.get.side_effect = fake_get
            # 模拟 build_market_summary：先取指数（secid_map 覆盖），写入缓存
            idx = ps.fetch_eastmoney_quotes(["000001"], secid_map={"000001": "1.000001"})
            assert idx["000001"]["price"] == 3300.0
            assert idx["000001"]["name"] == "上证指数"

            # 同一 TTL 窗口内取个股（无 secid_map → 0.000001）：不能命中指数缓存
            stock = ps.fetch_eastmoney_quotes(["000001"])
            assert stock["000001"]["price"] == 11.5
            assert stock["000001"]["name"] == "平安银行"
            # 确认第二次确实发起了网络请求（缓存未串）
            assert calls == ["1.000001", "0.000001"]
    finally:
        ps.clear_quote_cache()


def test_quote_cache_hits_when_secid_matches(monkeypatch):
    """同 secid 的重复请求仍应命中缓存（修复不破坏正常缓存行为）。"""
    import price_sync as ps

    ps.clear_quote_cache()
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append(params["secids"])
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"data": {"diff": [
            {"f12": "600519", "f14": "贵州茅台", "f2": "1000.0", "f3": "1.2", "f18": "988.0"},
        ]}}
        return resp

    try:
        with mock.patch.object(ps, "requests") as mock_req, mock.patch.object(ps, "_CACHE_TTL", 300):
            mock_req.get.side_effect = fake_get
            q1 = ps.fetch_eastmoney_quotes(["600519"])
            q2 = ps.fetch_eastmoney_quotes(["600519"])
            assert q1["600519"]["price"] == 1000.0
            assert q2["600519"]["price"] == 1000.0
            assert len(calls) == 1  # 第二次命中缓存
    finally:
        ps.clear_quote_cache()


# ---------- 2. 闰年 2/29 近一年收益同步 ----------

def test_one_year_before_leap_day_falls_back_to_feb_28():
    from return_sync import one_year_before

    # 2028-02-29.replace(year=2027) 原先抛 ValueError → 同步接口 500
    assert one_year_before(dt_date(2028, 2, 29)) == dt_date(2027, 2, 28)
    # 普通日期保持原有语义
    assert one_year_before(dt_date(2026, 8, 30)) == dt_date(2025, 8, 30)
    assert one_year_before(dt_date(2025, 3, 1)) == dt_date(2024, 3, 1)

# ---------- 3. 交易 code trim ----------

def _post_buy(client, code, name="中国石化", date="2026-01-10"):
    return client.post("/transactions", json={
        "date": date,
        "code": code,
        "name": name,
        "category": "A股权益",
        "account": "华泰证券",
        "direction": "买入",
        "quantity": 1000,
        "price": 6.0,
        "amount": 6005.0,
        "fee": 5.0,
        "remark": "test",
    })


def test_transaction_code_whitespace_still_updates_holdings(app_module, client):
    """带空白的 code 不应再造成“现金已扣、持仓不变”的账实分离。"""
    from database import db_session

    resp = _post_buy(client, " 600028 ")
    assert resp.status_code == 200

    with db_session(row_factory=sqlite3.Row) as conn:
        tx = conn.execute("SELECT code FROM transactions").fetchone()
        assert tx["code"] == "600028"
        holding = conn.execute(
            "SELECT quantity, avg_cost FROM holdings WHERE code = '600028'"
        ).fetchone()
        assert holding is not None
        assert holding["quantity"] == 1000
        assert holding["avg_cost"] == 6.005


def test_transaction_blank_code_rejected(app_module, client):
    resp = _post_buy(client, "   ")
    assert resp.status_code == 422  # pydantic 校验拒绝空 code，而非入库后账实分离


def test_transaction_update_strips_code(app_module, client):
    from database import db_session

    create = _post_buy(client, "600028")
    assert create.status_code == 200
    with db_session(row_factory=sqlite3.Row) as conn:
        tx_id = conn.execute("SELECT id FROM transactions WHERE code = '600028'").fetchone()["id"]

    # PUT 带空白的 code 应被 strip 后落库
    resp = client.put(f"/transactions/{tx_id}", json={"code": " 600028 "})
    assert resp.status_code == 200
    # 空白-only code 视为“不修改”，不应清空原有 code
    blank = client.put(f"/transactions/{tx_id}", json={"code": "   ", "name": "中国石化H"})
    assert blank.status_code == 200
    with db_session(row_factory=sqlite3.Row) as conn:
        row = conn.execute("SELECT code, name FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        assert row["code"] == "600028"
        assert row["name"] == "中国石化H"


# ---------- 4. fee-settings 缺省 accounts ----------

def test_fee_settings_put_without_accounts_keeps_custom_accounts(app_module, client):
    """PUT 不传 accounts 时，账户应从 settings keys 推导，而不是静默重置。"""
    custom = {
        "国金证券": {
            "A股权益": {"commission_rate": 0.001, "stamp_tax_rate": 0.0005,
                        "transfer_fee_rate": 0.00001, "min_commission": 5.0},
        },
    }
    resp = client.put("/fee-settings", json={"settings": custom})
    assert resp.status_code == 200
    data = resp.json()
    assert "国金证券" in data["accounts"]
    rule = data["settings"]["国金证券"]["A股权益"]
    assert rule["commission_rate"] == 0.001
    assert rule["min_commission"] == 5.0

    # 持久化后 GET 返回同样保留
    got = client.get("/fee-settings").json()
    assert "国金证券" in got["accounts"]
    assert got["settings"]["国金证券"]["A股权益"]["commission_rate"] == 0.001


def test_fee_settings_put_with_explicit_accounts_still_works(app_module, client):
    resp = client.put("/fee-settings", json={
        "accounts": ["华泰证券"],
        "active_account": "华泰证券",
        "settings": {"华泰证券": {"A股ETF": {"commission_rate": 0.0002}}},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["accounts"] == ["华泰证券"]
    assert data["settings"]["华泰证券"]["A股ETF"]["commission_rate"] == 0.0002


# ---------- 5. 登录限速 / 伪造 XFF ----------

def test_login_throttle_ignores_forged_xff_by_default(client, monkeypatch):
    """默认不信任 X-Forwarded-For：换假 IP 无法获得新的失败额度。"""
    import auth as auth_mod

    monkeypatch.setenv("INVEST_TRACKER_PASSWORD", "correct-password")
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    monkeypatch.setattr(auth_mod, "LOGIN_MAX_FAILURES", 3)
    auth_mod.reset_login_throttle_state()

    for fake_ip in ["1.1.1.1", "2.2.2.2", "3.3.3.3"]:
        resp = client.post("/login", json={"password": "wrong"},
                           headers={"X-Forwarded-For": fake_ip})
        assert resp.status_code == 400

    # 真实来源 IP（testclient）已积累 3 次失败 → 再换假 IP 也应被锁
    locked = client.post("/login", json={"password": "wrong"},
                         headers={"X-Forwarded-For": "4.4.4.4"})
    assert locked.status_code == 429
    auth_mod.reset_login_throttle_state()


def test_login_throttle_honors_xff_when_trust_enabled(client, monkeypatch):
    """显式设置 TRUST_PROXY_HEADERS=1 时恢复旧行为（可信代理部署场景）。"""
    import auth as auth_mod

    monkeypatch.setenv("INVEST_TRACKER_PASSWORD", "correct-password")
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    monkeypatch.setattr(auth_mod, "LOGIN_MAX_FAILURES", 3)
    auth_mod.reset_login_throttle_state()

    for fake_ip in ["1.1.1.1", "2.2.2.2", "3.3.3.3"]:
        resp = client.post("/login", json={"password": "wrong"},
                           headers={"X-Forwarded-For": fake_ip})
        assert resp.status_code == 400

    # 每个伪造 IP 各自独立计数，不触发锁定（可信代理场景下的原有语义）
    another = client.post("/login", json={"password": "wrong"},
                          headers={"X-Forwarded-For": "4.4.4.4"})
    assert another.status_code == 400
    auth_mod.reset_login_throttle_state()


def test_throttle_state_bounded_under_forged_ip_flood(monkeypatch):
    """伪造 IP 洪水不再导致 _fail_events 无限增长。"""
    import auth as auth_mod

    monkeypatch.setattr(auth_mod, "LOGIN_MAX_FAILURES", 5)
    monkeypatch.setattr(auth_mod, "LOGIN_MAX_TRACKED_IPS", 10)
    auth_mod.reset_login_throttle_state()

    for i in range(200):
        auth_mod.register_login_failure(f"10.0.{i // 256}.{i % 256}")

    assert len(auth_mod._fail_events) <= 10
    assert len(auth_mod._lock_until) <= 10
    auth_mod.reset_login_throttle_state()



# =====================================================================
# 第二批修复（2026-08-30 同日追加）：中等优先级问题
# =====================================================================

# ---------- 6. CSV Sniffer 回退 ----------

def test_read_upload_csv_sniffer_fallback():
    """单列/无分隔符 CSV 不再因 Sniffer 抛 csv.Error 导致导入接口 500。"""
    from csv_utils import read_upload_csv

    rows = read_upload_csv("date,code\n2025-01-01,600028\n".encode("utf-8"))
    assert rows[0]["date"] == "2025-01-01"
    # 单列、无分隔符：Sniffer 无法判定分隔符，应回退 excel 方言而非抛异常
    rows = read_upload_csv("date\n2025-01-01\n".encode("utf-8"))
    assert rows[0]["date"] == "2025-01-01"
    assert read_upload_csv(b"") == []


# ---------- 7. GET /dividends/scan 参数校验 ----------

def test_dividends_scan_get_invalid_lookback_422(app_module, client):
    """query 参数绕过 pydantic 模型校验，非法值应 422 而不是 500。"""
    resp = client.get("/dividends/scan?lookback_days=10")
    assert resp.status_code == 422
    assert "参数校验失败" in resp.json()["detail"]
    # 合法值仍可用
    assert client.get("/dividends/scan?lookback_days=400").status_code == 200


# ---------- 8. 分红导入报错行号 = 文件真实行号 ----------

def test_dividends_import_error_row_uses_file_line_number(app_module, client):
    csv_content = (
        "date,account,code,name,category,amount,fee,remark\n"
        "2026-01-10,华泰证券,,农业银行,A股权益,123.45,0,x\n"
    )
    resp = client.post("/dividends/import",
                       files={"file": ("dividends.csv", csv_content.encode("utf-8"), "text/csv")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 0 and data["failed"] == 1
    # 第1行是表头，出错的数据在文件第2行
    assert data["errors"][0]["row"] == 2


# ---------- 9. 交易/流水日期参数校验 ----------

def test_transaction_and_cash_flow_date_params_reject_non_iso(app_module, client):
    """非 ISO 日期不再静默给出错误过滤结果，而是 400。"""
    assert client.get("/transactions?start_date=2025/01/01").status_code == 400
    assert client.get("/transactions?end_date=2025-1-1").status_code == 400
    assert client.get("/transactions/export?start_date=2025/01/01").status_code == 400
    assert client.get("/cash-flows?start_date=2025/01/01").status_code == 400
    # 合法 ISO 日期正常返回
    assert client.get("/transactions?start_date=2025-01-01&end_date=2025-12-31").status_code == 200
    assert client.get("/cash-flows?start_date=2025-01-01").status_code == 200


# ---------- 11. 交易日接口非法日期 → 400 ----------

def test_trading_day_invalid_date_returns_400(app_module, client):
    bad = client.get("/market/trading-day?date=2025/1/1")
    assert bad.status_code == 400
    assert "YYYY-MM-DD" in bad.json()["detail"]
    ok = client.get("/market/trading-day?date=2026-08-28")
    assert ok.status_code == 200
    assert ok.json()["date"] == "2026-08-28"
    # 不传日期 → 默认今天（保留原有语义）
    default = client.get("/market/trading-day")
    assert default.status_code == 200
    assert default.json()["date"]  # 返回今天的 ISO 日期


# ---------- 12. 确认分红拒绝未来日期 ----------

def test_confirm_dividends_rejects_future_event_date(app_module, client):
    from datetime import date as dt_date, timedelta

    from database import db_session

    tomorrow = (dt_date.today() + timedelta(days=1)).isoformat()
    yesterday = (dt_date.today() - timedelta(days=1)).isoformat()
    payload = {
        "backup": False,
        "drafts": [
            {"code": "600028", "name": "中国石化", "category": "A股权益",
             "account": "华泰证券", "event_date": tomorrow, "amount": 100.0,
             "fee": 0, "remark": "future", "direction": "分红"},
            {"code": "600029", "name": "南方航空", "category": "A股权益",
             "account": "华泰证券", "event_date": yesterday, "amount": 50.0,
             "fee": 0, "remark": "past", "direction": "分红"},
        ],
    }
    resp = client.post("/dividends/confirm", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["created_count"] == 1
    assert data["error_count"] == 1
    assert "不能晚于今天" in data["errors"][0]["reason"]
    with db_session(row_factory=sqlite3.Row) as conn:
        rows = conn.execute(
            "SELECT code, date FROM transactions WHERE direction = '分红' ORDER BY id"
        ).fetchall()
    assert [r["code"] for r in rows] == ["600029"]  # 未来的那条没有入账


# ---------- 13. dividend_sync 与 holding_calculator 的历史持仓口径一致 ----------

def test_dividend_sync_holding_qty_uses_latest_correction_le_as_of(app_module):
    """多条校准记录时，分红估算与交易编辑路径使用同一套锚点回退语义。"""
    from datetime import date as dt_date

    from database import db_session
    from dividend_sync import holding_quantity_as_of as ds_qty
    from holding_calculator import holding_quantity_as_of as hc_qty

    with db_session(row_factory=sqlite3.Row) as conn:
        conn.execute(
            "INSERT INTO holding_corrections (date, code, name, actual_quantity, actual_avg_cost) "
            "VALUES ('2024-01-10', '600028', '中国石化', 500, 10)"
        )
        conn.execute(
            "INSERT INTO holding_corrections (date, code, name, actual_quantity, actual_avg_cost) "
            "VALUES ('2025-06-01', '600028', '中国石化', 1000, 10)"
        )
        conn.execute(
            "INSERT INTO transactions (date, code, name, direction, quantity, price, amount) "
            "VALUES ('2024-03-01', '600028', '中国石化', '买入', 100, 10, 1000)"
        )
        conn.execute(
            "INSERT INTO transactions (date, code, name, direction, quantity, price, amount) "
            "VALUES ('2025-08-01', '600028', '中国石化', '买入', 50, 10, 500)"
        )
        conn.commit()

        as_of = dt_date(2025, 1, 1)
        # 2024 锚点生效（500）+ 锚点后的买入 100；2025 新锚点因日期 > as_of 被排除
        assert ds_qty(conn, "600028", as_of) == 600.0
        # 与 holding_calculator 实现完全一致
        assert hc_qty(conn, "600028", as_of_date=as_of) == ds_qty(conn, "600028", as_of)


# ---------- 10. 存款导入 NaN/缺利率列 ----------

def test_deposit_import_rejects_nan_and_missing_rate_column(app_module, client):
    from database import db_session

    csv_content = (
        "银行,金额,起存日,到期日,备注\n"
        "测试银行,nan,2026-01-01,2026-12-31,备注\n"
        "工商银行,1000.00,2026-01-01,2026-12-31,备注\n"
    )
    resp = client.post("/deposits/import",
                       files={"file": ("deposits.csv", csv_content.encode("utf-8"), "text/csv")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 1
    assert data["failed"] == 1
    assert data["errors"][0]["row"] == 2  # nan 行
    with db_session(row_factory=sqlite3.Row) as conn:
        rows = conn.execute("SELECT bank_name, amount, interest_rate FROM deposits ORDER BY id").fetchall()
    assert len(rows) == 1
    assert rows[0]["bank_name"] == "工商银行"
    # 缺“年利率”列 → NULL（未填），而不是被误写成 0.0
    assert rows[0]["interest_rate"] is None



# ---------- 14. 飞书 token 缓存按凭证区分 ----------

def test_feishu_token_cache_keyed_by_credentials(monkeypatch):
    """更换 app_id/app_secret 后立即重新换取 token，不再沿用旧应用缓存。"""
    import notify as n

    n.reset_feishu_token_cache()
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((json["app_id"], json["app_secret"]))
        resp = mock.Mock()
        resp.status_code = 200
        resp.json.return_value = {"code": 0, "tenant_access_token": f"tok-{json['app_id']}"}
        return resp

    try:
        with mock.patch("requests.post", side_effect=fake_post):
            t1 = n._feishu_tenant_token("app_a", "secret_a")
            t1b = n._feishu_tenant_token("app_a", "secret_a")  # 同凭证 → 命中缓存
            t2 = n._feishu_tenant_token("app_b", "secret_a")  # 换凭证 → 重新换取
            t2b = n._feishu_tenant_token("app_b", "secret_b")  # 只换 secret 也要重新换取
        assert (t1, t1b, t2) == ("tok-app_a", "tok-app_a", "tok-app_b")
        assert t2b == "tok-app_b"
        assert calls == [
            ("app_a", "secret_a"),
            ("app_b", "secret_a"),
            ("app_b", "secret_b"),
        ]
    finally:
        n.reset_feishu_token_cache()


# ---------- 15. clear_alert_events 必须带过滤条件或显式 allow_all ----------

def test_clear_alert_events_requires_filter_or_allow_all(app_module):
    import sqlite3

    import pytest

    import market as m

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE alert_events (id INTEGER PRIMARY KEY AUTOINCREMENT, target_code TEXT, trigger_time TEXT)")
    conn.execute("INSERT INTO alert_events (target_code, trigger_time) VALUES ('600000', '2026-01-01')")
    conn.execute("INSERT INTO alert_events (target_code, trigger_time) VALUES ('000001', '2026-01-02')")

    with pytest.raises(ValueError):
        m.clear_alert_events(conn)  # 无过滤 → 拒绝，不再清空全表
    assert m.clear_alert_events(conn, code="600000") == 1
    assert m.clear_alert_events(conn, allow_all=True) == 1  # 显式全清仍可用
    conn.close()


# ---------- 16. 组合流水 created_at 显式写入 ----------

def test_portfolio_cash_flow_created_at_written(app_module, client):
    from datetime import date as dt_date

    from database import db_session

    resp = client.post("/portfolio-cash-flows", json={
        "date": str(dt_date.today()),
        "flow_type": "投入",
        "amount": 1000,
    })
    assert resp.status_code == 200
    with db_session(row_factory=sqlite3.Row) as conn:
        row = conn.execute("SELECT created_at FROM portfolio_cash_flows ORDER BY id DESC LIMIT 1").fetchone()
    # 显式写入应用本地时间（不依赖容器 OS 时区），且非空
    assert row["created_at"]
    assert len(str(row["created_at"])) >= 19  # 'YYYY-MM-DD HH:MM:SS'

