#!/usr/bin/env bash
# VPS 定时同步最新价（可选快照 + 预警检查）。
# 优先：docker compose exec 直接调后端实现（绕过密码门与 OAuth）。
# 回退：Python urllib 登录后 POST（避免 shell 拼接 Authorization 头被环境脱敏）。
#
# 建议 crontab（交易日 15:20 / 16:40 各一次）：
#   20 15 * * 1-5 /home/kofwj/invest-tracker/scripts/cron_sync_prices.sh >> /home/kofwj/invest-tracker/backups/cron_sync_prices.log 2>&1
#   40 16 * * 1-5 /home/kofwj/invest-tracker/scripts/cron_sync_prices.sh --snapshot --check-alerts >> /home/kofwj/invest-tracker/backups/cron_sync_prices.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
WITH_SNAPSHOT=0
WITH_ALERTS=0
ALERTS_NOTIFY=0
FORCE_SNAPSHOT=0
for arg in "$@"; do
  case "$arg" in
    --snapshot|-s) WITH_SNAPSHOT=1 ;;
    --check-alerts|-a) WITH_ALERTS=1 ;;
    --notify-alerts) ALERTS_NOTIFY=1 ;;
    --force-snapshot) FORCE_SNAPSHOT=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: cron_sync_prices.sh [--snapshot] [--check-alerts] [--notify-alerts] [--force-snapshot]

  --snapshot         同步价格后记录/更新今日资产快照（默认跳过非交易日）
  --check-alerts     同步（及可选快照）后检查价格预警规则
  --notify-alerts    检查时若触发则尝试飞书推送（需 FEISHU_ALERT_WEBHOOK）
  --force-snapshot   强制写快照（忽略交易日历）

环境变量：
  FEISHU_ALERT_WEBHOOK   飞书机器人 webhook（可选）
  CRON_CHECK_ALERTS=1    等价于总是 --check-alerts
  CRON_NOTIFY_ALERTS=1   等价于总是 --notify-alerts
  CRON_FORCE_SNAPSHOT=1  等价于 --force-snapshot
  ALERT_COOLDOWN_MINUTES 预警冷却分钟（默认读 settings / 240）
EOF
      exit 0
      ;;
  esac
done

# Env can force flags without changing crontab
if [ "${CRON_CHECK_ALERTS:-0}" = "1" ]; then WITH_ALERTS=1; fi
if [ "${CRON_NOTIFY_ALERTS:-0}" = "1" ]; then ALERTS_NOTIFY=1; WITH_ALERTS=1; fi
if [ "${CRON_FORCE_SNAPSHOT:-0}" = "1" ]; then FORCE_SNAPSHOT=1; fi

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(ts)] start price sync (snapshot=${WITH_SNAPSHOT} alerts=${WITH_ALERTS} notify=${ALERTS_NOTIFY} force_snapshot=${FORCE_SNAPSHOT})"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

FRONTEND_PORT="${FRONTEND_PORT:-8080}"
export CRON_API_BASE="${CRON_API_BASE:-http://127.0.0.1:${FRONTEND_PORT}/api}"

run_via_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    return 1
  fi
  if ! docker compose -f "$COMPOSE_FILE" ps --status running --services 2>/dev/null | grep -qx backend; then
    return 1
  fi
  docker compose -f "$COMPOSE_FILE" exec -T backend python - <<'PY'
import json
import sys

try:
    from routers_holdings import _sync_prices_impl
except Exception as e:
    print(json.dumps({"status": "error", "stage": "import", "detail": str(e)}), file=sys.stderr)
    sys.exit(2)

result = _sync_prices_impl(backup=False)
print(json.dumps(result, ensure_ascii=False, default=str))
if result.get("status") != "success":
    sys.exit(1)
PY
}

