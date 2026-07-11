#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and edit it first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

git pull --rebase origin deploy/vps
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
echo
echo "Health check:"
curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${FRONTEND_PORT:-8080}/api/health"
echo

# 清 Docker 构建缓存，避免多次 --build 占满小盘（不影响运行中容器）
if command -v docker >/dev/null 2>&1; then
  echo
  echo "Pruning docker build cache..."
  docker builder prune -f
  docker system df 2>/dev/null || true
fi
