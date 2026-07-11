import time

import auth as auth_mod


def test_login_rate_limit_locks_after_failures(client, monkeypatch):
    monkeypatch.setenv("INVEST_TRACKER_PASSWORD", "correct-password")
    monkeypatch.setattr(auth_mod, "LOGIN_MAX_FAILURES", 3)
    monkeypatch.setattr(auth_mod, "LOGIN_WINDOW_SECONDS", 600)
    monkeypatch.setattr(auth_mod, "LOGIN_LOCK_SECONDS", 900)
    auth_mod.reset_login_throttle_state()

    for _ in range(3):
        resp = client.post("/login", json={"password": "wrong"})
        assert resp.status_code == 400

    locked = client.post("/login", json={"password": "wrong"})
    assert locked.status_code == 429
    assert "频繁" in locked.json()["detail"]

    # Even correct password is blocked while locked
    still = client.post("/login", json={"password": "correct-password"})
    assert still.status_code == 429


def test_login_success_clears_failures(client, monkeypatch):
    monkeypatch.setenv("INVEST_TRACKER_PASSWORD", "correct-password")
    monkeypatch.setattr(auth_mod, "LOGIN_MAX_FAILURES", 5)
    auth_mod.reset_login_throttle_state()

    client.post("/login", json={"password": "wrong"})
    client.post("/login", json={"password": "wrong"})
    ok = client.post("/login", json={"password": "correct-password"})
    assert ok.status_code == 200
    assert ok.json()["token"]

    # Counter reset: can fail again without immediate lock
    for _ in range(4):
        resp = client.post("/login", json={"password": "wrong"})
        assert resp.status_code == 400
