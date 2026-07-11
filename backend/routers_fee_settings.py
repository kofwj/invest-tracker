import json
import sqlite3
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

try:
    from .cash import DEFAULT_ACCOUNT, set_setting
    from .database import db_session
    from .fee_settings import DEFAULT_FEE_RULES, get_fee_settings_from_conn, normalize_fee_settings
except ImportError:
    from cash import DEFAULT_ACCOUNT, set_setting
    from database import db_session
    from fee_settings import DEFAULT_FEE_RULES, get_fee_settings_from_conn, normalize_fee_settings

router = APIRouter()


class FeeSettingsUpdate(BaseModel):
    accounts: Optional[List[str]] = None
    active_account: Optional[str] = None
    settings: dict


@router.get("/fee-settings")
def get_fee_settings():
    with db_session(row_factory=sqlite3.Row) as conn:
        return get_fee_settings_from_conn(conn)


@router.put("/fee-settings")
def update_fee_settings(data: FeeSettingsUpdate):
    with db_session() as conn:
        normalized = normalize_fee_settings({
            "accounts": data.accounts or [],
            "active_account": data.active_account,
            "settings": data.settings,
        })
        set_setting(conn, "fee_settings", json.dumps(normalized, ensure_ascii=False))
        conn.commit()
    return {"status": "success", **normalized}


@router.post("/fee-settings/reset")
def reset_fee_settings():
    with db_session() as conn:
        normalized = normalize_fee_settings({
            "accounts": [DEFAULT_ACCOUNT],
            "active_account": DEFAULT_ACCOUNT,
            "settings": {DEFAULT_ACCOUNT: DEFAULT_FEE_RULES},
        })
        set_setting(conn, "fee_settings", json.dumps(normalized, ensure_ascii=False))
        conn.commit()
    return {"status": "success", **normalized}
