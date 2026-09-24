"""OpenAI-compatible chat client, config, and call audit.

No vendor SDK. Never raises out of chat()/call_ai().
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from .cash import set_setting
    from .database import LOCAL_TZ, local_today_iso
    from .version import APP_VERSION
except ImportError:
    from cash import set_setting
    from database import LOCAL_TZ, local_today_iso
    from version import APP_VERSION

SETTING_ENABLED = "ai_enabled"
SETTING_BASE_URL = "ai_base_url"
SETTING_API_KEY = "ai_api_key"
SETTING_MODEL = "ai_model"
SETTING_TIMEOUT = "ai_timeout_seconds"
SETTING_SHADOW = "ai_shadow_mode"
SETTING_CAP = "ai_daily_call_cap"
SETTING_FEATURES = "ai_features"

DEFAULT_FEATURES = {"brief": False, "alert_note": False, "nl_rule": False}
DEFAULT_TIMEOUT = 8
DEFAULT_CAP = 30
AI_LOG_KEEP_DAYS = 30
# 供应方前面常挂 Cloudflare：urllib 默认 UA "Python-urllib/x.y" 会命中 CF 1010 被 403
# （2026-09-25 实测 api.anemy.org：Python-urllib → 403 error code: 1010；下面这个 → 200）
USER_AGENT = "invest-tracker/%s (+https://github.com/kofwj/invest-tracker)" % APP_VERSION

ENV_MAP = {
    SETTING_ENABLED: "AI_ENABLED",
    SETTING_BASE_URL: "AI_BASE_URL",
    SETTING_API_KEY: "AI_API_KEY",
    SETTING_MODEL: "AI_MODEL",
    SETTING_TIMEOUT: "AI_TIMEOUT_SECONDS",
    SETTING_SHADOW: "AI_SHADOW_MODE",
    SETTING_CAP: "AI_DAILY_CALL_CAP",
}


@dataclass(frozen=True)
class AiConfig:
    enabled: bool
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    shadow_mode: bool
    daily_call_cap: int
    features: Dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_FEATURES))


def ensure_ai_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_call_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            feature TEXT,
            model TEXT,
            shadow INTEGER DEFAULT 0,
            ok INTEGER DEFAULT 0,
            reason TEXT,
            status_code INTEGER,
            duration_ms INTEGER,
            tokens INTEGER,
            payload_json TEXT,
            output_text TEXT,
            warnings_json TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_call_log_created ON ai_call_log(created_at)"
    )
    ensure_ai_log_columns(conn)


def ensure_ai_log_columns(conn) -> None:
    cols = []
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(ai_call_log)").fetchall()]
    except sqlite3.OperationalError:
        return
    if cols and "warnings_json" not in cols:
        conn.execute("ALTER TABLE ai_call_log ADD COLUMN warnings_json TEXT")


def purge_ai_call_log(conn, *, as_of: str) -> None:
    day = str(as_of or local_today_iso())[:10]
    try:
        as_of_d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return
    cut = (as_of_d - timedelta(days=AI_LOG_KEEP_DAYS)).isoformat()
    try:
        conn.execute("DELETE FROM ai_call_log WHERE substr(created_at,1,10) < ?", (cut,))
    except sqlite3.OperationalError:
        pass


def _now_local() -> datetime:
    if LOCAL_TZ is not None:
        return datetime.now(LOCAL_TZ).replace(tzinfo=None)
    return datetime.now()


def _get_setting(conn, key: str) -> Optional[str]:
    if conn is None:
        return None
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        value = row["value"] if hasattr(row, "keys") else row[0]
        if value is None:
            return None
        return str(value)
    except Exception:
        return None


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def _as_bool(raw: Optional[str], default: bool = False) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _as_int(raw: Optional[str], default: int) -> int:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def _pref(conn, key: str, default: str = "") -> str:
    # Non-None DB value wins, including "" (UI cleared the key).
    db_val = _get_setting(conn, key)
    if db_val is not None:
        return str(db_val).strip()
    env_name = ENV_MAP.get(key)
    if env_name:
        env_val = _env(env_name)
        if env_val:
            return env_val
    return default


def mask_key(key: str) -> str:
    """'' → ''; 'sk-abcdef1234' → 'sk-****1234'. Short keys never leak."""
    value = str(key or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    tail = value[-4:]
    if value.startswith("sk-"):
        return "sk-****" + tail
    return "****" + tail


def normalize_chat_url(base_url: str) -> str:
    """Strip trailing slash; default-append /v1 if missing; then /chat/completions."""
    url = str(base_url or "").strip()
    if not url:
        return ""
    url = url.rstrip("/")
    lower = url.lower()
    if lower.endswith("/chat/completions"):
        return url
    segments = [p for p in url.split("/")]
    path_parts = segments[3:] if len(segments) > 3 else segments
    has_v1 = any(p.lower() == "v1" for p in path_parts)
    if not has_v1:
        url = url + "/v1"
    if not url.lower().endswith("/chat/completions"):
        url = url + "/chat/completions"
    return url


def normalize_models_url(base_url: str) -> str:
    """base_url → …/v1/models（与 chat 用同一套补全规则）。"""
    chat_url = normalize_chat_url(base_url)
    if not chat_url:
        return ""
    suffix = "/chat/completions"
    if chat_url.endswith(suffix):
        return chat_url[: -len(suffix)] + "/models"
    return chat_url.rstrip("/") + "/models"


def _parse_features(raw: Optional[str]) -> Dict[str, bool]:
    out = dict(DEFAULT_FEATURES)
    if not raw:
        return out
    try:
        data = json.loads(raw)
    except Exception:
        return out
    if not isinstance(data, dict):
        return out
    for key in DEFAULT_FEATURES:
        if key in data:
            out[key] = bool(data[key])
    return out


def load_ai_config(conn=None) -> AiConfig:
    # Non-None DB value wins (including "" / "0"); missing key falls back to env.
    db_enabled = _get_setting(conn, SETTING_ENABLED)
    if db_enabled is not None:
        enabled = _as_bool(db_enabled, default=False)
    else:
        enabled = _as_bool(_env("AI_ENABLED"), default=False)

    db_shadow = _get_setting(conn, SETTING_SHADOW)
    if db_shadow is not None:
        shadow = _as_bool(db_shadow, default=True)
    else:
        env_shadow = _env("AI_SHADOW_MODE")
        shadow = _as_bool(env_shadow, default=True) if env_shadow else True

    timeout = _as_int(_pref(conn, SETTING_TIMEOUT, str(DEFAULT_TIMEOUT)), DEFAULT_TIMEOUT)
    if timeout <= 0:
        timeout = DEFAULT_TIMEOUT
    cap = _as_int(_pref(conn, SETTING_CAP, str(DEFAULT_CAP)), DEFAULT_CAP)
    features_raw = _get_setting(conn, SETTING_FEATURES)
    return AiConfig(
        enabled=enabled,
        base_url=_pref(conn, SETTING_BASE_URL, ""),
        api_key=_pref(conn, SETTING_API_KEY, ""),
        model=_pref(conn, SETTING_MODEL, ""),
        timeout_seconds=timeout,
        shadow_mode=shadow,
        daily_call_cap=cap,
        features=_parse_features(features_raw),
    )


def _count_today_calls(conn, day: str, *, used_only: bool) -> int:
    try:
        if used_only:
            sql = (
                "SELECT COUNT(*) AS n FROM ai_call_log "
                "WHERE created_at LIKE ? AND ok = 1 AND IFNULL(feature,'') != 'test'"
            )
        else:
            sql = "SELECT COUNT(*) AS n FROM ai_call_log WHERE created_at LIKE ?"
        row = conn.execute(sql, (day + "%",)).fetchone()
        return int((row["n"] if hasattr(row, "keys") else row[0]) or 0)
    except sqlite3.OperationalError:
        return 0


def _public_config(cfg: AiConfig, conn=None) -> Dict[str, Any]:
    today = local_today_iso()
    today_calls = 0
    today_used = 0
    last_error = None
    recent: List[Dict[str, Any]] = []
    if conn is not None:
        today_calls = _count_today_calls(conn, today, used_only=False)
        today_used = _count_today_calls(conn, today, used_only=True)
        try:
            fail = conn.execute(
                "SELECT reason FROM ai_call_log WHERE ok = 0 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if fail:
                last_error = fail["reason"] if hasattr(fail, "keys") else fail[0]
            logs = conn.execute(
                """
                SELECT created_at, feature, model, shadow, ok, reason, status_code,
                       duration_ms, tokens, output_text
                FROM ai_call_log
                ORDER BY id DESC
                LIMIT 10
                """
            ).fetchall()
            for item in logs:
                if hasattr(item, "keys"):
                    recent.append({k: item[k] for k in item.keys()})
                else:
                    recent.append(
                        {
                            "created_at": item[0],
                            "feature": item[1],
                            "model": item[2],
                            "shadow": item[3],
                            "ok": item[4],
                            "reason": item[5],
                            "status_code": item[6],
                            "duration_ms": item[7],
                            "tokens": item[8],
                            "output_text": item[9],
                        }
                    )
        except sqlite3.OperationalError:
            pass
    return {
        "enabled": cfg.enabled,
        "base_url": cfg.base_url,
        "model": cfg.model,
        "timeout_seconds": cfg.timeout_seconds,
        "shadow_mode": cfg.shadow_mode,
        "daily_call_cap": cfg.daily_call_cap,
        "features": dict(cfg.features),
        "api_key_masked": mask_key(cfg.api_key),
        "api_key_configured": bool(cfg.api_key),
        "available": ai_available(cfg),
        "today_calls": today_calls,
        "today_used": today_used,
        "last_error": last_error,
        "recent": recent,
    }


def save_ai_config(conn, payload: Dict[str, Any]) -> Dict[str, Any]:
    """payload['api_key'] empty string = keep existing key. Returns masked config."""
    payload = payload or {}
    current = load_ai_config(conn)

    if "enabled" in payload and payload["enabled"] is not None:
        set_setting(conn, SETTING_ENABLED, "1" if payload["enabled"] else "0")
    if "base_url" in payload and payload["base_url"] is not None:
        set_setting(conn, SETTING_BASE_URL, str(payload["base_url"]).strip())
    if "model" in payload and payload["model"] is not None:
        set_setting(conn, SETTING_MODEL, str(payload["model"]).strip())
    if "timeout_seconds" in payload and payload["timeout_seconds"] is not None:
        timeout = _as_int(str(payload["timeout_seconds"]), current.timeout_seconds)
        set_setting(conn, SETTING_TIMEOUT, max(1, timeout))
    if "shadow_mode" in payload and payload["shadow_mode"] is not None:
        set_setting(conn, SETTING_SHADOW, "1" if payload["shadow_mode"] else "0")
    if "daily_call_cap" in payload and payload["daily_call_cap"] is not None:
        cap = _as_int(str(payload["daily_call_cap"]), current.daily_call_cap)
        set_setting(conn, SETTING_CAP, max(0, cap))
    if "features" in payload and isinstance(payload["features"], dict):
        merged = dict(current.features)
        for key in DEFAULT_FEATURES:
            if key in payload["features"]:
                merged[key] = bool(payload["features"][key])
        set_setting(conn, SETTING_FEATURES, json.dumps(merged, ensure_ascii=False))

    if payload.get("clear_api_key"):
        set_setting(conn, SETTING_API_KEY, "")
    else:
        new_key = payload.get("api_key")
        if new_key is not None and str(new_key).strip() != "":
            set_setting(conn, SETTING_API_KEY, str(new_key).strip())

    cfg = load_ai_config(conn)
    return _public_config(cfg, conn)


def ai_available(cfg: AiConfig) -> bool:
    """enabled and base_url/model/api_key are all non-empty."""
    return bool(
        cfg.enabled
        and str(cfg.base_url or "").strip()
        and str(cfg.model or "").strip()
        and str(cfg.api_key or "").strip()
    )


def ai_budget_ok(conn, cfg: AiConfig, now=None) -> bool:
    """True if today's successful non-test calls < cap. cap<=0 unlimited."""
    if cfg.daily_call_cap <= 0:
        return True
    if now is None:
        now = _now_local()
    day = now.date().isoformat() if hasattr(now, "date") else str(now)[:10]
    return _count_today_calls(conn, day, used_only=True) < cfg.daily_call_cap


