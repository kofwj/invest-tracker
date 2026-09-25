#!/usr/bin/env bash
set -euo pipefail

# 检查失败时至少告诉人家是哪一行挂的：原先 set -e 直接退出，零提示。
trap 'status=$?; echo "" >&2; echo "!! 检查失败：scripts/check.sh 第 $LINENO 行（exit $status）" >&2' ERR

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

backend_container="${BACKEND_CONTAINER:-backend}"
backend_url="${BACKEND_URL:-http://localhost:8000}"
frontend_url="${FRONTEND_URL:-http://localhost:8080}"
python_bin="${PYTHON_BIN:-python3}"

echo "==> Checking health endpoint wiring"
grep -q 'api/health' backend/main.py
grep -q 'api/health' docker-compose.yml

echo "==> Checking Vite frontend structure"
test -f frontend/index.html
test -f frontend/package.json
test -f frontend/package-lock.json
test -f frontend/Dockerfile
test -f frontend/nginx.conf
test -f frontend/src/main.js
test -f frontend/src/App.vue
test -f frontend/src/styles/styles.css
test -f frontend/src/utils/index.js
test -f frontend/src/api/index.js
test -f frontend/src/charts/index.js
test -f frontend/src/modules/transactions.js
test -f frontend/src/modules/deposits.js
test -f frontend/src/modules/cash.js
test -f frontend/src/modules/snapshots.js
test -f frontend/src/modules/performance.js
test -f frontend/src/composables/authMask.js
test -f frontend/src/composables/domainHelpers.js
test -f frontend/src/composables/feeHelpers.js
test -f frontend/src/composables/maintenanceHelpers.js
test -f frontend/src/composables/importExportHelpers.js
test -f frontend/src/composables/useAppCtx.js
test -f frontend/src/modules/tabNav.js
test -f frontend/src/components/AppHeader.vue
test -f frontend/src/components/HomeDashboard.vue
test -f frontend/src/components/AppDialogs.vue
test -f frontend/src/components/LoginOverlay.vue
# 分析组收敛后「资产快照」并入「收益与快照」：这里断言"已并入"，而不是"文件还在"
grep -q '快照明细' frontend/src/views/PerformanceTab.vue
test -f frontend/src/views/AllocationTab.vue
test -f frontend/src/views/PerformanceTab.vue
test -f frontend/src/views/DecisionTab.vue
test -f frontend/src/views/HoldingsTab.vue
test -f frontend/src/views/DepositsTab.vue
test -f frontend/src/views/TransactionsTab.vue
test -f frontend/src/views/CashTab.vue
test -f frontend/src/views/NotifyOpsTab.vue
test -f frontend/src/views/AiOpsTab.vue
test -f frontend/src/views/BackupOpsTab.vue
test -f frontend/src/modules/market.js
test -f backend/market.py
test -f backend/routers_market.py
test -f backend/trading_calendar.py
test -f backend/discipline.py
test -f backend/routers_discipline.py
test -f backend/notify.py
test -f backend/routers_notify.py
test -f backend/routers_cron.py
test -f frontend/src/modules/discipline.js
test -f frontend/src/views/BrokerReconcileTab.vue
grep -q 'type="module" src="/src/main.js"' frontend/index.html
grep -q '@vitejs/plugin-vue' frontend/package.json
grep -q 'unplugin-vue-components' frontend/package.json
grep -q 'vite build' frontend/package.json
grep -q 'npm run build' frontend/Dockerfile
grep -q 'COPY --from=build /app/dist' frontend/Dockerfile
"$python_bin" - <<'PY'
from pathlib import Path
html = Path('frontend/index.html').read_text(encoding='utf-8')
assert '/src/main.js' in html, 'missing Vite frontend entry'
assert '/assets/app.js' not in html, 'legacy app.js script should not be referenced'
assert 'id="app"' in html, 'missing #app mount point'
assert '<el-tabs' not in html, 'legacy inlined tabs should live in App.vue, not index.html'
main = Path('frontend/src/main.js').read_text(encoding='utf-8')
assert "from 'vue'" in main or 'from "vue"' in main, 'should use runtime Vue (not vue.esm-bundler)'
assert 'vue.esm-bundler' not in main, 'full compiler build should not be used after SFC migration'
assert "import App from './App.vue'" in main, 'missing App.vue import'
assert 'extends: App' in main, 'root component should extend App.vue template'
assert "element-plus/dist/index.css" not in main, 'full Element Plus CSS should not be imported after on-demand'
for module in ['./utils/index.js', './api/index.js', './modules/transactions.js', './modules/deposits.js', './modules/cash.js', './modules/snapshots.js', './modules/performance.js', './modules/market.js', './modules/allocation.js', './modules/dataSync.js', './modules/appInit.js', './modules/brief.js', './modules/holdingCorrections.js', './modules/tabNav.js', './composables/authMask.js', './composables/domainHelpers.js']:
    assert module in main, f'missing frontend module import: {module}'
