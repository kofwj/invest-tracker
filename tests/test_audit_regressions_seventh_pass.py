# -*- coding: utf-8 -*-
"""第七轮审计回归：首轮修复后复核发现的问题。

1. period_gain 无基准快照且本期之前已有资金 → 必须返回 None，不得捏数字
2. target_return_pct 单位：前端直接拼 %，必须是 4.0 而不是 0.04
3. TWR/Sharpe 共用同一套现金流剥离日收益（前缀和区间求和）
"""
import sqlite3

from performance import _daily_returns, _flow_prefix_sums, _flows_between


# ----------------------------- 问题 1 -----------------------------

def test_period_gain_is_none_without_baseline_and_prior_capital(client):
    """本期之前已有在册资金、却没有起点快照 → 期间收益不可知。

    修复前 period_gain = total_assets(50万) − period_net(1万) = 49万，
    再除以 period_net 报 +4900%，而真实全周期收益是 0%。
    """
    assert client.put("/securities-cash", json={"amount": 0}).status_code == 200
    # 本期之前的资金
    assert client.post(
        "/portfolio-cash-flows",
        json={"date": "2024-01-01", "flow_type": "投入", "amount": 490000},
    ).status_code == 200
    # 本期净投入
    assert client.post(
        "/portfolio-cash-flows",
        json={"date": "2026-08-01", "flow_type": "投入", "amount": 10000},
    ).status_code == 200

    summary = client.get("/performance/summary", params={"start_date": "2026-08-01"}).json()
    assert summary["period_gain"] is None
    assert summary["period_gain_pct"] is None
    # 全周期口径仍然可用，前端据此回退展示
    assert summary["total_gain"] is not None
    assert summary["total_gain_pct"] is not None


def test_period_gain_still_computed_when_all_capital_in_period(client):
    """本期之前没有任何在册资金时，净投入即全部本金，仍可正常算期间收益。"""
    assert client.put("/securities-cash", json={"amount": 0}).status_code == 200
    assert client.post("/transactions", json={
        "date": "2026-01-02", "code": "600111", "name": "回归标的", "category": "A股权益",
        "account": "华泰证券", "direction": "买入", "quantity": 100, "price": 10,
        "amount": 1000, "fee": 0, "remark": "",
    }).status_code == 200
    assert client.post(
        "/portfolio-cash-flows",
        json={"date": "2026-01-01", "flow_type": "投入", "amount": 1000},
    ).status_code == 200

    summary = client.get("/performance/summary", params={"start_date": "2026-01-01"}).json()
    # 全部本金都在本期 → period_net(1000) == net_contribution(1000)，可以算
    assert summary["period_gain"] is not None
    assert summary["period_gain_pct"] is not None


# ----------------------------- 问题 2 -----------------------------

def test_target_return_pct_is_percentage(client):
    """前端 performance.js 直接把该值拼上 '%'，必须是 4.0 而不是 0.04。"""
    summary = client.get("/performance/summary").json()
    assert abs(summary["target_return_pct"] - 4.0) < 1e-9


# ----------------------------- 问题 3 -----------------------------

def test_daily_returns_strip_cash_flows():
    """一次 100 万转入不能被当成行情暴涨（TWR 与 Sharpe 共用此序列）。"""
    rets = _daily_returns(
        [100000.0, 1100000.0],
        dates=["2026-01-01", "2026-01-02"],
        flows_by_date={"2026-01-02": 1000000.0},
    )
    assert len(rets) == 1
    assert abs(rets[0] - 0.0) < 1e-9


def test_daily_returns_keeps_market_move():
    """无现金流时就是普通日收益。"""
    rets = _daily_returns([100.0, 110.0, 121.0])
    assert len(rets) == 2
    assert abs(rets[0] - 0.1) < 1e-9
    assert abs(rets[1] - 0.1) < 1e-9


def test_flows_between_is_half_open_interval():
    """区间为 (lo, hi]：左开右闭，与快照日期约定一致。"""
    dates, cum = _flow_prefix_sums({"2026-01-01": 100.0, "2026-01-05": 50.0, "2026-01-10": -20.0})
    # (01-01, 01-05] 只含 01-05 的 50，不含 01-01 的 100
    assert abs(_flows_between(dates, cum, "2026-01-01", "2026-01-05") - 50.0) < 1e-9
    # 全区间合计 100 + 50 − 20
    assert abs(_flows_between(dates, cum, "2025-12-31", "2026-01-10") - 130.0) < 1e-9
    # 空区间
    assert abs(_flows_between(dates, cum, "2026-01-05", "2026-01-05") - 0.0) < 1e-9


def test_flows_between_handles_empty():
    dates, cum = _flow_prefix_sums({})
    assert _flows_between(dates, cum, "2026-01-01", "2026-01-31") == 0.0


# ----------------------------- TWR/Sharpe 时间筛选 -----------------------------

