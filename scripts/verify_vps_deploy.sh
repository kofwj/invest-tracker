#!/usr/bin/env bash
# 一键核对：VPS 更新后是否把关键能力部署到位。
# 在 VPS 仓库根目录执行：./scripts/verify_vps_deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
PASS=0
FAIL=0
WARN=0

ok() { echo "  [OK] $*"; PASS=$((PASS + 1)); }
bad() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }
warn() { echo "  [WARN] $*"; WARN=$((WARN + 1)); }

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

FRONTEND_PORT="${FRONTEND_PORT:-8080}"
BASE="http://127.0.0.1:${FRONTEND_PORT}"

echo "== 1. Git / 分支 =="
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
HEAD="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
if [ "$BRANCH" = "deploy/vps" ]; then
  ok "当前分支 deploy/vps @ ${HEAD}"
else
  warn "当前分支是 ${BRANCH}（建议 deploy/vps）@ ${HEAD}"
fi
if git status --porcelain | grep -q .; then
  warn "工作区有未提交改动（部署后本地脏工作区需注意）"
else
  ok "工作区 clean"
fi

echo
echo "== 2. 数据目录 =="
if [ -d data ] && [ -f data/invest.db ]; then
  ok "data/invest.db 存在"
  if command -v sqlite3 >/dev/null 2>&1; then
    TXN="$(sqlite3 data/invest.db 'SELECT COUNT(*) FROM transactions;' 2>/dev/null || echo '?')"
    HOLD="$(sqlite3 data/invest.db 'SELECT COUNT(*) FROM holdings WHERE quantity>0;' 2>/dev/null || echo '?')"
    ok "持仓 ${HOLD} 只 / 交易 ${TXN} 笔（粗检）"
  fi
else
  bad "缺少 data/invest.db — 切勿用空库覆盖生产数据"
fi
if [ -d backups ]; then
  ok "backups/ 目录存在"
else
  warn "backups/ 不存在（建议先建并做一次备份）"
fi

echo
echo "== 3. Compose 服务 =="
if command -v docker >/dev/null 2>&1; then
  if docker compose -f "$COMPOSE_FILE" ps >/tmp/invest-tracker-ps.$$ 2>/dev/null; then
    cat /tmp/invest-tracker-ps.$$
    for svc in backend frontend oauth2-proxy caddy; do
      if docker compose -f "$COMPOSE_FILE" ps --status running --services 2>/dev/null | grep -qx "$svc"; then
        ok "${svc} 运行中"
      else
        # oauth2-proxy 崩溃时域名登录会挂，本机 8080 仍可能 healthy
        if [ "$svc" = "oauth2-proxy" ] || [ "$svc" = "caddy" ]; then
          bad "${svc} 未运行（看 logs: docker compose -f $COMPOSE_FILE logs --tail=50 $svc）"
        else
          bad "${svc} 未运行"
        fi
      fi
    done
  else
    bad "docker compose ps 失败（是否在 VPS 且 Compose 文件正确？）"
  fi
  rm -f /tmp/invest-tracker-ps.$$
else
  warn "本机无 docker，跳过容器检查"
fi

echo
echo "== 3b. OAuth cookie secret 长度 =="
if [ -n "${OAUTH2_PROXY_COOKIE_SECRET:-}" ]; then
  SECRET_LEN_MSG="$(python3 - <<'PY'
import base64, os
s = os.environ.get("OAUTH2_PROXY_COOKIE_SECRET", "").strip().strip('"').strip("'")
try:
    raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    n = len(raw)
except Exception as e:
    print(f"decode_error: {e}")
    raise SystemExit(0)
print(n)
PY
)" || SECRET_LEN_MSG="error"
  case "$SECRET_LEN_MSG" in
    16|24|32) ok "OAUTH2_PROXY_COOKIE_SECRET 解码后 ${SECRET_LEN_MSG} 字节" ;;
    *)
      bad "OAUTH2_PROXY_COOKIE_SECRET 非法（解码后应为 16/24/32 字节，当前: ${SECRET_LEN_MSG}）"
      warn "修复: python3 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())' 写入 .env 后 up -d oauth2-proxy"
      ;;
  esac
else
  warn "未从 .env 读到 OAUTH2_PROXY_COOKIE_SECRET（若 compose 用 env_file 仍可能生效）"
fi

echo
echo "== 4. 健康检查 / API =="
if curl -fsS --max-time 8 "${BASE}/api/health" >/tmp/invest-health.$$ 2>/dev/null; then
  ok "GET ${BASE}/api/health -> $(cat /tmp/invest-health.$$)"
else
  bad "健康检查失败：${BASE}/api/health"
fi
rm -f /tmp/invest-health.$$

AUTH_JSON="$(curl -fsS --max-time 8 "${BASE}/api/auth/status" 2>/dev/null || true)"
if [ -n "$AUTH_JSON" ]; then
  ok "auth/status: ${AUTH_JSON}"
else
  warn "无法读取 /api/auth/status"
fi

echo
echo "== 5. 部署后功能核对（人工） =="
cat <<EOF
  请在浏览器强刷（Ctrl/Cmd+Shift+R）后逐项确认：

  [ ] 登录页中文正常、无乱码/马赛克遮挡密码框
  [ ] 首页「持仓浮盈」与「全周期盈亏」两个卡片都有数字
  [ ] 持仓明细列：持仓浮盈 / 全周期盈亏 显示金额（非百分比串位）
  [ ] 点「同步最新价」后 updated_at 更新；或看 cron 日志
  [ ] 收益分析：导读三步 + 贡献表有「全周期盈亏」列
  [ ] 半自动分红：扫描 513530 / 508056 / 个股草稿可出
  [ ] 数据维护：可创建备份；data/ backups/ 未被删

  代码侧近期关键 commit（应至少包含）：
    - 半自动分红 ETF/REIT
    - 收益分析讲解向
    - 持仓浮盈 helper 暴露
    - 首页/贡献表全周期 + 定时同步价（本批）

  更新命令：
    cd /home/kofwj/invest-tracker
    python3 scripts/backup_db.py --label before_deploy || true
    ./scripts/deploy_vps.sh
    ./scripts/verify_vps_deploy.sh
EOF

echo
echo "== 6. Cron 建议 =="
if [ -x scripts/cron_sync_prices.sh ]; then
  ok "scripts/cron_sync_prices.sh 可执行"
else
  warn "请 chmod +x scripts/cron_sync_prices.sh"
fi
cat <<'EOF'
  # 备份
  15 2 * * * curl -fsS -X POST http://127.0.0.1:8080/api/maintenance/backups >/dev/null
  # 或：cd /home/kofwj/invest-tracker && python3 scripts/backup_db.py --label daily

  # 交易日收盘后同步价 + 晚盘再同步并写快照
  20 15 * * 1-5 /home/kofwj/invest-tracker/scripts/cron_sync_prices.sh >> /home/kofwj/invest-tracker/backups/cron_sync_prices.log 2>&1
  40 16 * * 1-5 /home/kofwj/invest-tracker/scripts/cron_sync_prices.sh --snapshot --check-alerts >> /home/kofwj/invest-tracker/backups/cron_sync_prices.log 2>&1
EOF

echo
echo "==== 汇总: OK=${PASS} WARN=${WARN} FAIL=${FAIL} ===="
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