assert 'createFeeHelpers' in main or 'feeHelpers' in main or "from './composables/domainHelpers.js'" in main
# modules import computed themselves; main should not pass computed into factories
# 路由化之后 tab 由 vue-router 驱动（旧断言 "computed," not in main 与之矛盾：main 本来就
# import computed，它一直是假断言）。改为断言真正的结构约束。
assert 'createRouter' in Path('frontend/src/router/index.js').read_text(encoding='utf-8'), 'missing vue-router setup'
assert 'router-view' in Path('frontend/src/App.vue').read_text(encoding='utf-8'), 'App.vue should render the router outlet'
fee = Path('frontend/src/composables/feeHelpers.js').read_text(encoding='utf-8')
assert 'createFeeHelpers' in fee
assert 'apiErrorDetail' in Path('frontend/src/utils/index.js').read_text(encoding='utf-8')
assert '已到期' in Path('frontend/src/modules/deposits.js').read_text(encoding='utf-8')
deposits_mod = Path('frontend/src/modules/deposits.js').read_text(encoding='utf-8')
assert "import { computed } from 'vue'" in deposits_mod
# charts import may now live in allocation module after extraction
allocation = Path('frontend/src/modules/allocation.js').read_text(encoding='utf-8')
assert ('./charts/index.js' in main or '../charts/index.js' in allocation or './charts/index.js' in allocation), 'missing charts dynamic/static import reference'
tab_nav = Path('frontend/src/modules/tabNav.js').read_text(encoding='utf-8')
assert "'market'" in tab_nav or '"market"' in tab_nav, 'SCREENSHOT_TABS should still include market (legacy ?tab= compatibility)'
app_vue = Path('frontend/src/App.vue').read_text(encoding='utf-8')
for needle in ['router-view', 'AppHeader', 'AppDialogs', 'LoginOverlay']:
    assert needle in app_vue, f'missing shell fragment in App.vue: {needle}'
# 子导航行在批次 1 里并进了 PageShell（页头一行式：左 tab、右 actions），
# App.vue 不应再自己渲染一条 tab 条。
assert 'page-nav' not in app_vue, 'tab nav should live in PageShell now'
assert 'page-tabs' in Path('frontend/src/components/PageShell.vue').read_text(encoding='utf-8'), \
    'PageShell should render the tab row'
