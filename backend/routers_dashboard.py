import sqlite3

from fastapi import APIRouter

try:
    from .database import open_db
    from .dashboard import build_dashboard
except ImportError:
    from database import open_db
    from dashboard import build_dashboard

router = APIRouter()


@router.get("/dashboard")
def get_dashboard():
    conn = open_db(row_factory=sqlite3.Row)
    data = build_dashboard(conn)
    conn.commit()
    conn.close()
    return data
