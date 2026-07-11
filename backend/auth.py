import os
import time
import hmac
import hashlib
from fastapi import Header, HTTPException, APIRouter
from pydantic import BaseModel

PASSWORD_ENV_VAR = "INVEST_TRACKER_PASSWORD"
router = APIRouter()


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
        # Token is valid for 30 days
        if time.time() - timestamp > 30 * 24 * 3600:
            return False
        pw_hash = get_password_hash()
        expected_signature = hmac.new(
            pw_hash, timestamp_str.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)
    except Exception:
        return False


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
def login(req: LoginRequest):
    if not is_auth_enabled():
        return {"status": "success", "token": ""}

    expected = get_system_password()
    # Constant-time compare when lengths match (Py3.9 raises on length mismatch).
    pw_b = req.password.encode("utf-8")
    exp_b = expected.encode("utf-8")
    if len(pw_b) == len(exp_b) and hmac.compare_digest(pw_b, exp_b):
        token = generate_token()
        return {"status": "success", "token": token}
    raise HTTPException(status_code=400, detail="密码错误")


@router.get("/auth/status")
def auth_status():
    return {"auth_enabled": is_auth_enabled()}
