import os
import time
import hmac
import hashlib
import logging
import threading
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import Header, HTTPException, APIRouter, Request
from pydantic import BaseModel

PASSWORD_ENV_VAR = "INVEST_TRACKER_PASSWORD"
router = APIRouter()
logger = logging.getLogger(__name__)

# In-process login throttle (enough for single uvicorn worker personal deploy).
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "5"))
LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "600"))  # 10 min
LOGIN_LOCK_SECONDS = int(os.environ.get("LOGIN_LOCK_SECONDS", "900"))  # 15 min
_fail_lock = threading.Lock()
_fail_events: Dict[str, Deque[float]] = defaultdict(deque)
_lock_until: Dict[str, float] = {}


class LoginRequest(BaseModel):
    password: str


def get_system_password() -> str:
    pw = os.environ.get(PASSWORD_ENV_VAR, "").strip()
    if len(pw) >= 2:
        if (pw[0] == '"' and pw[-1] == '"') or (pw[0] == "'" and pw[-1] == "'"):
            pw = pw[1:-1]
    return pw


def is_auth_enabled() -> bool:
    return bool(get_system_password())


def get_password_hash() -> bytes:
    pw = get_system_password()
    return hashlib.sha256(pw.encode("utf-8")).digest()


# Token is valid for TOKEN_TTL_DAYS (default 30). Change password invalidates via hash bind.
TOKEN_TTL_DAYS = int(os.environ.get("TOKEN_TTL_DAYS", "30"))
TOKEN_TTL_SECONDS = max(1, TOKEN_TTL_DAYS) * 24 * 3600


def generate_token() -> str:
    timestamp = str(int(time.time()))
    pw_hash = get_password_hash()
    signature = hmac.new(pw_hash, timestamp.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{timestamp}.{signature}"


def verify_token(token: str) -> bool:
    if not token:
        return False
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return False
        timestamp_str, signature = parts
        timestamp = int(timestamp_str)
        if time.time() - timestamp > TOKEN_TTL_SECONDS:
            return False
        pw_hash = get_password_hash()
        expected_signature = hmac.new(
            pw_hash, timestamp_str.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)
    except Exception:
        return False


def client_ip(request: Optional[Request]) -> str:
    if request is None:
        return "unknown"
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        # left-most is original client when behind Caddy/CF
        return xff.split(",")[0].strip() or "unknown"
    real_ip = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _prune_failures(ip: str, now: float) -> None:
    q = _fail_events.get(ip)
    if not q:
        return
    cutoff = now - LOGIN_WINDOW_SECONDS
    while q and q[0] < cutoff:
        q.popleft()
    if not q:
        _fail_events.pop(ip, None)


def is_login_locked(ip: str) -> bool:
    now = time.time()
    with _fail_lock:
        until = _lock_until.get(ip)
        if until is not None:
            if now < until:
                return True
            _lock_until.pop(ip, None)
        _prune_failures(ip, now)
        return False


def register_login_failure(ip: str) -> None:
    now = time.time()
    with _fail_lock:
        _prune_failures(ip, now)
        q = _fail_events[ip]
        q.append(now)
        if len(q) >= LOGIN_MAX_FAILURES:
            _lock_until[ip] = now + LOGIN_LOCK_SECONDS
            q.clear()
            logger.warning("login locked for ip=%s for %ss", ip, LOGIN_LOCK_SECONDS)


def clear_login_failures(ip: str) -> None:
    with _fail_lock:
        _fail_events.pop(ip, None)
        _lock_until.pop(ip, None)


def reset_login_throttle_state() -> None:
    """Test helper: clear all in-memory throttle state."""
    with _fail_lock:
        _fail_events.clear()
        _lock_until.clear()


def require_auth(authorization: str = Header(None)):
    if not is_auth_enabled():
        return

    token = None
    if authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization

    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="Authentication required")


@router.post("/login")
def login(req: LoginRequest, request: Request):
    if not is_auth_enabled():
        return {"status": "success", "token": ""}

    ip = client_ip(request)
    if is_login_locked(ip):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")

    expected = get_system_password()
    # Constant-time compare when lengths match (Py3.9 raises on length mismatch).
    pw_b = req.password.encode("utf-8")
    exp_b = expected.encode("utf-8")
    if len(pw_b) == len(exp_b) and hmac.compare_digest(pw_b, exp_b):
        clear_login_failures(ip)
        token = generate_token()
        return {"status": "success", "token": token}

    register_login_failure(ip)
    logger.warning("login failed for ip=%s", ip)
    raise HTTPException(status_code=400, detail="密码错误")


@router.get("/auth/status")
def auth_status():
    return {"auth_enabled": is_auth_enabled()}
