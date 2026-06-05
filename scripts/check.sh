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
