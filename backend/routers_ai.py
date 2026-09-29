"""AI config / status / connection-test API."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Response
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
    from .ai_entry import ENTRY_MAX_UTTERANCE, parse_entry_draft
    from .ai_nl_rule import NL_RULE_MAX_UTTERANCE, parse_rule_draft
    from .ai_usage import ai_usage_summary, audit_csv, audit_filename, audit_json
    from .ai_notice import classify_notice_points
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
    from ai_entry import ENTRY_MAX_UTTERANCE, parse_entry_draft
    from ai_nl_rule import NL_RULE_MAX_UTTERANCE, parse_rule_draft
    from ai_usage import ai_usage_summary, audit_csv, audit_filename, audit_json
    from ai_notice import classify_notice_points
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


class EntryBody(BaseModel):
    utterance: str = ""


@router.post("/ai/nl-entry")
def post_nl_entry(body: EntryBody):
    """一句话记账 → 交易草稿。AI 只填字段，不落库（写库仍走 POST /transactions）。"""
    text = str(body.utterance or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="请先说一句要记的交易")
    if len(text) > ENTRY_MAX_UTTERANCE:
        # 超长在花钱之前就拦掉：既省额度，也避免把长文丢给供应商。
        raise HTTPException(status_code=400, detail="原话过长（限 %d 字）" % ENTRY_MAX_UTTERANCE)
    with db_session() as conn:
        result = parse_entry_draft(conn, text)
        conn.commit()
    return result


class RuleBody(BaseModel):
    utterance: str = ""


@router.post("/ai/nl-rule")
def post_nl_rule(body: RuleBody):
    """一句话 → 预警规则草稿。AI 只产草稿，写库仍走 POST /market/alert-rules。"""
    text = str(body.utterance or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="请先说一句要设的规则")
    if len(text) > NL_RULE_MAX_UTTERANCE:
        raise HTTPException(status_code=400, detail="原话过长（限 %d 字）" % NL_RULE_MAX_UTTERANCE)
    with db_session() as conn:
        result = parse_rule_draft(conn, text)
        conn.commit()
    return result


@router.get("/ai/usage")
def get_ai_usage(days: int = 7):
    """近 N 天用量与命中率（只读）。days 会被夹到 1..30。"""
    with db_session() as conn:
        return ai_usage_summary(conn, days=days)


@router.get("/ai/audit/export")
def get_ai_audit_export(days: int = 7, format: str = "json"):
    """导出窗口内的调用审计（不含密钥）。json 自带窗口信息，csv 是纯表格。"""
    fmt = str(format or "json").strip().lower()
    if fmt not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="format 只支持 json 或 csv")
    with db_session() as conn:
        body = audit_json(conn, days=days) if fmt == "json" else audit_csv(conn, days=days)
    media = "application/json" if fmt == "json" else "text/csv"
    return Response(
        content=body,
        media_type=media + "; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="%s"' % audit_filename(fmt)},
    )


@router.get("/ai/notice-class/{code}")
def get_notice_class(code: str, refresh: int = Query(default=0, ge=0, le=1)):
    """公告要点分类（N4）：只读缓存、命中才生成；只给站内看，不进推送。

    refresh=1（用户点弹窗里的「刷新」）跳过缓存读，重跑一次分类：空结果要等到
    16:40 之后才会自动重算，用户在此之前想再试一次只能自己触发。
    """
    text = str(code or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="code 不能为空")
    with db_session() as conn:
        result = classify_notice_points(conn, text, refresh=bool(refresh))
        conn.commit()
    return result
