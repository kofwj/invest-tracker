"""AI config / status / connection-test API."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    from .ai_client import (
        ai_status,
        call_ai,
        fetch_models,
        load_ai_config,
        normalize_chat_url,
        save_ai_config,
    )
    from .database import db_session
except ImportError:
    from ai_client import (
        ai_status,
        call_ai,
        fetch_models,
        load_ai_config,
        normalize_chat_url,
        save_ai_config,
    )
    from database import db_session

router = APIRouter(tags=["ai"])


class AiConfigBody(BaseModel):
    enabled: Optional[bool] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=120)
    shadow_mode: Optional[bool] = None
    daily_call_cap: Optional[int] = Field(default=None, ge=0, le=10000)
    features: Optional[Dict[str, Any]] = None
    clear_api_key: Optional[bool] = None


@router.get("/ai/status")
def get_ai_status():
    with db_session() as conn:
        return ai_status(conn)


@router.put("/ai/config")
def put_ai_config(body: AiConfigBody):
    with db_session() as conn:
        data = save_ai_config(conn, body.model_dump())
        conn.commit()
    return data


@router.post("/ai/test")
def post_ai_test():
    with db_session() as conn:
        cfg = load_ai_config(conn)
        request_url = normalize_chat_url(cfg.base_url) if cfg.base_url else ""
        result = call_ai(
            conn,
            cfg,
            "test",
            [{"role": "user", "content": "ping"}],
            max_tokens=16,
            temperature=0,
        )
        conn.commit()
    return {
        "ok": bool(result.get("ok")),
        "request_url": request_url,
        "status": result.get("status"),
        "duration_ms": result.get("duration_ms"),
        "model": cfg.model,
        "text": result.get("text"),
        "reason": result.get("reason"),
        "provider_error": result.get("provider_error") or "",
    }


@router.get("/ai/models")
def get_ai_models():
    """列出供应方 /models 里的真实模型 id（只读，不计日额度、不写审计）。"""
    with db_session() as conn:
        cfg = load_ai_config(conn)
    data = fetch_models(cfg)
    return {
        "ok": bool(data.get("ok")),
        "request_url": data.get("request_url"),
        "status": data.get("status"),
        "ids": data.get("ids") or [],
        "display": data.get("display") or {},
        "error": data.get("error") or "",
        "model_current": cfg.model,
    }
