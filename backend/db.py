from contextlib import contextmanager
import sqlite3
from typing import Iterator


@contextmanager
def get_db_connection(db_path: str, *, row_factory=None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    if row_factory is not None:
        conn.row_factory = row_factory
    try:
        yield conn
    finally:
        conn.close()


def connect_db(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def fetch_all_as_dicts(db_path: str, query: str, params=()):
    with get_db_connection(db_path, row_factory=sqlite3.Row) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def check_database_health(db_path: str) -> str:
    with get_db_connection(db_path) as conn:
        conn.execute("SELECT 1")
    return "ok"
