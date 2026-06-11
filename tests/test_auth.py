import pytest
from fastapi.testclient import TestClient

def test_auth_status_disabled_by_default(client, monkeypatch):
    monkeypatch.setenv("INVEST_TRACKER_PASSWORD", "")
    response = client.get('/auth/status')
    assert response.status_code == 200
    assert response.json()["auth_enabled"] is False

def test_auth_status_enabled_when_env_var_set(client, monkeypatch):
    monkeypatch.setenv("INVEST_TRACKER_PASSWORD", "secret_pass")
    response = client.get('/auth/status')
    assert response.status_code == 200
    assert response.json()["auth_enabled"] is True

def test_login_success_and_failure(client, monkeypatch):
    monkeypatch.setenv("INVEST_TRACKER_PASSWORD", "my_secret_password")
    
    # Fail login
    response = client.post('/login', json={"password": "wrong_password"})
    assert response.status_code == 400
    assert response.json()["detail"] == "密码错误"
    
    # Success login
    response = client.post('/login', json={"password": "my_secret_password"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    token = response.json()["token"]
    assert token != ""
    assert "." in token

def test_protected_endpoints_blocked_when_auth_enabled(client, monkeypatch):
    monkeypatch.setenv("INVEST_TRACKER_PASSWORD", "my_secret_password")
    
    # Access dashboard without token
    response = client.get('/dashboard')
    assert response.status_code == 401
    
    # Access dashboard with invalid token
    response = client.get('/dashboard', headers={"Authorization": "Bearer invalid.token"})
    assert response.status_code == 401
    
    # Login to get valid token
    login_res = client.post('/login', json={"password": "my_secret_password"})
    token = login_res.json()["token"]
    
    # Access dashboard with valid token
    response = client.get('/dashboard', headers={"Authorization": f"Bearer {token}"})
    # Auth is verified, we shouldn't get 401. Status code should be 200 (since dashboard doesn't require complex tables to exist).
    assert response.status_code == 200
