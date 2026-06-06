#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.cloudflare}"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Copy .env.cloudflare.example to $ENV_FILE and edit it first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

git pull --rebase origin deploy/cloudflare-tunnel
docker compose --env-file "$ENV_FILE" -f docker-compose.cloudflare.yml up -d --build
docker compose --env-file "$ENV_FILE" -f docker-compose.cloudflare.yml ps

echo
echo "Local health check:"
curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:${FRONTEND_PORT:-8080}/api/health"
echo
