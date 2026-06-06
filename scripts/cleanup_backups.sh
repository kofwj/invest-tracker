#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-60}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"

if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
  echo "ERROR: BACKUP_RETENTION_DAYS must be a number." >&2
  exit 1
fi

if [ "$RETENTION_DAYS" -lt 7 ]; then
  echo "ERROR: Refusing to keep fewer than 7 days of backups." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
find "$BACKUP_DIR" -type f -name '*.bak' -mtime +"$RETENTION_DAYS" -print -delete
