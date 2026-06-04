import os
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

    return AppConfig(
        db_path=db_path,
        local_timezone=ZoneInfo(timezone_name),
    )
