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
    from .auth import require_auth, require_cron_token, router as auth_router
    from .cash import set_setting  # noqa: F401  (module-level API used by tests)
    from .version import APP_VERSION
    from .database import (
        APP_CONFIG,
        DB_PATH,
        check_database_health as _check_database_health,
        fetch_all_as_dicts,  # noqa: F401  (module-level API used by tests)
        get_db_connection,   # noqa: F401  (module-level API used by tests)
        local_today_iso,     # noqa: F401  (module-level API used by tests)
    )
    from .routers_cash import router as cash_router
    from .routers_dashboard import router as dashboard_router
    from .routers_dividends import router as dividends_router
    from .routers_deposits import router as deposits_router
    from .routers_holdings import router as holdings_router
    from .routers_klines import router as klines_router
    from .routers_fundamentals import router as fundamentals_router
    from .routers_performance import router as performance_router
    from .routers_maintenance import router as maintenance_router
    from .routers_market import router as market_router
    from .routers_discipline import router as discipline_router
    from .routers_allocation import router as allocation_router
    from .routers_broker_reconcile import router as broker_reconcile_router
    from .routers_cron import router as cron_router
    from .routers_notify import router as notify_router
    from .routers_snapshots import router as snapshots_router
    from .routers_transactions import router as transactions_router
    from .schema import initialize_database, run_startup_migrations  # noqa: F401  (initialize_database is loaded by tests as module attr)
except ImportError:  # Allows tests to load this file directly via importlib.
    from auth import require_auth, require_cron_token, router as auth_router
    from cash import set_setting  # noqa: F401  (module-level API used by tests)
    from version import APP_VERSION
    from database import (
        APP_CONFIG,
        DB_PATH,
        check_database_health as _check_database_health,
        fetch_all_as_dicts,  # noqa: F401  (module-level API used by tests)
        get_db_connection,   # noqa: F401  (module-level API used by tests)
        local_today_iso,     # noqa: F401  (module-level API used by tests)
    )
    from routers_cash import router as cash_router
    from routers_dashboard import router as dashboard_router
    from routers_dividends import router as dividends_router
    from routers_deposits import router as deposits_router
    from routers_holdings import router as holdings_router
    from routers_klines import router as klines_router
    from routers_fundamentals import router as fundamentals_router
    from routers_performance import router as performance_router
    from routers_maintenance import router as maintenance_router
    from routers_market import router as market_router
    from routers_discipline import router as discipline_router
    from routers_allocation import router as allocation_router
    from routers_broker_reconcile import router as broker_reconcile_router
    from routers_cron import router as cron_router
    from routers_notify import router as notify_router
    from routers_snapshots import router as snapshots_router
    from routers_transactions import router as transactions_router
    from schema import initialize_database, run_startup_migrations  # noqa: F401  (initialize_database is loaded by tests as module attr)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup_migrations()
    yield


app = FastAPI(title="Investment Tracker API", lifespan=lifespan)

_cors_origins = (os.environ.get("CORS_ALLOW_ORIGINS") or "").strip()
_is_prod = os.environ.get("ENV", "").lower() in ("prod", "production")
if _cors_origins and _cors_origins != "*":
    _allow_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
elif _is_prod or os.environ.get("INVEST_TRACKER_PASSWORD"):
    # 生产/开启鉴权时不再悄悄 fallback 成 *：未显式配置则关同跨域（同源反代不受影响）
    _allow_origins = []
    if not _cors_origins:
        logger.warning(
            "CORS_ALLOW_ORIGINS 未设置，已默认关闭跨域；同源(反代)请求不受影响。"
            "如需跨域请显式设置，例如 https://%s",
            os.environ.get("APP_DOMAIN", "your-domain.com"),
        )
else:
    _allow_origins = ["*"]

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
app.include_router(klines_router, dependencies=[Depends(require_auth)])
app.include_router(fundamentals_router, dependencies=[Depends(require_auth)])
app.include_router(dividends_router, dependencies=[Depends(require_auth)])
app.include_router(dashboard_router, dependencies=[Depends(require_auth)])
app.include_router(performance_router, dependencies=[Depends(require_auth)])
app.include_router(maintenance_router, dependencies=[Depends(require_auth)])
app.include_router(market_router, dependencies=[Depends(require_auth)])
app.include_router(discipline_router, dependencies=[Depends(require_auth)])
app.include_router(allocation_router, dependencies=[Depends(require_auth)])
app.include_router(broker_reconcile_router, dependencies=[Depends(require_auth)])
app.include_router(notify_router, dependencies=[Depends(require_auth)])
app.include_router(cron_router, dependencies=[Depends(require_cron_token)])


def check_database_health():
    return _check_database_health(DB_PATH)


def health_payload():
    # 不暴露本机绝对路径（外网 /health 可达时避免信息泄露）
    db_status = check_database_health()
    status = "ok" if db_status == "ok" else "degraded"
    return {
        "status": status,
        "database": db_status,
        "timezone": str(APP_CONFIG.local_timezone),
        "version": APP_VERSION,
    }


@app.get("/api/health")
def health_check():
    payload = health_payload()
    if payload.get("status") != "ok":
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/health")
def proxied_health_check():
    # Nginx strips the /api prefix before proxying to the backend,
    # so /api/health on the frontend reaches /health here.
    return health_check()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