def _headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "Bearer " + str(api_key or ""),
        "User-Agent": USER_AGENT,
    }


_TAG_RE = re.compile(r"<[^>]+>")


def _provider_error(raw: str) -> str:
    """供应方给的可读原因：JSON 的 error.message / 纯文本 / HTML 去标签，截 160 字。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    data = None
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("type") or ""
            if msg:
                return str(msg)[:160]
        elif isinstance(err, str) and err.strip():
            return err.strip()[:160]
        for key in ("message", "detail", "msg"):
            if data.get(key):
                return str(data[key])[:160]
    plain = _TAG_RE.sub(" ", text) if "<" in text else text
    return " ".join(plain.split())[:160]


def _get_raw(url: str, api_key: str, timeout: int):
    """GET JSON. Returns (status_code, body_text). Raises TimeoutError on timeout."""
    req = urllib.request.Request(url, headers=_headers(api_key), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=max(1, int(timeout))) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return int(getattr(resp, "status", 200) or 200), raw
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(exc)
        return int(exc.code or 0), raw
    except TimeoutError:
        raise
    except socket.timeout as exc:
        raise TimeoutError(str(exc)) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, socket.timeout) or "timed out" in str(exc).lower():
            raise TimeoutError(str(exc)) from exc
        raise


def _post_chat(url: str, api_key: str, payload: Dict[str, Any], timeout: int):
    """POST JSON. Returns (status_code, body_text). Raises TimeoutError on timeout."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers=_headers(api_key),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=max(1, int(timeout))) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return int(getattr(resp, "status", 200) or 200), raw
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(exc)
        return int(exc.code or 0), raw
    except TimeoutError:
        raise
    except socket.timeout as exc:
        raise TimeoutError(str(exc)) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, socket.timeout) or "timed out" in str(exc).lower():
            raise TimeoutError(str(exc)) from exc
        raise


