"""本地运行时的数据目录解析 + 首次启动迁移。

优先级（从高到低）：

1. ``DB_PATH`` / ``BACKUP_DIR`` 环境变量 —— Docker、VPS、测试都走这条，行为与 1.5.x 完全一致，
   不解析平台目录、不动仓库里的任何文件。
2. ``INVEST_TRACKER_HOME`` —— 自己指定根目录（便携安装、一个目录放一套账）。
3. 平台标准目录：

   =========  ==============================================================
   macOS      ``~/Library/Application Support/InvestTracker``
   Windows    ``%APPDATA%\\InvestTracker``
   Linux      ``${XDG_DATA_HOME:-~/.local/share}/InvestTracker``
   =========  ==============================================================

首次启动迁移：只有「没设 DB_PATH」且「标准目录里还没有库」时，才把源码仓库里的
``<project>/data/invest.db`` 搬过去。搬完把旧文件改名成 ``invest.db.migrated-<时间戳>``，
一个字节都不删——迁错了还能改回来。已有旧库的老用户因此无感，新用户从空库开始。
"""
from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping, Optional, Union

APP_DIR_NAME = "InvestTracker"
DB_FILENAME = "invest.db"
MIGRATED_SUFFIX = ".migrated-"


@dataclass(frozen=True)
class DataPaths:
    """本地模式最终使用的两条路径。"""

    db_path: str
    backup_dir: str


def platform_data_root(
    env: Optional[Mapping[str, str]] = None,
    *,
    sys_platform: Optional[str] = None,
    os_name: Optional[str] = None,
) -> Path:
    """返回数据根目录（不含 data/backups 这两层）。"""
    env = os.environ if env is None else env
    home_override = (env.get("INVEST_TRACKER_HOME") or "").strip()
    if home_override:
        return Path(home_override).expanduser()

    sys_platform = sys.platform if sys_platform is None else sys_platform
    os_name = os.name if os_name is None else os_name
    home = Path(env.get("HOME") or Path.home())

    if sys_platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR_NAME
    if os_name == "nt" or sys_platform.startswith("win"):
        appdata = (env.get("APPDATA") or env.get("LOCALAPPDATA") or "").strip()
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / APP_DIR_NAME
    xdg = (env.get("XDG_DATA_HOME") or "").strip()
    base = Path(xdg).expanduser() if xdg else home / ".local" / "share"
    return base / APP_DIR_NAME


def _guess_backup_dir(db_path: str, project_dir: Optional[str]) -> str:
    """复刻 database.py 原来的 backup 推导规则，保持 DB_PATH 场景行为不变。

    ``<x>/data/invest.db`` → ``<x>/backups``；其他情况用仓库根下的 ``backups/``。
    """
    db_parent = os.path.dirname(os.path.abspath(db_path))
    if os.path.basename(db_parent) == "data":
        return os.path.join(os.path.dirname(db_parent), "backups")
    if project_dir:
        return os.path.join(project_dir, "backups")
    return os.path.join(db_parent, "backups")


