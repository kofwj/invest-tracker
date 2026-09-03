"""Multi-channel notify dispatcher for invest-tracker (independent of Hermes).

Channels: feishu, dingtalk, wecom, telegram.
Events: price_alert, evening_brief, deposit_due, discipline, ops, test.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import logging
import os
import threading
import time
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

try:
    from .database import LOCAL_TZ, local_today_iso
except ImportError:
    from database import LOCAL_TZ, local_today_iso  # type: ignore

CHANNEL_KEYS = ("feishu", "dingtalk", "wecom", "telegram")
EVENT_KEYS = (
    "price_alert",
    "evening_brief",
    "deposit_due",
    "discipline",
    "ops",
    "test",
)

# settings key for UI overrides of event→channels
NOTIFY_EVENT_MAP_KEY = "notify_event_channels"
NOTIFY_ENABLED_KEY = "notify_enabled"
NOTIFY_COOLDOWN_KEY = "notify_cooldown_minutes"
NOTIFY_TEMPLATE_KEY = "notify_template"  # short | medium
# 页面可写通道密钥（优先于 .env；.env 仍作兜底）
NOTIFY_CHANNEL_CREDS_KEY = "notify_channel_credentials"
CHANNEL_CRED_FIELDS = (
    "feishu_webhook",
    "feishu_app_id",
    "feishu_app_secret",
    "feishu_open_id",
    "dingtalk_webhook",
    "dingtalk_secret",
    "wecom_webhook",
    "telegram_bot_token",
    "telegram_chat_id",
)

DEFAULT_EVENT_CHANNELS = {
    "price_alert": "feishu,telegram",
    "evening_brief": "feishu",
    "deposit_due": "telegram,feishu",
    "discipline": "feishu",
    "ops": "telegram",
    "test": "feishu,dingtalk,wecom,telegram",
}


def _now_local() -> datetime:
    if LOCAL_TZ is not None:
        return datetime.now(LOCAL_TZ).replace(tzinfo=None)
    return datetime.now()


def ensure_notify_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notify_send_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event TEXT,
            channel TEXT,
            title TEXT,
            body TEXT,
            ok INTEGER DEFAULT 0,
            reason TEXT,
            status_code INTEGER
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notify_send_log_created ON notify_send_log(created_at DESC)"
    )


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _mask_secret(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if len(value) <= 16:
        return "***"
    return value[:12] + "…" + value[-6:]


def _load_channel_creds(conn=None) -> Dict[str, str]:
    """DB-stored channel secrets (may be empty)."""
    out = {k: "" for k in CHANNEL_CRED_FIELDS}
    if conn is None:
        return out
    raw = _get_setting(conn, NOTIFY_CHANNEL_CREDS_KEY)
    if not raw:
        return out
    try:
        data = json.loads(raw)
    except Exception:
        return out
    if not isinstance(data, dict):
        return out
    for key in CHANNEL_CRED_FIELDS:
        val = data.get(key)
        if val is None:
            continue
        out[key] = str(val).strip()
    return out


def _feishu_app_for(db: Dict[str, str]) -> Dict[str, str]:
    """Feishu self-built app credentials (app_id + app_secret + receiver open_id)."""
    return {
        "app_id": db.get("feishu_app_id") or _env("NOTIFY_FEISHU_APP_ID"),
        "app_secret": db.get("feishu_app_secret") or _env("NOTIFY_FEISHU_APP_SECRET"),
        "open_id": db.get("feishu_open_id") or _env("NOTIFY_FEISHU_OPEN_ID"),
    }


FETCH_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
SEND_MSG_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
# Cached per credential pair: changing app_id/app_secret in settings used to
# keep serving the old app's token for up to 90 minutes.
_token_cache: str = ""
_token_cache_key: str = ""
_token_cache_at: float = 0.0


def reset_feishu_token_cache() -> None:
    """Test/ops helper."""
    global _token_cache, _token_cache_key, _token_cache_at
    _token_cache = ""
    _token_cache_key = ""
    _token_cache_at = 0.0


def _feishu_tenant_token(app_id: str, app_secret: str, timeout: int = 8) -> str:
    """Get (and cache) a Feishu tenant_access_token from app_id/app_secret."""
    global _token_cache_at, _token_cache, _token_cache_key
    now = time.time()
    key = f"{app_id}|{hashlib.sha256(app_secret.encode('utf-8')).hexdigest()[:12]}"
    if _token_cache and _token_cache_key == key and now - _token_cache_at < 5400:  # 90min cache, token lives ~2h
        return _token_cache
    import requests

    res = requests.post(
        FETCH_TOKEN_URL,
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=timeout,
    )
    data = res.json()
    code = data.get("code")
    if code not in (0, "0", None) or not data.get("tenant_access_token"):
        raise ValueError(f"飞书换取 token 失败({res.status_code}): {str(data.get('msg') or data)[:200]}")
    _token_cache = str(data["tenant_access_token"])
    _token_cache_key = key
    _token_cache_at = now
    return _token_cache


def _send_feishu_app(app: Dict[str, str], text: str, timeout: int = 10) -> Tuple[bool, Optional[int], str]:
    """Send via self-built app (app_id/app_secret/open_id) through the IM message API."""
    if not (app.get("app_id") and app.get("app_secret") and app.get("open_id")):
        return False, None, "not_configured"
    try:
        token = _feishu_tenant_token(app["app_id"], app["app_secret"])
    except Exception as exc:
        return False, None, str(exc)
    try:
        import requests

        payload = {
            "receive_id": app["open_id"],
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        res = requests.post(
            SEND_MSG_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        data = res.json()
        code = data.get("code")
        ok = code in (0, "0", None)
        reason = None if ok else str(data.get("msg") or res.text or "")[:200]
        return ok, res.status_code, reason or ""
    except Exception as exc:
        return False, None, str(exc)


def channel_config(conn=None) -> Dict[str, Dict[str, Any]]:
    """Return channel readiness. DB settings override .env; secrets stay internal."""
    db = _load_channel_creds(conn)
    feishu = db.get("feishu_webhook") or _env("NOTIFY_FEISHU_WEBHOOK") or _env("FEISHU_ALERT_WEBHOOK")
    feishu_app = _feishu_app_for(db)
    feishu_configured = bool(feishu) or bool(feishu_app["app_id"] and feishu_app["app_secret"] and feishu_app["open_id"])
    feishu_mode = "app" if (feishu_app["app_id"] and feishu_app["app_secret"] and feishu_app["open_id"]) else "webhook"
    dingtalk = db.get("dingtalk_webhook") or _env("NOTIFY_DINGTALK_WEBHOOK")
    dingtalk_secret = db.get("dingtalk_secret") or _env("NOTIFY_DINGTALK_SECRET")
    wecom = db.get("wecom_webhook") or _env("NOTIFY_WECOM_WEBHOOK")
    tg_token = db.get("telegram_bot_token") or _env("NOTIFY_TELEGRAM_BOT_TOKEN")
    tg_chat = db.get("telegram_chat_id") or _env("NOTIFY_TELEGRAM_CHAT_ID")

    return {
        "feishu": {
            "configured": feishu_configured,
            "hint": _mask_secret(feishu_app["app_id"] or feishu),
            "webhook": feishu,
            "app": feishu_app if feishu_mode == "app" else {},
            "mode": feishu_mode if feishu_configured else "",
            "source": "db" if (db.get("feishu_webhook") or db.get("feishu_app_id")) else ("env" if feishu_configured else ""),
        },
        "dingtalk": {
            "configured": bool(dingtalk),
            "hint": _mask_secret(dingtalk),
            "webhook": dingtalk,
            "secret": dingtalk_secret,
            "has_secret": bool(dingtalk_secret),
            "source": "db" if db.get("dingtalk_webhook") else ("env" if dingtalk else ""),
        },
        "wecom": {
            "configured": bool(wecom),
            "hint": _mask_secret(wecom),
            "webhook": wecom,
            "source": "db" if db.get("wecom_webhook") else ("env" if wecom else ""),
        },
        "telegram": {
            "configured": bool(tg_token and tg_chat),
            "hint": f"chat={tg_chat}" if tg_chat else "",
            "bot_token": tg_token,
            "chat_id": tg_chat,
            "source": "db" if (db.get("telegram_bot_token") or db.get("telegram_chat_id")) else (
                "env" if (tg_token or tg_chat) else ""
            ),
        },
    }


def save_channel_credentials(conn, payload: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Merge UI channel secrets into settings.

    Rules per field:
    - missing / None: keep previous
    - \"\": clear
    - non-empty string: set
    """
    if payload is None:
        return _load_channel_creds(conn)
    if not isinstance(payload, dict):
        raise ValueError("channel_credentials 必须是对象")
    current = _load_channel_creds(conn)
    next_vals = dict(current)
    for key in CHANNEL_CRED_FIELDS:
        if key not in payload:
            continue
        raw = payload.get(key)
        if raw is None:
            continue
        next_vals[key] = str(raw).strip()
    _set_setting(conn, NOTIFY_CHANNEL_CREDS_KEY, json.dumps(next_vals, ensure_ascii=False))
    return next_vals


