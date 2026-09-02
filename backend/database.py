import os
import socket
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

# akshare 多数 fetcher 内部 requests 不带 timeout，几个挂住的 socket 就能拖垮 uvicorn
# 线程池（FastAPI 默认 40 线程）。设全局 socket 默认超时兜底——应用与 cron docker exec
# 都导入本模块，等价于给所有未显式设 timeout 的网络调用加护栏。
socket.setdefaulttimeout(float(os.environ.get("NET_TIMEOUT_SECONDS", "20")))


def local_today_iso() -> str:
    return datetime.now(LOCAL_TZ).date().isoformat()


def configure_sqlite_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Apply pragmatic defaults for a multi-request personal SQLite app."""
    # WAL improves concurrent read during writes (sync prices / UI).
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    # NORMAL is a good durability/speed tradeoff for local personal data.
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def open_db(*, row_factory=None):
    conn = sqlite3.connect(DB_PATH)
    configure_sqlite_connection(conn)
    if row_factory is None:
        row_factory = sqlite3.Row
    conn.row_factory = row_factory
    return conn


@contextmanager
def db_session(*, row_factory=None):
    """Connection context that always closes and rolls back on error."""
    conn = open_db(row_factory=row_factory)
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def get_db_connection(db_path: str, *, row_factory=None):
    conn = sqlite3.connect(db_path)
    configure_sqlite_connection(conn)
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