def test_twr_and_sharpe_follow_period_filter(client, app_module):
    """选定期间后 TWR/Sharpe 必须按该期间计算，不能永远返回开仓至今。

    全周期 7 个快照 → TWR 131%；从 2026-06-01 起算只剩 4 个 → TWR 15.5%。
    修复前 snap_assets_full 无条件取全量，两个窗口都返回 131%。
    """
    snaps = [
        ("2026-01-01", 100000.0),
        ("2026-02-01", 110000.0),
        ("2026-03-01", 121000.0),
        ("2026-06-01", 200000.0),
        ("2026-07-01", 210000.0),
        ("2026-08-01", 220000.0),
        ("2026-09-01", 231000.0),
    ]
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        for d, v in snaps:
            conn.execute("INSERT INTO daily_snapshots (date, total_assets) VALUES (?, ?)", (d, v))
        conn.commit()
    finally:
        conn.close()

    all_time = client.get("/performance/summary").json()
    period = client.get("/performance/summary", params={"start_date": "2026-06-01"}).json()

    assert abs(all_time["twr"] - 131.0) < 1e-6
    assert abs(period["twr"] - 15.5) < 1e-6
    # Sharpe 与 TWR 同源，也必须跟着窗口变化（两个窗口都有 ≥3 个日收益样本）
    assert all_time["sharpe"] is not None
    assert period["sharpe"] is not None
    assert all_time["sharpe"] != period["sharpe"]


def test_twr_end_date_filter(client, app_module):
    """end_date 同样要生效：区间右端之后的快照不能参与计算。"""
    snaps = [
        ("2026-01-01", 100000.0),
        ("2026-02-01", 110000.0),
        ("2026-03-01", 121000.0),
    ]
    conn = sqlite3.connect(app_module.DB_PATH)
    try:
        for d, v in snaps:
            conn.execute("INSERT INTO daily_snapshots (date, total_assets) VALUES (?, ?)", (d, v))
        conn.commit()
    finally:
        conn.close()

    # 全窗口 [10万→11万→12.1万]：1.1 × 1.1 = 1.21 → 21%
    full = client.get("/performance/summary", params={"start_date": "2026-01-01"}).json()
    # 截止 2026-02-01 只剩 [10万→11万] → 10%
    capped = client.get(
        "/performance/summary", params={"start_date": "2026-01-01", "end_date": "2026-02-01"}
    ).json()

    assert abs(full["twr"] - 21.0) < 1e-6
    assert abs(capped["twr"] - 10.0) < 1e-6


# ----------------------------- SSRF：DNS rebinding -----------------------------

def test_webhook_dns_rebinding_is_pinned(monkeypatch):
    """校验与发请求之间域名被换成 127.0.0.1 时，请求不得落到内网服务上。

    先做阳性对照：不钉死时同样的 rebinding 确实能打到内网服务，
    以此证明这个测试真的构造出了攻击场景，而不是空跑。
    """
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    import requests
    from notify import post_webhook_response

    hits = []

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *args, **kwargs):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    real_getaddrinfo = socket.getaddrinfo
    state = {"resolved_once": False, "rebinding": False}
    HOST = "evil.example"

    def _fake_getaddrinfo(host, port_, *args, **kwargs):
        if host != HOST:
            return real_getaddrinfo(host, port_, *args, **kwargs)
        # 第一次（校验阶段）给一个看起来无害的公网 IP，之后一律换成本地「内网服务」
        if state["rebinding"] and not state["resolved_once"]:
            state["resolved_once"] = True
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port_))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port_))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    url = f"http://{HOST}:{port}/hook"
    try:
        # 阳性对照：不钉死 → rebinding 成功打到内网服务
        state["rebinding"] = False
        try:
            requests.post(url, json={"a": 1}, timeout=2)
        except Exception:
            pass
        assert hits, "阳性对照失败：未钉死时也没打到内网服务，说明 rebinding 场景没构造出来"

        # 实际修复：校验与建连锁定同一 IP → 必须打不到内网服务
        hits.clear()
        state["rebinding"] = True
        state["resolved_once"] = False
        try:
            post_webhook_response(url, {"a": 1}, timeout=2)
        except Exception:
            pass
        assert not hits, f"DNS rebinding 绕过了 SSRF 校验，内网服务被访问: {hits}"
    finally:
        server.shutdown()
        server.server_close()


def test_resolve_webhook_ip_returns_pinned_address():
    """字面 IP 直接返回该 IP；被拦的地址返回错误信息。"""
    from notify import resolve_webhook_ip

    ip, err = resolve_webhook_ip("https://93.184.216.34/hook")
    assert err is None
    assert ip == "93.184.216.34"

    ip, err = resolve_webhook_ip("http://127.0.0.1/hook")
    assert err is not None
    assert ip is None

    ip, err = resolve_webhook_ip("")
    assert err is not None
    assert ip is None