def chat(
    cfg: AiConfig,
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 400,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """Never raises. Returns ok/text/tokens/status or ok=False/reason/status."""
    url = normalize_chat_url(cfg.base_url)
    payload = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
    }
    try:
        status, raw = _post_chat(url, cfg.api_key, payload, cfg.timeout_seconds)
    except TimeoutError:
        return {"ok": False, "reason": "timeout", "status": None}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:200], "status": None}

    if status >= 400:
        detail = _provider_error(raw)
        reason = "http_%s" % status
        if detail:
            reason = "%s: %s" % (reason, detail)
        return {"ok": False, "reason": reason, "status": status, "provider_error": detail}

    try:
        data = json.loads(raw)
    except Exception:
        return {"ok": False, "reason": "invalid_json", "status": status}

    if not isinstance(data, dict):
        return {"ok": False, "reason": "invalid_json", "status": status}

    choices = data.get("choices")
    if not choices:
        return {"ok": False, "reason": "empty_choices", "status": status}

    first = choices[0] if isinstance(choices, list) else None
    if not isinstance(first, dict):
        return {"ok": False, "reason": "empty_choices", "status": status}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    text = message.get("content")
    if text is None:
        text = first.get("text")
    text = "" if text is None else str(text)

    tokens = None
    usage = data.get("usage")
    if isinstance(usage, dict):
        try:
            tokens = int(usage.get("total_tokens"))
        except (TypeError, ValueError):
            tokens = None
    return {"ok": True, "text": text, "tokens": tokens, "status": status}