def _copy_sqlite(src: Path, dst: Path) -> None:
    """用 SQLite 在线备份 API 复制，WAL 里未落盘的内容也会带上。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(tmp))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    os.replace(tmp, dst)


def harden_private_file(path: Union[str, Path], *, mode: int = 0o600) -> bool:
    """把落盘文件收紧到仅属主可读写；返回是否真的改过权限。

    为什么要做：账本库和备份里存着明文凭据（`ai_api_key`、飞书 app_secret、
    钉钉加签 secret、Telegram bot token、各 webhook），而 `sqlite3.connect()`
    建出来的文件权限跟着 umask 走，默认 0644 —— 同机任何用户都能读，备份
    一旦被同步到网盘/发出去，凭据就跟着出去了。这里只收权限、不碰内容。

    Windows 上 `chmod` 只影响只读位，失败直接吞掉：那是权限模型差异，
    不该让备份/建库流程挂掉。
    """
    try:
        os.chmod(str(path), mode)
        return True
    except OSError:
        return False


def _park_legacy(legacy: Path, stamp: Optional[str] = None) -> None:
    """把旧库改名留档（含 -wal / -shm），不删除。"""
    stamp = stamp or datetime.now().strftime("%Y%m%d%H%M%S")
    for suffix in ("", "-wal", "-shm"):
        side = Path(str(legacy) + suffix)
        if not side.exists():
            continue
        target = Path(str(legacy) + MIGRATED_SUFFIX + stamp + suffix)
        try:
            side.rename(target)
        except OSError:
            # 改名失败不影响已经复制好的新库，旧文件原样留在这儿
            continue


def migrate_legacy_into(legacy: Path, target: Path, *, stamp: Optional[str] = None) -> bool:
    """把 legacy 库复制到 target 并把旧文件改名。成功返回 True。"""
    if not legacy.is_file() or target.exists():
        return False
    try:
        _copy_sqlite(legacy, target)
    except (sqlite3.Error, OSError):
        return False
    _park_legacy(legacy, stamp)
    return True


def resolve_data_paths(
    project_dir: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> DataPaths:
    """按上面的优先级算出 db_path / backup_dir。纯函数：不建目录、不碰文件。"""
    env = os.environ if env is None else env

    db_env = (env.get("DB_PATH") or "").strip()
    backup_env = (env.get("BACKUP_DIR") or "").strip()
    if db_env:
        db_path = str(Path(db_env).expanduser())
        return DataPaths(
            db_path=db_path,
            backup_dir=backup_env or _guess_backup_dir(db_path, project_dir),
        )

    root = platform_data_root(env)
    return DataPaths(
        db_path=str(root / "data" / DB_FILENAME),
        backup_dir=backup_env or str(root / "backups"),
    )


def migrate_on_first_run(
    project_dir: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    *,
    stamp: Optional[str] = None,
) -> Optional[str]:
    """首次启动把仓库里的旧库搬到平台目录，返回旧库路径（没搬返回 None）。

    只在「没设 DB_PATH」「目标库还不存在」时动手，并且只复制 + 改名、不删文件。
    由启动入口显式调用，不在 import 路径上——跑测试不该搬用户的数据。
    """
    env = os.environ if env is None else env
    if (env.get("DB_PATH") or "").strip() or not project_dir:
        return None
    target = Path(resolve_data_paths(project_dir, env).db_path)
    if target.exists():
        return None
    legacy = Path(project_dir) / "data" / DB_FILENAME
    return str(legacy) if migrate_legacy_into(legacy, target, stamp=stamp) else None


def ensure_directories(paths: DataPaths) -> None:
    """建好 data/ 与 backups/，两侧都可能不存在（首次启动）。"""
    for directory in (os.path.dirname(paths.db_path), paths.backup_dir):
        if directory:
            os.makedirs(directory, exist_ok=True)


def describe(paths: DataPaths) -> str:
    """给启动日志用的一行摘要。"""
    return "数据库：%s；备份：%s" % (paths.db_path, paths.backup_dir)


def find_frontend_dist(project_dir: Optional[str] = None, env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """找出前端构建产物目录，找不到返回 None（纯 API 模式）。

    ``FRONTEND_DIST`` 显式指定；否则试用仓库里的 ``frontend/dist``，
    以及打包后与之并列的 ``web`` / ``dist`` 目录。
    """
    env = os.environ if env is None else env
    explicit = (env.get("FRONTEND_DIST") or "").strip()
    if explicit:
        return explicit if os.path.isdir(explicit) else None

    candidates = []
    if project_dir:
        candidates.append(os.path.join(project_dir, "frontend", "dist"))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.extend(
        [
            os.path.join(here, "web"),
            os.path.join(here, "dist"),
            os.path.join(os.path.dirname(here), "web"),
        ]
    )
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, "index.html")):
            return candidate
    return None


__all__ = [
    "APP_DIR_NAME",
    "DataPaths",
    "describe",
    "ensure_directories",
    "find_frontend_dist",
    "migrate_legacy_into",
    "migrate_on_first_run",
    "platform_data_root",
    "resolve_data_paths",
]


# 供调试用：python backend/app_paths.py 直接看到本机解析结果
if __name__ == "__main__":
    _project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(describe(resolve_data_paths(_project)))
    print("前端产物：", find_frontend_dist(_project) or "未找到")
