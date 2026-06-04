import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class AppConfig:
    db_path: str
    local_timezone: ZoneInfo


def load_config() -> AppConfig:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(base_dir) if os.path.basename(base_dir) == "backend" else base_dir
    db_path = os.environ.get("DB_PATH", os.path.join(project_dir, "data", "invest.db"))
    timezone_name = os.environ.get("APP_TIMEZONE", "Asia/Shanghai")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return AppConfig(db_path=db_path, local_timezone=ZoneInfo(timezone_name))


APP_CONFIG = load_config()
DB_PATH = APP_CONFIG.db_path
LOCAL_TZ = APP_CONFIG.local_timezone


def open_db(*, row_factory=None):
    conn = sqlite3.connect(DB_PATH)
    if row_factory is not None:
        conn.row_factory = row_factory
    return conn


@contextmanager
def db_session(*, row_factory=None):
    conn = open_db(row_factory=row_factory)
    try:
        yield conn
    finally:
        conn.close()


def get_db_connection(db_path: str, *, row_factory=None):
    conn = sqlite3.connect(db_path)
    if row_factory is not None:
        conn.row_factory = row_factory
    return conn


def fetch_all_as_dicts(db_path: str, query: str, params=()):
    with get_db_connection(db_path, row_factory=sqlite3.Row) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def check_database_health(db_path: str) -> str:
    with get_db_connection(db_path) as conn:
        conn.execute("SELECT 1")
    return "ok"
