#!/usr/bin/env bash
# 每日自动备份 + 轮转（保留最近 N 份，默认 30）。
# 用法：
#   scripts/backup_daily.sh            # 保留 30 份
#   BACKUP_RETAIN=14 scripts/backup_daily.sh
#
# 建议 crontab（VPS，每天 02:15）：
#   15 2 * * * /home/kofwj/invest-tracker/scripts/backup_daily.sh >> /home/kofwj/invest-tracker/backups/backup_daily.log 2>&1
#
# 心跳（可选，见 backend/heartbeat.py）：
#   配了 CRON_API_TOKEN 就 POST /cron/heartbeat {job:"backup"}，成功失败都报。
#   逾期（默认 30h 没成功）由 /cron/notify-events 喊人；想管「整机死了」这种
#   本机喊不出来的情况，给后端配 HEARTBEAT_BACKUP_URL（healthchecks.io 之类）。
#   上报失败只打日志，绝不让备份本身失败 —— 备份是最后一道防线，不能被上报绑架。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 只从 .env 里挑需要的键，不 source：.env 里的 DB_PATH=/app/data/invest.db 是容器内路径，
# source 进来会让「宿主机 cron + 宿主脚本」备份一个不存在的文件。
env_value() {
  local key="$1"
  [ -f "$ROOT/.env" ] || return 0
  sed -n "s/^[[:space:]]*${key}=//p" "$ROOT/.env" | tail -n 1 | sed -e 's/^["'\'']//' -e 's/["'\'']$//'
}

RETAIN="${BACKUP_RETAIN:-30}"

DB_PATH="${DB_PATH:-$ROOT/data/invest.db}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"

FRONTEND_PORT="${FRONTEND_PORT:-$(env_value FRONTEND_PORT)}"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"
CRON_API_TOKEN="${CRON_API_TOKEN:-$(env_value CRON_API_TOKEN)}"
CRON_API_BASE="${CRON_API_BASE:-http://127.0.0.1:${FRONTEND_PORT}/api}"

report_heartbeat() {  # $1=ok(true|false) $2=detail
  local ok="$1" detail="${2:-}"
  if [ -z "${CRON_API_TOKEN}" ]; then
    echo "[$(ts)] heartbeat skip: 未配置 CRON_API_TOKEN"
    return 0
  fi
  CRON_API_BASE="$CRON_API_BASE" CRON_API_TOKEN="$CRON_API_TOKEN" \
    python3 - "$ok" "$detail" <<'PY' || true
import json
import os
import sys
import urllib.request

ok = sys.argv[1].strip().lower() == "true"
detail = sys.argv[2] if len(sys.argv) > 2 else ""
base = os.environ.get("CRON_API_BASE", "http://127.0.0.1:8080/api").rstrip("/")
token = os.environ.get("CRON_API_TOKEN", "").strip()
body = json.dumps({"job": "backup", "ok": ok, "detail": detail}).encode("utf-8")
req = urllib.request.Request(
    base + "/cron/heartbeat",
    data=body,
    method="POST",
    headers={"Content-Type": "application/json", "X-Cron-Token": token},
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"[heartbeat] {resp.read().decode('utf-8', errors='replace')}")
except Exception as exc:  # 上报失败不能影响备份结果
    print(f"[heartbeat] post failed: {exc}", file=sys.stderr)
PY
}

echo "[$(ts)] daily backup retain=${RETAIN}"
if python3 scripts/backup_db.py --db "$DB_PATH" --backup-dir "$BACKUP_DIR" --label daily --retain "$RETAIN"; then
  echo "[$(ts)] done"
  report_heartbeat true "daily retain=${RETAIN}"
else
  code=$?
  echo "[$(ts)] backup failed (exit ${code})" >&2
  report_heartbeat false "daily exit=${code}"
  exit "$code"
fi