assert 'provide' in main or 'APP_CTX_KEY' in main, 'root should provide app context'
holdings = Path('frontend/src/views/HoldingsTab.vue').read_text(encoding='utf-8')
assert 'holdingLifetimeProfit' in holdings, 'holdings tab missing lifetime helper'
assert 'useAppCtx' in holdings, 'views should inject app ctx'
decision_tab = Path('frontend/src/views/DecisionTab.vue').read_text(encoding='utf-8')
assert 'useAppCtx' in decision_tab, 'decision tab should inject app ctx'
market_mod = Path('frontend/src/modules/market.js').read_text(encoding='utf-8')
assert 'checkAlerts' in decision_tab or 'checkAlerts' in market_mod, 'decision/market should expose checkAlerts'
assert 'exportAlertEvents' in decision_tab or 'exportAlertEvents' in market_mod, 'market should support alert export'
backend_main = Path('backend/main.py').read_text(encoding='utf-8')
assert 'market_router' in backend_main, 'backend should register market router'
schema = Path('backend/schema.py').read_text(encoding='utf-8')
assert 'migrate_to_v5_market_alerts' in schema, 'schema missing v5 market alerts migration'
assert 'migrate_to_v6_snapshot_lifetime_and_watchlist' in schema, 'schema missing v6 snapshot lifetime migration'
assert 'migrate_to_v18_ai_and_reason_cache' in schema, 'schema missing v18 AI/reason cache migration'
assert 'migrate_to_v19_ai_call_log_warnings' in schema, 'schema missing v19 AI audit warnings column'
import re as _re
_brief_src = Path('backend/ai_brief.py').read_text(encoding='utf-8')
_api_src = Path('frontend/src/api/index.js').read_text(encoding='utf-8')
_brief_t = _re.search(r'BRIEF_TIMEOUT_S = (\d+)', _brief_src)
_push_t = _re.search(r"evening-brief/notify', null, \{ timeout: (\d+) \}", _api_src)
assert _brief_t and _push_t, 'brief 预算 / 前端推送超时未找到（换了写法就同步改这条断言）'
assert int(_push_t.group(1)) > int(_brief_t.group(1)), '前端推送超时必须大于 AI brief 预算，否则界面先超时'
assert 'lifetime_profit' in Path('backend/snapshots.py').read_text(encoding='utf-8'), 'snapshots should store lifetime_profit'
assert 'is_a_share_trading_day' in Path('backend/trading_calendar.py').read_text(encoding='utf-8'), 'trading calendar missing'
PY

echo "==> Linting backend/tests with ruff"
# 规则集见 ruff.toml：只开 F（未使用导入/未定义名）+ E9（语法错误）。
# 默认规则集里的 UP（如 Union → X | Y）会破坏 Python 3.9 兼容，不要全量开启。
if command -v ruff >/dev/null 2>&1; then
  ruff check backend tests
elif "$python_bin" -m ruff --version >/dev/null 2>&1; then
  "$python_bin" -m ruff check backend tests
else
  echo "ruff not found; skipping lint (pip install ruff to enable)"
fi

echo "==> Checking frontend build"
if command -v npm >/dev/null 2>&1; then
  npm --prefix frontend run build
else
  echo "npm not found; skipping frontend build check"
fi

echo "==> Running frontend unit tests (vitest)"
if command -v npm >/dev/null 2>&1; then
  # jsdom 30 → undici 8 要求 node >=22.19。旧 Node 上 vitest 会在启动阶段全挂
  # （TypeError: webidl.util.markAsUncloneable），表现为「0 用例 + N errors」这种假红。
  # CI 与 frontend/Dockerfile 已固定 Node 22；这里对本地/VPS 的旧 Node 明确跳过并说清原因。
  if node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a===22&&b>=19)?0:1)' 2>/dev/null; then
    npm --prefix frontend test
  else
    echo "    ⚠ node $(node -v 2>/dev/null || echo '?') 不满足 >=22.19，跳过前端单测（jsdom 30 依赖 undici 8）" >&2
    echo "      CI 与 frontend/Dockerfile 已是 Node 22；本机升级 node 后再跑这一步。" >&2
  fi
else
  echo "npm not found; skipping frontend unit tests"
fi

echo "==> Auditing frontend dependencies"
if command -v npm >/dev/null 2>&1; then
  npm --prefix frontend audit --omit=dev
else
  echo "npm not found; skipping npm audit"
fi

