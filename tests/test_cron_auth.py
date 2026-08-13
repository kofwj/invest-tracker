"""Cron API: X-Cron-Token only, independent from login password."""


def test_cron_unconfigured_returns_503(client, monkeypatch):
    monkeypatch.delenv("CRON_API_TOKEN", raising=False)
    response = client.post("/cron/sync-prices")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_cron_rejects_missing_and_wrong_token(client, monkeypatch):
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    assert client.post("/cron/sync-prices").status_code == 401
    assert client.post(
        "/cron/sync-prices",
        headers={"X-Cron-Token": "wrong-token"},
    ).status_code == 401


def test_cron_token_does_not_unlock_user_routes(client, monkeypatch):
    monkeypatch.setenv("INVEST_TRACKER_PASSWORD", "user-pass")
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    response = client.get("/dashboard", headers={"X-Cron-Token": "correct-cron-token"})
    assert response.status_code == 401


def test_cron_trading_day_with_valid_token(client, monkeypatch):
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    response = client.get("/cron/trading-day", headers={"X-Cron-Token": "correct-cron-token"})
    assert response.status_code == 200
    data = response.json()
    assert "is_trading_day" in data
    assert "date" in data


def test_cron_snapshot_with_valid_token(client, monkeypatch):
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    response = client.post("/cron/snapshot", headers={"X-Cron-Token": "correct-cron-token"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] in ("created", "updated")
    assert data.get("date")


def test_cron_check_alerts_and_notify_events(client, monkeypatch):
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    headers = {"X-Cron-Token": "correct-cron-token"}
    alerts = client.post("/cron/check-alerts", headers=headers, json={"notify": False})
    assert alerts.status_code == 200
    assert alerts.json().get("status") == "success"
    events = client.post(
        "/cron/notify-events",
        headers=headers,
        json={"deposit": True, "discipline": True, "force": False},
    )
    assert events.status_code == 200
    assert events.json().get("status") == "success"


def test_login_password_cannot_call_cron(client, monkeypatch):
    monkeypatch.setenv("INVEST_TRACKER_PASSWORD", "user-pass")
    monkeypatch.setenv("CRON_API_TOKEN", "correct-cron-token")
    login = client.post("/login", json={"password": "user-pass"})
    assert login.status_code == 200
    token = login.json()["token"]
    response = client.post("/cron/snapshot", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code in (401, 503)