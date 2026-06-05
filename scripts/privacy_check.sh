#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0
warn() { printf 'WARN: %s\n' "$*" >&2; }
bad() { printf 'FAIL: %s\n' "$*" >&2; fail=1; }

tracked_files="$(git ls-files)"

# Files that should never be tracked in a public repository.
printf '%s\n' "$tracked_files" | grep -E '(^|/)(data|backups)/|\.db$|\.db\.bak$|\.sqlite$|\.sqlite3$|\.env$|\.DS_Store$' \
  && bad '发现不应公开提交的敏感/本地文件（data、backups、db、.env 等）' || true

# Sensitive local paths and machine/user identifiers in tracked text files.
patterns=(
  '/Users/'
  'wangjiandeMac'
  'jian@'
  'wangjian'
  'AKIA[0-9A-Z]{16}'
  'ghp_[A-Za-z0-9_]{20,}'
  'sk-[A-Za-z0-9_-]{20,}'
)

for pat in "${patterns[@]}"; do
  if git grep -n -I -E "$pat" -- . ':!scripts/privacy_check.sh' >/tmp/invest_privacy_hits 2>/dev/null; then
    cat /tmp/invest_privacy_hits >&2
    bad "发现疑似隐私/密钥模式：$pat"
  fi
done

# Screenshot reminder: images may contain real amounts. Warn, do not fail.
if printf '%s\n' "$tracked_files" | grep -E '^docs/screenshots/.*\.(png|jpg|jpeg)$' >/dev/null; then
  warn '仓库包含截图文件，请确认金额/账号等敏感信息已经打码。'
fi

if [ "$fail" -eq 0 ]; then
  echo 'Privacy check passed.'
else
  echo 'Privacy check failed.' >&2
  exit 1
fi
