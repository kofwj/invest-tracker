import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

try:
    from .auth import require_auth, router as auth_router
    from .cash import set_setting
    from .database import (
        APP_CONFIG,
        DB_PATH,
        LOCAL_TZ,
        check_database_health as _check_database_health,
        fetch_all_as_dicts,
        get_db_connection,
        local_today_iso,
    )
    from .routers_cash import router as cash_router
    from .routers_dashboard import router as dashboard_router
    from .routers_deposits import router as deposits_router
    from .routers_holdings import router as holdings_router
    from .routers_performance import router as performance_router
    from .routers_maintenance import router as maintenance_router
    from .routers_snapshots import router as snapshots_router
    from .routers_transactions import router as transactions_router
    from .schema import ensure_app_schema, ensure_core_tables, initialize_database, run_startup_migrations
except ImportError:  # Allows tests to load this file directly via importlib.
    from auth import require_auth, router as auth_router
    from cash import set_setting
    from database import (
        APP_CONFIG,
        DB_PATH,
        LOCAL_TZ,
        check_database_health as _check_database_health,
        fetch_all_as_dicts,
        get_db_connection,
        local_today_iso,
    )
    from routers_cash import router as cash_router
    from routers_dashboard import router as dashboard_router
    from routers_deposits import router as deposits_router
    from routers_holdings import router as holdings_router
    from routers_performance import router as performance_router
    from routers_maintenance import router as maintenance_router
    from routers_snapshots import router as snapshots_router
    from routers_transactions import router as transactions_router
    from schema import ensure_app_schema, ensure_core_tables, initialize_database, run_startup_migrations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup_migrations()
    yield


app = FastAPI(title="Investment Tracker API", lifespan=lifespan)

_cors_origins = os.environ.get("CORS_ALLOW_ORIGINS", "*")
if _cors_origins.strip() == "*":
    _allow_origins = ["*"]
else:
    _allow_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(deposits_router, dependencies=[Depends(require_auth)])
app.include_router(transactions_router, dependencies=[Depends(require_auth)])
app.include_router(cash_router, dependencies=[Depends(require_auth)])
app.include_router(snapshots_router, dependencies=[Depends(require_auth)])
app.include_router(holdings_router, dependencies=[Depends(require_auth)])
app.include_router(dashboard_router, dependencies=[Depends(require_auth)])
app.include_router(performance_router, dependencies=[Depends(require_auth)])
app.include_router(maintenance_router, dependencies=[Depends(require_auth)])


def check_database_health():
    return _check_database_health(DB_PATH)


def health_payload():
    return {
        "status": "ok",
        "database": check_database_health(),
        "timezone": str(APP_CONFIG.local_timezone),
        "db_path": DB_PATH,
    }


@app.get("/api/health")
def health_check():
    return health_payload()


@app.get("/health")
def proxied_health_check():
    # Nginx strips the /api prefix before proxying to the backend,
    # so /api/health on the frontend reaches /health here.
    return health_payload()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
