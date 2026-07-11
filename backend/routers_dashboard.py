import sqlite3

from fastapi import APIRouter

try:
    from .database import db_session
    from .dashboard import build_dashboard
except ImportError:
    from database import db_session
    from dashboard import build_dashboard

router = APIRouter()


@router.get("/dashboard")
def get_dashboard():
    with db_session(row_factory=sqlite3.Row) as conn:
        data = build_dashboard(conn)
        # ensure_cash_base may write settings on first run
        conn.commit()
    return data
