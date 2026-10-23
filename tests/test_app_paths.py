"""本地运行模式：平台数据目录、旧库迁移、单进程托管前端。

对应 ``backend/app_paths.py`` 和 ``backend/main.py`` 末尾那两段代码的契约：

- ``DB_PATH`` / ``BACKUP_DIR`` 优先，Docker、VPS、测试的行为一个字都不变；
- 没设 ``DB_PATH`` 时才落平台标准目录，且只有首次启动才搬仓库里的旧库
  （复制 + 改名留档，绝不删除）；
- 找得到前端产物时一个进程同时给 API 和页面：``/api`` 前缀照常路由，
  接口 404 不能回落成 ``index.html``，否则前端拿 HTML 当 JSON 解析。
"""
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app_paths import (
    MIGRATED_SUFFIX,
    DataPaths,
    describe,
    ensure_directories,
    find_frontend_dist,
    migrate_legacy_into,
    migrate_on_first_run,
    platform_data_root,
    resolve_data_paths,
)

def _make_db(path, rows=()):
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
        conn.executemany("INSERT INTO notes (body) VALUES (?)", rows)
        conn.commit()
    finally:
        conn.close()


def _read_notes(path):
    conn = sqlite3.connect(str(path))
    try:
        return [row[0] for row in conn.execute("SELECT body FROM notes ORDER BY id")]
    finally:
        conn.close()


# ---------------------------------------------------------------- 平台目录


def test_platform_data_root_macos():
    root = platform_data_root(
        {"HOME": "/Users/alice"}, sys_platform="darwin", os_name="posix"
    )
    assert str(root) == "/Users/alice/Library/Application Support/InvestTracker"


def test_platform_data_root_windows():
    root = platform_data_root(
        {"HOME": r"C:\Users\bob", "APPDATA": r"C:\Users\bob\AppData\Roaming"},
        sys_platform="win32",
        os_name="nt",
    )
    assert root.parts[-1] == "InvestTracker"
    assert "AppData" in str(root)


def test_platform_data_root_windows_without_appdata():
    root = platform_data_root({"HOME": r"C:\Users\bob"}, sys_platform="win32", os_name="nt")
    assert root.parts[-1] == "InvestTracker"
    assert root.parts[-3:] == ("AppData", "Roaming", "InvestTracker")


def test_platform_data_root_linux_uses_xdg():
    root = platform_data_root(
        {"HOME": "/home/carol", "XDG_DATA_HOME": "/home/carol/flat-data"},
        sys_platform="linux",
        os_name="posix",
    )
    assert str(root) == "/home/carol/flat-data/InvestTracker"


def test_platform_data_root_linux_defaults_to_local_share():
    root = platform_data_root({"HOME": "/home/carol"}, sys_platform="linux", os_name="posix")
    assert str(root) == "/home/carol/.local/share/InvestTracker"


def test_platform_data_root_honours_explicit_home():
    root = platform_data_root(
        {"HOME": "/home/carol", "INVEST_TRACKER_HOME": "/opt/ledger"},
        sys_platform="linux",
        os_name="posix",
    )
    assert str(root) == "/opt/ledger"


# ------------------------------------------------------------ 路径优先级


def test_db_path_env_wins_and_backup_is_derived(tmp_path):
    db = tmp_path / "data" / "invest.db"
    paths = resolve_data_paths(str(tmp_path), {"DB_PATH": str(db)})
    assert paths.db_path == str(db)
    assert paths.backup_dir == str(tmp_path / "backups")


def test_db_path_env_outside_data_dir_falls_back_to_project_backups(tmp_path):
    db = tmp_path / "somewhere" / "ledger.db"
    paths = resolve_data_paths("/srv/invest-tracker", {"DB_PATH": str(db)})
    assert paths.backup_dir == "/srv/invest-tracker/backups"


def test_backup_dir_env_wins(tmp_path):
    db = tmp_path / "data" / "invest.db"
    paths = resolve_data_paths(
        str(tmp_path), {"DB_PATH": str(db), "BACKUP_DIR": str(tmp_path / "baks")}
    )
    assert paths.backup_dir == str(tmp_path / "baks")


def test_default_paths_live_under_platform_root(tmp_path):
    env = {"HOME": str(tmp_path / "home"), "XDG_DATA_HOME": str(tmp_path / "xdg")}
    paths = resolve_data_paths(None, env)
    expected_root = platform_data_root(env)
    assert paths.db_path == str(expected_root / "data" / "invest.db")
    assert paths.backup_dir == str(expected_root / "backups")


def test_resolve_does_not_create_anything(tmp_path):
    env = {"HOME": str(tmp_path / "home")}
    paths = resolve_data_paths(None, env)
    assert not (tmp_path / "home").exists()
    assert not os.path.exists(paths.db_path)


def test_ensure_directories_creates_both_sides(tmp_path):
    paths = DataPaths(
        db_path=str(tmp_path / "a" / "b" / "invest.db"), backup_dir=str(tmp_path / "c")
    )
    ensure_directories(paths)
    assert (tmp_path / "a" / "b").is_dir()
    assert (tmp_path / "c").is_dir()


