import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)
PROJECT_DIR = os.path.dirname(CURRENT_DIR) if os.path.basename(CURRENT_DIR) == "backend" else CURRENT_DIR


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
    from .routers_ai import router as ai_router
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
    from routers_ai import router as ai_router
    from routers_snapshots import router as snapshots_router
    from routers_transactions import router as transactions_router
    from schema import initialize_database, run_startup_migrations  # noqa: F401  (initialize_database is loaded by tests as module attr)

try:
    from .app_paths import find_frontend_dist, migrate_on_first_run
except ImportError:
    from app_paths import find_frontend_dist, migrate_on_first_run

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup_migrations()
    yield


app = FastAPI(title="Investment Tracker API", lifespan=lifespan)

# ---- 运行形态判定（必须早于 include_router）----
# 找到前端产物 = 本地单进程：本进程同时提供 API 和页面，接口统一挂 /api 前缀，
# 把 /holdings /transactions /deposits 这些同名的前端 history 路由让给 SPA 兜底。
# 找不到 dist = Docker/VPS（nginx 剥前缀）或 pytest，接口仍注册在根路径，与改造前一致。
_FRONTEND_DIST = find_frontend_dist(PROJECT_DIR)
SERVE_FRONTEND = _FRONTEND_DIST is not None
API_PREFIX = "/api" if SERVE_FRONTEND else ""

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


# 单进程本地模式下前后端同源，但前端请求一律带 /api 前缀（以前由 nginx 的
# ``proxy_pass`` 去掉）。这里在 ASGI 层剥一次：Docker/VPS 走后端时请求已被
# nginx 剥过，不会命中这个分支，线上行为不变。
class StripApiPrefixMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            scope = dict(scope)
            scope["path"] = scope["path"][4:]
            scope["raw_path"] = scope["path"].encode("utf-8")
            # 标记一下：剥过前缀说明这是接口请求，SPA 回落时不能拿 index.html 顶包
            scope["invest_api_request"] = True
        await self.app(scope, receive, send)


if not SERVE_FRONTEND:
    # 本地模式接口本来就注册在 /api 下，不需要再剥前缀；只有生产拓扑（nginx 已剥过、
    # 但直连后端的调用仍带 /api）才挂。
    app.add_middleware(StripApiPrefixMiddleware)

# 本地单进程模式下接口统一挂在 /api 下，把 /holdings 这类前端 history 路由留给
# SPA 兜底；Docker/VPS 下 API_PREFIX 为空，注册位置与改造前逐字一致。
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(deposits_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(transactions_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(cash_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(snapshots_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(holdings_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(klines_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(fundamentals_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(dividends_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(dashboard_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(performance_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(maintenance_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(market_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(discipline_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(allocation_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(broker_reconcile_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(notify_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(ai_router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])
app.include_router(cron_router, prefix=API_PREFIX, dependencies=[Depends(require_cron_token)])


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


# ---- 本地单进程模式：一个进程同时提供 API 和前端 ----
# Docker/VPS 里前端由 nginx 托管；找不到 dist 就退化成纯 API，线上行为不变。
# _FRONTEND_DIST / SERVE_FRONTEND 已在文件上方算好，这里只负责挂静态托管。

if _FRONTEND_DIST:
    from fastapi import Request
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    _ASSETS_DIR = os.path.join(_FRONTEND_DIST, "assets")
    if os.path.isdir(_ASSETS_DIR):
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str, request: Request):
        # 接口路径一律 404（含刚被剥掉 /api 前缀的），不要回落成首页
        if request.scope.get("invest_api_request") or full_path == "api" or full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        root = os.path.realpath(_FRONTEND_DIST)
        candidate = os.path.realpath(os.path.join(root, full_path)) if full_path else root
        if candidate.startswith(root + os.sep) and os.path.isfile(candidate):
            return FileResponse(candidate)
        # 前端 history 路由（/dashboard 之类）回落到 index.html
        return FileResponse(os.path.join(root, "index.html"))

    logger.info("已托管前端：%s", _FRONTEND_DIST)
else:
    logger.info("未找到前端产物（frontend/dist），只提供 API；可用 FRONTEND_DIST 指定目录")


def open_browser_later(url: str, delay: float = 1.2) -> None:
    """延迟开浏览器：uvicorn 起来要一点时间，太早打开会看到连接被拒。"""
    import threading
    import webbrowser

    timer = threading.Timer(delay, lambda: webbrowser.open(url))
    timer.daemon = True
    timer.start()


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))

    # 首次启动：把仓库里的旧 data/invest.db 搬到平台数据目录（只复制 + 改名，不删文件）
    migrated_from = migrate_on_first_run(PROJECT_DIR)
    if migrated_from:
        logger.info("已从原位迁移数据库：%s → %s", migrated_from, DB_PATH)

    browse_host = "127.0.0.1" if host in ("", "0.0.0.0", "::") else host
    url = "http://%s:%s" % (browse_host, port)
    if os.environ.get("INVEST_TRACKER_NO_BROWSER", "").strip() in ("", "0"):
        open_browser_later(url)
    logger.info("本机访问：%s（不开浏览器设 INVEST_TRACKER_NO_BROWSER=1）", url)
    uvicorn.run(app, host=host, port=port)
