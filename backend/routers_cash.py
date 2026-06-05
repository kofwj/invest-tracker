"""Compatibility router that groups cash-related subrouters."""
from fastapi import APIRouter

try:
    from .routers_cash_flows import router as cash_flows_router
    from .routers_fee_settings import router as fee_settings_router
    from .routers_securities_cash import router as securities_cash_router
except ImportError:
    from routers_cash_flows import router as cash_flows_router
    from routers_fee_settings import router as fee_settings_router
    from routers_securities_cash import router as securities_cash_router

router = APIRouter()
router.include_router(fee_settings_router)
router.include_router(securities_cash_router)
router.include_router(cash_flows_router)
