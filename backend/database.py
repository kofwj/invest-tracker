import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class AppConfig:
    db_path: str
    local_timezone: ZoneInfo
    backup_dir: str


def load_config() -> AppConfig:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(base_dir) if os.path.basename(base_dir) == "backend" else base_dir
    db_path = os.environ.get("DB_PATH", os.path.join(project_dir, "data", "invest.db"))
    timezone_name = os.environ.get("APP_TIMEZONE", "Asia/Shanghai")

    if os.environ.get("BACKUP_DIR"):
        backup_dir = os.environ["BACKUP_DIR"]
    else:
        data_parent = os.path.dirname(db_path)
        project_guess = (
            os.path.dirname(data_parent)
            if os.path.basename(data_parent) == "data"
            else project_dir
        )
        backup_dir = os.path.join(project_guess, "backups")

    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)
    return AppConfig(
        db_path=db_path,
        local_timezone=ZoneInfo(timezone_name),
        backup_dir=backup_dir,
    )


APP_CONFIG = load_config()
DB_PATH = APP_CONFIG.db_path
LOCAL_TZ = APP_CONFIG.local_timezone
BACKUP_DIR = APP_CONFIG.backup_dir


def local_today_iso() -> str:
    return datetime.now(LOCAL_TZ).date().isoformat()


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
        try:
            conn.execute("SELECT value FROM settings WHERE key = 'schema_version'")
        except sqlite3.OperationalError:
            return "degraded"
    return "ok"
