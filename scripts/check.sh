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

echo "==> Checking split frontend assets"
test -f frontend/index.html
test -f frontend/assets/styles.css
test -f frontend/assets/app.js
test -f frontend/assets/utils.js
test -f frontend/assets/charts.js
test -f frontend/assets/api.js
test -f frontend/assets/modules/transactions.js
test -f frontend/assets/modules/deposits.js
test -f frontend/assets/modules/cash.js
grep -q 'assets/styles.css' frontend/index.html
grep -q 'assets/utils.js' frontend/index.html
grep -q 'assets/api.js' frontend/index.html
grep -q 'assets/charts.js' frontend/index.html
grep -q 'assets/modules/transactions.js' frontend/index.html
grep -q 'assets/modules/deposits.js' frontend/index.html
grep -q 'assets/modules/cash.js' frontend/index.html
grep -q 'assets/app.js' frontend/index.html
grep -q 'COPY assets' frontend/Dockerfile
"$python_bin" - <<'PY'
from pathlib import Path
html = Path('frontend/index.html').read_text(encoding='utf-8')
for asset in ['styles.css', 'utils.js', 'api.js', 'charts.js', 'modules/transactions.js', 'modules/deposits.js', 'modules/cash.js', 'app.js']:
    assert f'/assets/{asset}' in html, f'missing frontend asset reference: {asset}'
script_order = [html.index('/assets/utils.js'), html.index('/assets/api.js'), html.index('/assets/charts.js'), html.index('/assets/modules/transactions.js'), html.index('/assets/modules/deposits.js'), html.index('/assets/modules/cash.js'), html.index('/assets/app.js')]
assert script_order == sorted(script_order), 'frontend scripts must load as utils -> api -> charts -> modules -> app'
assert '<el-date-picker\n                            <el-date-picker' not in html, 'duplicate el-date-picker tag found'
PY

echo "==> Checking frontend JavaScript syntax"
if command -v node >/dev/null 2>&1; then
  node --check frontend/assets/utils.js
  node --check frontend/assets/api.js
  node --check frontend/assets/charts.js
  node --check frontend/assets/modules/transactions.js
  node --check frontend/assets/modules/deposits.js
  node --check frontend/assets/modules/cash.js
  node --check frontend/assets/app.js
else
  echo "node not found; skipping frontend JavaScript syntax check"
fi

echo "==> Checking split backend modules"
required_backend_files=(
  backend/main.py
  backend/database.py
  backend/csv_utils.py
  backend/holdings.py
  backend/cash.py
  backend/dashboard.py
  backend/snapshots.py
  backend/performance.py
  backend/routers_deposits.py
  backend/routers_transactions.py
  backend/routers_cash.py
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