def _get_setting(conn, key: str) -> Optional[str]:
    if conn is None:
        return None
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        return row["value"] if hasattr(row, "keys") else row[0]
    except Exception:
        return None


def _set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def is_notify_enabled(conn=None) -> bool:
    if conn is not None:
        v = _get_setting(conn, NOTIFY_ENABLED_KEY)
        if v is not None and str(v).strip() != "":
            return str(v).strip().lower() in ("1", "true", "yes", "on")
    return _env_bool("NOTIFY_ENABLED", True)


def get_template_mode(conn=None) -> str:
    if conn is not None:
        v = _get_setting(conn, NOTIFY_TEMPLATE_KEY)
        if v in ("short", "medium"):
            return str(v)
    mode = _env("NOTIFY_TEMPLATE", "medium").lower()
    return mode if mode in ("short", "medium") else "medium"


def get_cooldown_minutes(conn=None) -> int:
    if conn is not None:
        v = _get_setting(conn, NOTIFY_COOLDOWN_KEY)
        if v is not None:
            try:
                return max(0, int(v))
            except (TypeError, ValueError):
                pass
    try:
        return max(0, int(_env("NOTIFY_COOLDOWN_MINUTES", "240") or "240"))
    except (TypeError, ValueError):
        return 240


def _parse_channel_list(raw: str) -> List[str]:
    out = []
    for part in str(raw or "").split(","):
        c = part.strip().lower()
        if c in CHANNEL_KEYS and c not in out:
            out.append(c)
    return out