echo "==> Checking frontend JavaScript syntax"
if command -v node >/dev/null 2>&1; then
  node --check frontend/src/main.js
  node --check frontend/src/utils/index.js
  node --check frontend/src/api/index.js
  node --check frontend/src/charts/index.js
  node --check frontend/src/modules/transactions.js
  node --check frontend/src/modules/deposits.js
  node --check frontend/src/modules/cash.js
  node --check frontend/src/modules/snapshots.js
  node --check frontend/src/modules/performance.js
  node --check frontend/src/modules/allocation.js
  node --check frontend/src/modules/dataSync.js
  node --check frontend/src/modules/appInit.js
  node --check frontend/src/modules/brief.js
  node --check frontend/src/modules/holdingCorrections.js
  node --check frontend/src/composables/authMask.js
  node --check frontend/src/composables/domainHelpers.js
else
  echo "node not found; skipping frontend JavaScript syntax check"
fi

echo "==> Checking split backend modules"
required_backend_files=(
  backend/main.py
  backend/database.py
  backend/csv_utils.py
  backend/holdings.py
  backend/holding_calculator.py
  backend/price_sync.py
  backend/return_sync.py
  backend/cash.py
  backend/dashboard.py
  backend/snapshots.py
  backend/performance.py
  backend/routers_deposits.py
  backend/routers_transactions.py
  backend/routers_cash.py
  backend/routers_fee_settings.py
  backend/routers_securities_cash.py
  backend/routers_cash_flows.py
  backend/routers_snapshots.py
  backend/routers_holdings.py
  backend/routers_dashboard.py
  backend/routers_performance.py
  backend/schema.py
  backend/ai_client.py
  backend/routers_ai.py
  backend/ai_payload.py
  backend/reason_sources.py
  backend/reason_cache.py
  backend/ai_brief.py
  backend/routers_cron.py
)
for file in "${required_backend_files[@]}"; do
  test -f "$file"
done

echo "==> Checking backend importability"
PYTHONPATH=backend "$python_bin" - <<'PY'
import importlib.util
import sys
from pathlib import Path

path = Path("backend/main.py").resolve()
spec = importlib.util.spec_from_file_location("backend_main_check", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

required_routes = {
    "/api/health",
    "/transactions",
    "/deposits",
    "/dashboard",
    "/holdings",
    "/holding-corrections",
    "/sync-prices",
    "/dividends/scan",
    "/cron/sync-prices",
    "/cron/snapshot",
    "/cron/check-alerts",
    "/cron/notify-events",
    "/cron/trading-day",
    "/cron/refresh-reasons",
    "/ai/status",
    "/ai/config",
    "/ai/test",
    "/ai/models",
}
routes = {getattr(route, "path", "") for route in module.app.routes}
missing = sorted(required_routes - routes)
if missing:
    raise SystemExit(f"Missing required routes: {missing}")
PY

# 下面这几段依赖 docker / 正在跑的服务；本地没起 docker 时应该明确跳过，
# 而不是让整个 check 脚本挂在中间（以前就是这个下场）。
if docker info >/dev/null 2>&1; then
  echo "==> Validating docker compose config"
  docker compose config >/dev/null

  echo "==> Checking running services"
  docker compose ps

  echo "==> Running backend pytest suite"
  # 注意：容器内必须让 backend 目录在 sys.path 上，否则 tests/ 里那几个
  # 裸导入（import dividend_sync / market ...）会 collection error。
  docker compose exec -T -e PYTHONPATH=/app "$backend_container" pytest -q /app/tests

  echo "==> Checking backend health endpoint"
  curl --fail --silent --show-error "$backend_url/api/health" >/dev/null

  echo "==> Checking frontend HTTP endpoint"
  curl --fail --silent --show-error --head "$frontend_url/" >/dev/null
else
  echo "==> docker 不可用，跳过 compose 校验 / 容器内 pytest / 健康检查"
  echo "    （本地可以先跑：PYTHONPATH=backend python3 -m pytest -q tests）"
fi

echo "==> All checks passed"
