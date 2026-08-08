#!/usr/bin/env bash
# 每日自动备份 + 轮转（保留最近 N 份，默认 30）。
# 用法：
#   scripts/backup_daily.sh            # 保留 30 份
#   BACKUP_RETAIN=14 scripts/backup_daily.sh
#
# 建议 crontab（VPS，每天 02:15）：
#   15 2 * * * /home/kofwj/invest-tracker/scripts/backup_daily.sh >> /home/kofwj/invest-tracker/backups/backup_daily.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RETAIN="${BACKUP_RETAIN:-30}"

DB_PATH="${DB_PATH:-$ROOT/data/invest.db}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] daily backup retain=${RETAIN}"
python3 scripts/backup_db.py --db "$DB_PATH" --backup-dir "$BACKUP_DIR" --label daily --retain "$RETAIN"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] done"