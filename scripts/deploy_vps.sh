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

# --- 磁盘守卫 ---------------------------------------------------------------
# 这台机器只有 19G，而 docker 构建缓存能长到 8G 以上。盘满时 SQLite 写不了 WAL，
# 后端会以 disk I/O error 崩溃重启、前端也起不来（2026-09-24 真事故）。
# 所以构建之前先看空间：不够先清构建缓存，还是不够就直接拦住，别把生产搞挂。
free_mb() { df -Pm / | awk 'NR==2 {print $4}'; }

FREE=$(free_mb)
if [ "$FREE" -lt 5120 ]; then
  echo "Free space ${FREE}MB < 5GB —— 先清掉全部 docker 构建缓存"
  docker builder prune -af >/dev/null 2>&1 || true
  FREE=$(free_mb)
  echo "清理后可用：${FREE}MB"
fi
if [ "$FREE" -lt 2048 ]; then
  echo "ERROR: 根分区只剩 ${FREE}MB，先腾空间再部署 —— 盘满时后端会 disk I/O error 起不来。" >&2
  echo "       可以看：du -sh /home/* /var/log /var/lib/docker/*；必要时 docker system prune -af（不加 --volumes）" >&2
  exit 1
fi
# ---------------------------------------------------------------------------

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
  echo "部署后可用空间：$(free_mb)MB"
fi