def event_channel_map(conn=None) -> Dict[str, List[str]]:
    """Resolve event → channel list: settings override > env > defaults."""
    result: Dict[str, List[str]] = {}
    stored: Dict[str, Any] = {}
    if conn is not None:
        raw = _get_setting(conn, NOTIFY_EVENT_MAP_KEY)
        if raw:
            try:
                stored = json.loads(raw)
            except Exception:
                stored = {}

    for event in EVENT_KEYS:
        if event in stored and stored[event] is not None:
            result[event] = _parse_channel_list(
                stored[event] if isinstance(stored[event], str) else ",".join(stored[event])
            )
            continue
        env_key = f"NOTIFY_ON_{event.upper()}"
        env_val = _env(env_key)
        if env_val:
            result[event] = _parse_channel_list(env_val)
        else:
            result[event] = _parse_channel_list(DEFAULT_EVENT_CHANNELS.get(event, "feishu"))
    return result


def save_notify_settings(
    conn,
    *,
    enabled: Optional[bool] = None,
    cooldown_minutes: Optional[int] = None,
    template: Optional[str] = None,
    event_channels: Optional[Dict[str, Any]] = None,
    channel_credentials: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_notify_tables(conn)
    if enabled is not None:
        _set_setting(conn, NOTIFY_ENABLED_KEY, "1" if enabled else "0")
    if cooldown_minutes is not None:
        _set_setting(conn, NOTIFY_COOLDOWN_KEY, str(int(cooldown_minutes)))
    if template is not None and template in ("short", "medium"):
        _set_setting(conn, NOTIFY_TEMPLATE_KEY, template)
    if event_channels is not None:
        cleaned = {}
        for k, v in event_channels.items():
            if k not in EVENT_KEYS:
                continue
            if isinstance(v, list):
                cleaned[k] = ",".join(_parse_channel_list(",".join(v)))
            else:
                cleaned[k] = ",".join(_parse_channel_list(str(v)))
        _set_setting(conn, NOTIFY_EVENT_MAP_KEY, json.dumps(cleaned, ensure_ascii=False))
    if channel_credentials is not None:
        save_channel_credentials(conn, channel_credentials)
    return notify_status(conn)


def format_message(
    *,
    title: str,
    body: str,
    event: str,
    template: str = "medium",
) -> str:
    title = (title or "").strip() or "invest-tracker"
    body = (body or "").strip()
    if template == "short":
        if body:
            first = body.splitlines()[0][:200]
            return f"【{title}】{first}"
        return f"【{title}】"
    # medium
    lines = [f"【invest-tracker · {title}】"]
    if event and event != "test":
        lines.append(f"事件: {event}")
    if body:
        lines.append(body)
    lines.append(f"时间: {_now_local().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


def _dingtalk_signed_url(webhook: str, secret: str) -> str:
    if not secret:
        return webhook
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={timestamp}&sign={sign}"


def _is_blocked_ip(ip: str) -> bool:
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # 只拦真正的 SSRF 攻击面：内网/环回/链路本地(169.254 元数据)/未指定地址。
    # 不用 is_reserved：会误伤 198.18/15 等 benchmark/文档段（测试环境 DNS sinkhole 常见）。
    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_unspecified


def resolve_webhook_ip(url: str) -> Tuple[Optional[str], Optional[str]]:
    """校验 webhook，并给出应当实际建连的 IP。

    返回 (ip, error)，两者语义独立：
      - error 非空   → 校验不通过，禁止发送；
      - ip 非空      → 已通过校验、且必须被钉死的目标地址；
      - 两者都为空   → 域名暂时解析不出，放行（连接会自然失败，不构成 SSRF，
                       也避免离线环境误伤合法地址）；此时无从钉死，退化为普通请求。
    """
    if not url:
        return None, "webhook 未配置"
    try:
        parsed = urllib.parse.urlparse(str(url).strip())
    except Exception:
        return None, "webhook URL 无法解析"
    if parsed.scheme not in ("http", "https"):
        return None, "webhook 只允许 http/https"
    host = parsed.hostname
    if not host:
        return None, "webhook 缺少主机名"

    import ipaddress
    import socket

    # 字面 IP：直接判定，且不存在「重解析」问题
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass  # 域名，走 DNS
    else:
        if _is_blocked_ip(host):
            return None, f"webhook 主机指向受限地址 {host}"
        return host, None

    try:
        infos = socket.getaddrinfo(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            proto=socket.IPPROTO_TCP,
        )
    except Exception:
        # 无法解析 → 连接会自然失败，不构成 SSRF；放行避免离线环境下误伤合法地址
        return None, None
    for info in infos:
        ip = info[4][0]
        if _is_blocked_ip(ip):
            return None, f"webhook 主机指向受限地址 {ip}"
    if not infos:
        return None, None
    return infos[0][4][0], None


def validate_webhook_url(url: str) -> Optional[str]:
    """SSRF 防护：Webhook 仅允许 http/https，且主机不能解析到内网/环回/链路本地/未指定地址。

    返回错误信息字符串（不可用），可用则返回 None。
    """
    _, err = resolve_webhook_ip(url)
    return err


# 钉死建连地址时必须串行：urllib3 的 create_connection 是进程级的，并发发送会互相干扰
_WEBHOOK_PIN_LOCK = threading.Lock()


@contextlib.contextmanager
def _pinned_webhook_dns(hostname: str, ip: Optional[str]):
    """把 hostname 的建连目标临时固定为已校验的 ip。

    校验与发请求是两步：requests 在第二步才解析域名，攻击者可控的 DNS 可以在两步之间
    返回不同结果（DNS rebinding），让前置校验形同虚设。这里在 socket 层替换建连地址，
    而 TLS 的 SNI 与 HTTP 的 Host 头仍用原始主机名，因此不影响 HTTPS 证书校验。
    """
    if not ip or not hostname:
        yield
        return
    try:
        import urllib3.util.connection as _ul_conn
    except Exception:
        # requests 的传递依赖拿不到时，退化为不钉死（校验仍然生效）
        yield
        return

    original = _ul_conn.create_connection

    def _create_connection(address, *args, **kwargs):
        if address and address[0] == hostname:
            address = (ip, address[1])
        return original(address, *args, **kwargs)

    with _WEBHOOK_PIN_LOCK:
        _ul_conn.create_connection = _create_connection
        try:
            yield
        finally:
            _ul_conn.create_connection = original


def post_webhook_response(url: str, payload: dict, timeout: int = 10, headers: Optional[dict] = None):
    """校验与发送合为一步：保证「校验通过的那个 IP」就是「实际建连的 IP」。

    返回 requests.Response；校验不通过时抛 ValueError。
    """
    import requests

    pinned_ip, err = resolve_webhook_ip(url)
    if err:
        raise ValueError(err)
    host = urllib.parse.urlparse(str(url).strip()).hostname or ""
    with _pinned_webhook_dns(host, pinned_ip):
        return requests.post(url, json=payload, timeout=timeout, headers=headers)


def _post_json(url: str, payload: dict, timeout: int = 10) -> Tuple[bool, Optional[int], str]:
    try:
        # 校验与建连在同一步完成：校验通过的那个 IP 就是实际连出去的 IP，
        # 否则攻击者可控 DNS 可在两步之间换答案（rebinding）。
        res = post_webhook_response(url, payload, timeout=timeout)
    except Exception as exc:
        # 校验不通过也是 ValueError，与其它网络错误一样作为失败原因返回
        return False, None, str(exc)
    try:
        ok = 200 <= res.status_code < 300
        # some bots return 200 with errcode != 0
        try:
            data = res.json()
            if isinstance(data, dict):
                if data.get("errcode") not in (None, 0, "0"):
                    ok = False
                if data.get("StatusCode") not in (None, 0, "0") and "StatusCode" in data:
                    ok = False
                if data.get("ok") is False:
                    ok = False
        except Exception:
            pass
        reason = None if ok else (res.text or "")[:200]
        return ok, res.status_code, reason or ""
    except Exception as exc:
        return False, None, str(exc)


def send_to_channel(channel: str, text: str, cfg: Optional[Dict] = None, conn=None) -> Dict[str, Any]:
    cfg = cfg or channel_config(conn)
    ch = cfg.get(channel) or {}
    if channel == "feishu":
        webhook = ch.get("webhook") or ""
        if not webhook:
            # 自建应用：app_id + app_secret + open_id
            app = ch.get("app") if isinstance(ch.get("app"), dict) else {}
            ok, code, reason = _send_feishu_app(app, text)
            return {"channel": channel, "ok": ok, "status_code": code, "reason": reason or None}
        ok, code, reason = _post_json(
            webhook,
            {"msg_type": "text", "content": {"text": text}},
        )
        return {"channel": channel, "ok": ok, "status_code": code, "reason": reason or None}

    if channel == "dingtalk":
        webhook = ch.get("webhook") or ""
        if not webhook:
            return {"channel": channel, "ok": False, "reason": "not_configured"}
        url = _dingtalk_signed_url(webhook, ch.get("secret") or "")
        ok, code, reason = _post_json(url, {"msgtype": "text", "text": {"content": text}})
        return {"channel": channel, "ok": ok, "status_code": code, "reason": reason or None}

    if channel == "wecom":
        webhook = ch.get("webhook") or ""
        if not webhook:
            return {"channel": channel, "ok": False, "reason": "not_configured"}
        ok, code, reason = _post_json(
            webhook,
            {"msgtype": "text", "text": {"content": text}},
        )
        return {"channel": channel, "ok": ok, "status_code": code, "reason": reason or None}

    if channel == "telegram":
        token = ch.get("bot_token") or ""
        chat_id = ch.get("chat_id") or ""
        if not token or not chat_id:
            return {"channel": channel, "ok": False, "reason": "not_configured"}
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        ok, code, reason = _post_json(
            url,
            {"chat_id": chat_id, "text": text},
        )
        return {"channel": channel, "ok": ok, "status_code": code, "reason": reason or None}

    return {"channel": channel, "ok": False, "reason": "unknown_channel"}


def _log_send(conn, *, event, channel, title, body, ok, reason, status_code) -> None:
    if conn is None:
        return
    try:
        ensure_notify_tables(conn)
        conn.execute(
            """
            INSERT INTO notify_send_log
                (created_at, event, channel, title, body, ok, reason, status_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now_local().isoformat(sep=" ", timespec="seconds"),
                event,
                channel,
                (title or "")[:120],
                (body or "")[:2000],
                1 if ok else 0,
                (reason or "")[:300] if reason else None,
                status_code,
            ),
        )
    except Exception as exc:
        logger.warning("notify log write failed: %s", exc)


def _in_cooldown(conn, event: str, channel: str, minutes: int) -> bool:
    if conn is None or minutes <= 0:
        return False
    try:
        ensure_notify_tables(conn)
        row = conn.execute(
            """
            SELECT created_at FROM notify_send_log
            WHERE event = ? AND channel = ? AND ok = 1
            ORDER BY id DESC LIMIT 1
            """,
            (event, channel),
        ).fetchone()
        if not row:
            return False
        raw = row["created_at"] if hasattr(row, "keys") else row[0]
        last = datetime.fromisoformat(str(raw).replace("T", " ")[:19])
        return (_now_local() - last) < timedelta(minutes=minutes)
    except Exception:
        return False


def dispatch(
    text: str = "",
    *,
    title: str = "通知",
    event: str = "ops",
    channels: Optional[Sequence[str]] = None,
    conn=None,
    force: bool = False,
    template: Optional[str] = None,
    respect_cooldown: bool = True,
) -> Dict[str, Any]:
    """Send message to one or more channels. Returns summary + per-channel results."""
    event = (event or "ops").strip().lower()
    if event not in EVENT_KEYS:
        event = "ops"

    if not is_notify_enabled(conn) and not force:
        return {
            "sent": False,
            "reason": "notify_disabled",
            "event": event,
            "results": [],
        }

    if channels is None:
        channels = event_channel_map(conn).get(event) or []
    else:
        channels = _parse_channel_list(",".join(channels) if not isinstance(channels, str) else channels)

    if not channels:
        # fallback: any configured channel
        cfg = channel_config(conn)
        channels = [c for c in CHANNEL_KEYS if cfg[c]["configured"]]

    if not channels:
        return {
            "sent": False,
            "reason": "no_channels",
            "event": event,
            "results": [],
        }

    tmpl = template or get_template_mode(conn)
    body_raw = text or ""
    message = format_message(title=title, body=body_raw, event=event, template=tmpl)
    cooldown = 0 if (force or not respect_cooldown or event == "test") else get_cooldown_minutes(conn)
    cfg = channel_config(conn)

    results = []
    any_ok = False
    for ch in channels:
        if ch not in CHANNEL_KEYS:
            continue
        if respect_cooldown and not force and _in_cooldown(conn, event, ch, cooldown):
            item = {
                "channel": ch,
                "ok": False,
                "reason": f"cooldown_{cooldown}m",
                "skipped_cooldown": True,
            }
            results.append(item)
            continue
        item = send_to_channel(ch, message, cfg)
        results.append(item)
        if item.get("ok"):
            any_ok = True
        _log_send(
            conn,
            event=event,
            channel=ch,
            title=title,
            body=message,
            ok=bool(item.get("ok")),
            reason=item.get("reason"),
            status_code=item.get("status_code"),
        )

    return {
        "sent": any_ok,
        "reason": None if any_ok else "all_failed_or_skipped",
        "event": event,
        "title": title,
        "template": tmpl,
        "message_preview": message[:300],
        "results": results,
    }


def list_notify_logs(conn, limit: int = 20) -> List[Dict[str, Any]]:
    ensure_notify_tables(conn)
    limit = max(1, min(int(limit or 20), 100))
    rows = conn.execute(
        """
        SELECT id, created_at, event, channel, title, body, ok, reason, status_code
        FROM notify_send_log
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r) if hasattr(r, "keys") else {
            "id": r[0],
            "created_at": r[1],
            "event": r[2],
            "channel": r[3],
            "title": r[4],
            "body": r[5],
            "ok": r[6],
            "reason": r[7],
            "status_code": r[8],
        }
        d["ok"] = bool(d.get("ok"))
        out.append(d)
    return out


def notify_status(conn=None) -> Dict[str, Any]:
    cfg = channel_config(conn)
    db_creds = _load_channel_creds(conn)
    public_channels = {
        k: {
            "configured": v.get("configured"),
            "hint": v.get("hint"),
            "source": v.get("source") or "",
            **({"has_secret": v.get("has_secret")} if k == "dingtalk" else {}),
        }
        for k, v in cfg.items()
    }
    # 表单不回填明文；只告诉前端哪些字段已有值（可留空不改 / 填空清除）
    credential_flags = {k: bool(db_creds.get(k)) for k in CHANNEL_CRED_FIELDS}
    return {
        "enabled": is_notify_enabled(conn),
        "template": get_template_mode(conn),
        "cooldown_minutes": get_cooldown_minutes(conn),
        "channels": public_channels,
        "event_channels": event_channel_map(conn),
        "events": list(EVENT_KEYS),
        "channel_keys": list(CHANNEL_KEYS),
        "credential_fields": list(CHANNEL_CRED_FIELDS),
        "credential_flags": credential_flags,
        "compat": {
            "FEISHU_ALERT_WEBHOOK": bool(_env("FEISHU_ALERT_WEBHOOK")),
            "NOTIFY_FEISHU_WEBHOOK": bool(_env("NOTIFY_FEISHU_WEBHOOK")),
        },
    }


# ── event builders (B) ──────────────────────────────────────────────


def build_price_alert_text(triggered: List[Dict[str, Any]]) -> str:
    if not triggered:
        return ""
    lines = []
    for t in triggered[:30]:
        lines.append(str(t.get("message") or t))
    if len(triggered) > 30:
        lines.append(f"…共 {len(triggered)} 条")
    return "\n".join(lines)


def notify_price_alerts(triggered: List[Dict[str, Any]], *, conn=None, force: bool = False) -> Dict[str, Any]:
    if not triggered:
        return {"sent": False, "reason": "no_triggers", "results": []}
    text = build_price_alert_text(triggered)
    return dispatch(
        text,
        title="价格预警",
        event="price_alert",
        conn=conn,
        force=force,
        respect_cooldown=False,  # per-rule cooldown already applied upstream
    )


def notify_evening_brief(brief_text: str, *, conn=None, force: bool = False) -> Dict[str, Any]:
    return dispatch(
        brief_text or "（空简报）",
        title="晚间简报",
        event="evening_brief",
        conn=conn,
        force=force,
    )


def check_deposit_due(
    conn,
    *,
    windows: Sequence[int] = (0, 7, 30),
) -> Dict[str, Any]:
    """Find deposits due within windows (days). Returns groups + plain text."""
    today = date.fromisoformat(local_today_iso())
    rows = conn.execute(
        "SELECT id, bank_name, amount, interest_rate, due_date, start_date, remark FROM deposits"
    ).fetchall()
    items = []
    for r in rows:
        d = dict(r) if hasattr(r, "keys") else {
            "id": r[0],
            "bank_name": r[1],
            "amount": r[2],
            "interest_rate": r[3],
            "due_date": r[4],
            "start_date": r[5],
            "remark": r[6],
        }
        due_raw = d.get("due_date")
        if not due_raw:
            continue
        try:
            due = date.fromisoformat(str(due_raw)[:10])
        except ValueError:
            continue
        days_left = (due - today).days
        d["days_left"] = days_left
        items.append(d)

    buckets: Dict[str, List[Dict]] = {
        "overdue": [],
        "d0": [],
        "d7": [],
        "d30": [],
    }
    for d in items:
        days = d["days_left"]
        if days < 0:
            buckets["overdue"].append(d)
        elif days == 0:
            buckets["d0"].append(d)
        elif days <= 7:
            buckets["d7"].append(d)
        elif days <= 30:
            buckets["d30"].append(d)

    lines = []
    if buckets["overdue"]:
        lines.append("⚠ 已到期未处理：")
        for d in buckets["overdue"][:10]:
            lines.append(
                f"· {d.get('bank_name')} ¥{float(d.get('amount') or 0):,.0f} "
                f"到期 {d.get('due_date')}（过期 {abs(d['days_left'])} 天）"
            )
    if buckets["d0"]:
        lines.append("今天到期：")
        for d in buckets["d0"][:10]:
            lines.append(f"· {d.get('bank_name')} ¥{float(d.get('amount') or 0):,.0f}")
    if buckets["d7"]:
        lines.append("7 天内到期：")
        for d in buckets["d7"][:10]:
            lines.append(
                f"· {d.get('bank_name')} ¥{float(d.get('amount') or 0):,.0f} "
                f"→ {d.get('due_date')}（剩 {d['days_left']} 天）"
            )
    if buckets["d30"]:
        lines.append("30 天内到期：")
        for d in buckets["d30"][:10]:
            lines.append(
                f"· {d.get('bank_name')} ¥{float(d.get('amount') or 0):,.0f} "
                f"→ {d.get('due_date')}（剩 {d['days_left']} 天）"
            )

    count = sum(len(v) for v in buckets.values())
    text = "\n".join(lines) if lines else "近 30 天内无存款到期。"
    return {
        "count": count,
        "buckets": {
            k: [
                {
                    "id": x.get("id"),
                    "bank_name": x.get("bank_name"),
                    "amount": x.get("amount"),
                    "due_date": x.get("due_date"),
                    "days_left": x.get("days_left"),
                }
                for x in v
            ]
            for k, v in buckets.items()
        },
        "text": text,
        "has_actionable": count > 0,
    }


def notify_deposit_due(conn, *, force: bool = False) -> Dict[str, Any]:
    info = check_deposit_due(conn)
    if not info.get("has_actionable") and not force:
        return {"sent": False, "reason": "nothing_due", "deposit": info, "results": []}
    result = dispatch(
        info["text"],
        title="存款到期提醒",
        event="deposit_due",
        conn=conn,
        force=force,
    )
    result["deposit"] = info
    return result


def check_discipline_summary(conn) -> Dict[str, Any]:
    try:
        try:
            from .discipline import build_discipline_report
        except ImportError:
            from discipline import build_discipline_report

        report = build_discipline_report(conn)
    except Exception as exc:
        logger.warning("discipline summary failed: %s", exc)
        return {"has_breaches": False, "text": f"纪律报告不可用：{exc}", "breach_count": 0}

    breaches = report.get("breaches") or []
    summary = report.get("summary") or report.get("summary_text") or ""
    lines = []
    if summary:
        lines.append(str(summary)[:300])
    if breaches:
        lines.append(f"破线条数：{len(breaches)}")
        for b in breaches[:8]:
            if isinstance(b, dict):
                lines.append(f"· {b.get('title') or b.get('message') or b.get('text') or b}")
            else:
                lines.append(f"· {b}")
    else:
        lines.append("当前无破线。")

    return {
        "has_breaches": len(breaches) > 0,
        "breach_count": len(breaches),
        "text": "\n".join(lines),
        "summary": summary,
    }


def notify_discipline(conn, *, force: bool = False, only_if_breaches: bool = True) -> Dict[str, Any]:
    info = check_discipline_summary(conn)
    if only_if_breaches and not info.get("has_breaches") and not force:
        return {"sent": False, "reason": "no_breaches", "discipline": info, "results": []}
    result = dispatch(
        info["text"],
        title="纪律破线",
        event="discipline",
        conn=conn,
        force=force,
    )
    result["discipline"] = info
    return result


def run_scheduled_events(
    conn,
    *,
    deposit: bool = True,
    discipline: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    """Cron entry: deposit due + discipline summary."""
    out: Dict[str, Any] = {"ran_at": _now_local().isoformat(sep=" ", timespec="seconds")}
    if deposit:
        out["deposit_due"] = notify_deposit_due(conn, force=force)
    if discipline:
        out["discipline"] = notify_discipline(conn, force=force, only_if_breaches=not force)
    return out