def _write_audit(
    conn,
    *,
    cfg: AiConfig,
    feature: str,
    ok: bool,
    reason: Optional[str],
    status: Optional[int],
    duration_ms: int,
    tokens: Optional[int],
    payload: Any,
    output: Optional[str],
    warnings: Optional[List[str]] = None,
) -> Optional[int]:
    created = _now_local().strftime("%Y-%m-%d %H:%M:%S")
    warnings_json = json.dumps(warnings or [], ensure_ascii=False)[:4000]
    payload_json = json.dumps(payload, ensure_ascii=False)[:4000] if payload is not None else ""
    args = (
        created,
        feature,
        cfg.model,
        1 if cfg.shadow_mode else 0,
        1 if ok else 0,
        (reason or "")[:200],
        status,
        duration_ms,
        tokens,
        payload_json,
        (output or "")[:4000],
        warnings_json,
    )
    try:
        cur = conn.execute(
            """
            INSERT INTO ai_call_log (
                created_at, feature, model, shadow, ok, reason, status_code,
                duration_ms, tokens, payload_json, output_text, warnings_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            args,
        )
        return cur.lastrowid
    except sqlite3.OperationalError:
        try:
            cur = conn.execute(
                """
                INSERT INTO ai_call_log (
                    created_at, feature, model, shadow, ok, reason, status_code,
                    duration_ms, tokens, payload_json, output_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                args[:-1],
            )
            return cur.lastrowid
        except Exception:
            logger.exception("failed to write ai_call_log")
            return None
    except Exception:
        logger.exception("failed to write ai_call_log")
        return None


def stamp_ai_warnings(conn, audit_id, warnings) -> None:
    if not audit_id:
        return
    try:
        conn.execute(
            "UPDATE ai_call_log SET warnings_json = ? WHERE id = ?",
            (json.dumps(warnings or [], ensure_ascii=False)[:4000], int(audit_id)),
        )
    except Exception:
        logger.exception("failed to stamp ai_call_log warnings")


def call_ai(
    conn,
    cfg: AiConfig,
    feature: str,
    messages,
    *,
    max_tokens: int = 400,
    temperature: float = 0.2,
    timeout_seconds: Optional[int] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Guarded chat(): availability → budget → call → audit. Never raises."""
    import time as _time

    if not cfg.enabled:
        return {"ok": False, "reason": "disabled", "status": None}
    if feature in DEFAULT_FEATURES and not bool(cfg.features.get(feature)):
        return {"ok": False, "reason": "feature_disabled", "status": None}
    if not ai_available(cfg):
        return {"ok": False, "reason": "not_configured", "status": None}
    if not ai_budget_ok(conn, cfg):
        _write_audit(
            conn,
            cfg=cfg,
            feature=feature,
            ok=False,
            reason="budget",
            status=None,
            duration_ms=0,
            tokens=None,
            payload={"feature": feature},
            output="",
            warnings=warnings,
        )
        return {"ok": False, "reason": "budget", "status": None}

    cfg_use = cfg
    if timeout_seconds is not None:
        try:
            timeout = max(1, int(timeout_seconds))
        except (TypeError, ValueError):
            timeout = cfg.timeout_seconds
        cfg_use = replace(cfg, timeout_seconds=timeout)

    started = _time.monotonic()
    result = chat(cfg_use, list(messages or []), max_tokens=max_tokens, temperature=temperature)
    duration_ms = int((_time.monotonic() - started) * 1000)
    result["duration_ms"] = duration_ms
    safe_payload = {
        "model": cfg_use.model,
        "feature": feature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": m.get("role"), "content": str(m.get("content") or "")[:500]}
            for m in (messages or [])
            if isinstance(m, dict)
        ],
    }
    audit_id = _write_audit(
        conn,
        cfg=cfg_use,
        feature=feature,
        ok=bool(result.get("ok")),
        reason=None if result.get("ok") else str(result.get("reason") or ""),
        status=result.get("status"),
        duration_ms=duration_ms,
        tokens=result.get("tokens"),
        payload=safe_payload,
        output=result.get("text") if result.get("ok") else "",
        warnings=warnings,
    )
    result["audit_id"] = audit_id
    return result


def ai_status(conn) -> Dict[str, Any]:
    cfg = load_ai_config(conn)
    return _public_config(cfg, conn)



def fetch_models(cfg: AiConfig, *, timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
    """GET {base}/models —— 设置页据此列真实模型名。Never raises，不计额度、不写审计。"""
    url = normalize_models_url(cfg.base_url)
    out: Dict[str, Any] = {
        "ok": False,
        "request_url": url,
        "ids": [],
        "display": {},
        "status": None,
        "error": "",
    }
    if not url:
        out["error"] = "base_url 未配置"
        return out
    if not str(cfg.api_key or "").strip():
        out["error"] = "api_key 未配置"
        return out
    timeout = _as_int(str(timeout_seconds or cfg.timeout_seconds), DEFAULT_TIMEOUT)
    try:
        status, raw = _get_raw(url, cfg.api_key, timeout)
    except TimeoutError:
        out["error"] = "timeout"
        return out
    except Exception as exc:
        out["error"] = str(exc)[:160]
        return out
    out["status"] = status
    if status >= 400:
        out["error"] = _provider_error(raw) or ("http_%s" % status)
        return out
    try:
        data = json.loads(raw)
    except Exception:
        out["error"] = "invalid_json"
        return out
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        out["error"] = "no_models_field"
        return out
    for item in rows:
        if isinstance(item, dict) and item.get("id"):
            mid = str(item["id"]).strip()
            if not mid:
                continue
            out["ids"].append(mid)
            label = item.get("display_name") or item.get("name")
            if label:
                out["display"][mid] = str(label)[:80]
        elif isinstance(item, str) and item.strip():
            out["ids"].append(item.strip())
    out["ids"] = sorted(set(out["ids"]))
    out["ok"] = bool(out["ids"])
    if not out["ok"]:
        out["error"] = "empty"
    return out
