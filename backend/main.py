import logging
import os
import sys
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

try:
    from .cash import set_setting
    from .database import (
        APP_CONFIG,
        DB_PATH,
        LOCAL_TZ,
        check_database_health as _check_database_health,
        fetch_all_as_dicts,
        get_db_connection,
    )
    from .routers_cash import router as cash_router
    from .routers_dashboard import router as dashboard_router
    from .routers_deposits import router as deposits_router
    from .routers_holdings import router as holdings_router
    from .routers_performance import router as performance_router
    from .routers_snapshots import router as snapshots_router
    from .routers_transactions import router as transactions_router
    from .schema import ensure_app_schema, ensure_core_tables, initialize_database, run_startup_migrations
except ImportError:  # Allows tests to load this file directly via importlib.
    from cash import set_setting
    from database import (
        APP_CONFIG,
        DB_PATH,
        LOCAL_TZ,
        check_database_health as _check_database_health,
        fetch_all_as_dicts,
        get_db_connection,
    )
    from routers_cash import router as cash_router
    from routers_dashboard import router as dashboard_router
    from routers_deposits import router as deposits_router
    from routers_holdings import router as holdings_router
    from routers_performance import router as performance_router
    from routers_snapshots import router as snapshots_router
    from routers_transactions import router as transactions_router
    from schema import ensure_app_schema, ensure_core_tables, initialize_database, run_startup_migrations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Investment Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(deposits_router)
app.include_router(transactions_router)
app.include_router(cash_router)
app.include_router(snapshots_router)
app.include_router(holdings_router)
app.include_router(dashboard_router)
app.include_router(performance_router)


def local_today_iso():
    return datetime.now(LOCAL_TZ).date().isoformat()


def check_database_health():
    return _check_database_health(DB_PATH)


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "database": check_database_health(),
        "timezone": str(APP_CONFIG.local_timezone),
        "db_path": DB_PATH,
    }


@app.on_event("startup")
def startup():
    run_startup_migrations()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
