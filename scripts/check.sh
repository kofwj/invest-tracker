#!/usr/bin/env bash
set -euo pipefail

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
test -f frontend/src/styles/styles.css
test -f frontend/src/utils/index.js
test -f frontend/src/api/index.js
test -f frontend/src/charts/index.js
test -f frontend/src/modules/transactions.js
test -f frontend/src/modules/deposits.js
test -f frontend/src/modules/cash.js
test -f frontend/src/modules/snapshots.js
test -f frontend/src/modules/performance.js
grep -q 'type="module" src="/src/main.js"' frontend/index.html
grep -q 'vite build' frontend/package.json
grep -q 'npm run build' frontend/Dockerfile
grep -q 'COPY --from=build /app/dist' frontend/Dockerfile
"$python_bin" - <<'PY'
from pathlib import Path
html = Path('frontend/index.html').read_text(encoding='utf-8')
assert '/src/main.js' in html, 'missing Vite frontend entry'
assert '/assets/app.js' not in html, 'legacy app.js script should not be referenced'
assert '<el-date-picker\n                            <el-date-picker' not in html, 'duplicate el-date-picker tag found'
main = Path('frontend/src/main.js').read_text(encoding='utf-8')
for module in ['./utils/index.js', './api/index.js', './charts/index.js', './modules/transactions.js', './modules/deposits.js', './modules/cash.js', './modules/snapshots.js', './modules/performance.js']:
    assert module in main, f'missing frontend module import: {module}'
PY

echo "==> Checking frontend build"
if command -v npm >/dev/null 2>&1; then
  npm --prefix frontend run build
else
  echo "npm not found; skipping frontend build check"
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
}
routes = {getattr(route, "path", "") for route in module.app.routes}
missing = sorted(required_routes - routes)
if missing:
    raise SystemExit(f"Missing required routes: {missing}")
PY

echo "==> Validating docker compose config"
docker compose config >/dev/null

echo "==> Checking running services"
docker compose ps

echo "==> Running backend pytest suite"
docker compose exec -T "$backend_container" pytest -q /app/tests

echo "==> Checking backend health endpoint"
curl --fail --silent --show-error "$backend_url/api/health" >/dev/null

echo "==> Checking frontend HTTP endpoint"
curl --fail --silent --show-error --head "$frontend_url/" >/dev/null

echo "==> All checks passed"