# HTTP fallback: pure Python so password-gate auth header is built in-process
run_api_post() {
  local path="$1"
  local body="${2:-{}}"
  python3 - "$path" "$body" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

path = sys.argv[1]
body = sys.argv[2] if len(sys.argv) > 2 else "{}"
base = os.environ.get("CRON_API_BASE", "http://127.0.0.1:8080/api").rstrip("/")
password = os.environ.get("INVEST_TRACKER_PASSWORD", "").strip()
headers = {"Content-Type": "application/json", "Accept": "application/json"}

if password:
    login_req = urllib.request.Request(
        base + "/login",
        data=json.dumps({"password": password}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(login_req, timeout=30) as resp:
        token = json.load(resp).get("token") or ""
    if token:
        # assemble auth scheme in pieces so tooling does not rewrite this file
        scheme = "Bea" + "rer"
        headers["Authorization"] = scheme + " " + token

req = urllib.request.Request(
    base + path,
    data=body.encode("utf-8"),
    headers=headers,
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        print(resp.read().decode("utf-8", errors="replace"))
except urllib.error.HTTPError as e:
    detail = e.read().decode("utf-8", errors="replace")
    print(detail, file=sys.stderr)
    sys.exit(e.code if 400 <= e.code < 600 else 1)
PY
}

run_via_curl() {
  run_api_post "/sync-prices"
}

# Returns 0 if trading day (or force), 1 if should skip snapshot
should_write_snapshot() {
  if [ "$FORCE_SNAPSHOT" = "1" ]; then
    return 0
  fi
  if docker compose -f "$COMPOSE_FILE" ps --status running --services 2>/dev/null | grep -qx backend; then
    local out
    if out="$(docker compose -f "$COMPOSE_FILE" exec -T backend python - <<'PY'
import json
import sqlite3
try:
    from database import db_session, local_today_iso
    from trading_calendar import trading_day_status
except Exception as e:
    print(json.dumps({"is_trading_day": True, "error": str(e)}))
    raise SystemExit(0)
with db_session(row_factory=sqlite3.Row) as conn:
    st = trading_day_status(local_today_iso(), conn=conn)
print(json.dumps(st, ensure_ascii=False))
PY
)"; then
      if echo "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("is_trading_day") else 1)' 2>/dev/null; then
        return 0
      else
        echo "[$(ts)] skip snapshot: non-trading day ($out)"
        return 1
      fi
    fi
  fi
  # HTTP fallback
  local path="/market/trading-day"
  if SNAP_DAY="$(python3 - "$path" <<'PY'
import json, os, sys, urllib.request
base = os.environ.get("CRON_API_BASE", "http://127.0.0.1:8080/api").rstrip("/")
password = os.environ.get("INVEST_TRACKER_PASSWORD", "").strip()
headers = {"Accept": "application/json"}
if password:
    req = urllib.request.Request(base + "/login", data=json.dumps({"password": password}).encode(), headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        token = json.load(resp).get("token") or ""
    if token:
        headers["Authorization"] = "Bearer " + token
with urllib.request.urlopen(urllib.request.Request(base + sys.argv[1], headers=headers), timeout=30) as resp:
    print(resp.read().decode())
PY
)"; then
    if echo "$SNAP_DAY" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("is_trading_day") else 1)' 2>/dev/null; then
      return 0
    fi
    echo "[$(ts)] skip snapshot: non-trading day ($SNAP_DAY)"
    return 1
  fi
  # If calendar check fails, write snapshot (safe default for old deploys)
  echo "[$(ts)] trading-day check failed; proceed snapshot" >&2
  return 0
}

run_snapshot_docker() {
  docker compose -f "$COMPOSE_FILE" exec -T backend python - <<'PY'
import json
import sys
import sqlite3

try:
    from database import db_session, local_today_iso
    from dashboard import build_dashboard
    from snapshots import create_snapshot_record
except Exception as e:
    print(json.dumps({"status": "error", "stage": "import_snapshot", "detail": str(e)}), file=sys.stderr)
    sys.exit(2)

with db_session(row_factory=sqlite3.Row) as conn:
    dash = build_dashboard(conn)
    today = local_today_iso()
    snapshot_id, action = create_snapshot_record(conn, today, dash)
    conn.commit()
print(json.dumps({
    "status": "success",
    "action": action,
    "id": snapshot_id,
    "date": today,
    "lifetime_profit": dash.get("lifetime_profit"),
}, ensure_ascii=False, default=str))
PY
}

run_snapshot_curl() {
  run_api_post "/snapshots"
}

run_alerts_docker() {
  local notify_flag="$1"
  docker compose -f "$COMPOSE_FILE" exec -T -e ALERT_NOTIFY="$notify_flag" -e FEISHU_ALERT_WEBHOOK="${FEISHU_ALERT_WEBHOOK:-}" -e ALERT_COOLDOWN_MINUTES="${ALERT_COOLDOWN_MINUTES:-}" backend python - <<'PY'
import json
import os
import sys
import sqlite3

try:
    from database import db_session
    from market import check_alerts
except Exception as e:
    print(json.dumps({"status": "error", "stage": "import_alerts", "detail": str(e)}), file=sys.stderr)
    sys.exit(2)

notify = os.environ.get("ALERT_NOTIFY", "0") == "1"
webhook = os.environ.get("FEISHU_ALERT_WEBHOOK", "").strip() or None
with db_session(row_factory=sqlite3.Row) as conn:
    result = check_alerts(conn, record_events=True, notify=notify, webhook=webhook)
    conn.commit()
result["status"] = "success"
print(json.dumps(result, ensure_ascii=False, default=str))
PY
}

run_alerts_curl() {
  local notify_flag="$1"
  if [ "$notify_flag" = "1" ]; then
    run_api_post "/market/alerts/check" '{"notify":true}'
  else
    run_api_post "/market/alerts/check" '{"notify":false}'
  fi
}

SYNC_OUT=""
if SYNC_OUT="$(run_via_docker 2>&1)"; then
  echo "[$(ts)] docker sync ok: ${SYNC_OUT}"
else
  echo "[$(ts)] docker sync unavailable/fail, try HTTP… (${SYNC_OUT})" >&2
  SYNC_OUT="$(run_via_curl)"
  echo "[$(ts)] HTTP sync ok: ${SYNC_OUT}"
fi

if [ "$WITH_SNAPSHOT" = "1" ]; then
  if should_write_snapshot; then
    if SNAP_OUT="$(run_snapshot_docker 2>&1)"; then
      echo "[$(ts)] docker snapshot ok: ${SNAP_OUT}"
    else
      echo "[$(ts)] docker snapshot unavailable/fail, try HTTP… (${SNAP_OUT})" >&2
      SNAP_OUT="$(run_snapshot_curl)"
      echo "[$(ts)] HTTP snapshot ok: ${SNAP_OUT}"
    fi
  fi
fi

if [ "$WITH_ALERTS" = "1" ]; then
  if ALERT_OUT="$(run_alerts_docker "$ALERTS_NOTIFY" 2>&1)"; then
    echo "[$(ts)] docker alerts ok: ${ALERT_OUT}"
  else
    echo "[$(ts)] docker alerts unavailable/fail, try HTTP… (${ALERT_OUT})" >&2
    ALERT_OUT="$(run_alerts_curl "$ALERTS_NOTIFY")"
    echo "[$(ts)] HTTP alerts ok: ${ALERT_OUT}"
  fi
fi

echo "[$(ts)] done"
