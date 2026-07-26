import sqlite3

from fastapi import APIRouter

try:
    from .allocation_analysis import build_allocation_story
    from .database import db_session
except ImportError:
    from allocation_analysis import build_allocation_story
    from database import db_session

router = APIRouter()


@router.get("/allocation/story")
def allocation_story():
    with db_session(row_factory=sqlite3.Row) as conn:
        return build_allocation_story(conn)