def test_describe_mentions_both_paths(tmp_path):
    paths = DataPaths(db_path=str(tmp_path / "invest.db"), backup_dir=str(tmp_path / "b"))
    text = describe(paths)
    assert str(tmp_path / "invest.db") in text
    assert str(tmp_path / "b") in text


# ---------------------------------------------------------------- 旧库迁移


def test_migrate_copies_rows_and_parks_legacy(tmp_path):
    legacy = tmp_path / "invest.db"
    _make_db(legacy, [("持仓",), ("流水",)])
    target = tmp_path / "new" / "invest.db"

    assert migrate_legacy_into(legacy, target, stamp="20250101120000") is True

    assert _read_notes(target) == ["持仓", "流水"]
    assert not legacy.exists(), "旧库应改名而不是留着同名文件"
    parked = tmp_path / ("invest.db" + MIGRATED_SUFFIX + "20250101120000")
    assert parked.exists(), "旧库必须留档，迁错了才能改回来"
    assert _read_notes(parked) == ["持仓", "流水"]


def test_migrate_keeps_existing_target(tmp_path):
    legacy = tmp_path / "invest.db"
    _make_db(legacy, [("旧",)])
    target = tmp_path / "invest.db.new"
    _make_db(target, [("新",)])

    assert migrate_legacy_into(legacy, target) is False
    assert _read_notes(target) == ["新"]
    assert legacy.exists()


def test_migrate_without_legacy_is_noop(tmp_path):
    assert migrate_legacy_into(tmp_path / "missing.db", tmp_path / "out.db") is False


def test_first_run_migrates_and_reports_source(tmp_path):
    project = tmp_path / "repo"
    (project / "data").mkdir(parents=True)
    legacy = project / "data" / "invest.db"
    _make_db(legacy, [("老账本",)])
    env = {"HOME": str(tmp_path / "home")}
    target = resolve_data_paths(str(project), env).db_path

    assert migrate_on_first_run(str(project), env, stamp="20250101") == str(legacy)

    assert _read_notes(target) == ["老账本"]
    assert not legacy.exists()


def test_first_run_is_noop_when_db_path_is_set(tmp_path):
    project = tmp_path / "repo"
    (project / "data").mkdir(parents=True)
    legacy = project / "data" / "invest.db"
    _make_db(legacy)
    env = {"HOME": str(tmp_path / "home"), "DB_PATH": str(tmp_path / "elsewhere.db")}

    assert migrate_on_first_run(str(project), env) is None
    assert legacy.exists(), "显式指定 DB_PATH 时不许动仓库里的库（Docker/VPS/测试）"


def test_second_start_does_not_migrate_twice(tmp_path):
    project = tmp_path / "repo"
    (project / "data").mkdir(parents=True)
    legacy = project / "data" / "invest.db"
    _make_db(legacy, [("老账本",)])
    env = {"HOME": str(tmp_path / "home")}

    assert migrate_on_first_run(str(project), env) == str(legacy)
    assert migrate_on_first_run(str(project), env) is None


def test_first_run_without_legacy_starts_empty(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()
    assert migrate_on_first_run(str(project), {"HOME": str(tmp_path / "home")}) is None


# ------------------------------------------------------------ 前端产物查找


def test_find_frontend_dist_explicit(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    assert find_frontend_dist(None, {"FRONTEND_DIST": str(dist)}) == str(dist)


def test_find_frontend_dist_explicit_missing_is_none(tmp_path):
    assert find_frontend_dist(None, {"FRONTEND_DIST": str(tmp_path / "nope")}) is None


def test_find_frontend_dist_uses_project_dist(tmp_path):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    assert find_frontend_dist(str(tmp_path), {}) == str(dist)


# --------------------------------------------------- 单进程模式：一个端口


def test_spa_serves_index_at_root(spa_app):
    response = TestClient(spa_app.app).get("/")
    assert response.status_code == 200
    assert "spa-index" in response.text


def test_spa_history_route_falls_back_to_index(spa_app):
    response = TestClient(spa_app.app).get("/performance/drawdown")
    assert response.status_code == 200
    assert "spa-index" in response.text


def test_spa_serves_assets(spa_app):
    response = TestClient(spa_app.app).get("/assets/app.js")
    assert response.status_code == 200
    assert "spa-asset" in response.text


def test_api_prefix_reaches_backend_without_nginx(spa_app):
    response = TestClient(spa_app.app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unknown_api_path_stays_json_404(spa_app):
    response = TestClient(spa_app.app).get("/api/not-a-route")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}


def test_path_traversal_cannot_escape_dist(spa_app):
    response = TestClient(spa_app.app).get("/%2e%2e%2f%2e%2e%2fetc%2fpasswd")
    assert "root:" not in response.text


def test_pure_api_mode_has_no_spa_fallback(client):
    assert client.get("/").status_code == 404
    assert client.get("/health").status_code == 200


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
