"""Tests for scripts/backup_db.py rotation (--retain N).

Pure file-level logic, no DB / no network. Backend modules are NOT needed here.
"""
import importlib.util
import sys
from pathlib import Path

import pytest


def _load_backup_db():
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    path = scripts_dir / "backup_db.py"
    if not path.exists():
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        path = scripts_dir / "backup_db.py"
    spec = importlib.util.spec_from_file_location("backup_db_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def backup_mod():
    return _load_backup_db()


def _touch(backup_dir: Path, name: str):
    (backup_dir / name).write_text("x", encoding="utf-8")


def test_is_backup_file_matches_expected(backup_mod):
    assert backup_mod._is_backup_file("invest_20260808_153000.db.bak")
    assert backup_mod._is_backup_file("invest_20260808_153000_before_deploy.db.bak")
    assert backup_mod._is_backup_file("invest_20260808_153000.market_1_5.db.bak")
    assert not backup_mod._is_backup_file("invest.db")
    assert not backup_mod._is_backup_file("cron_sync_prices.log")
    assert not backup_mod._is_backup_file("notes.txt")


def test_rotate_keeps_retain_most_recent(backup_mod, tmp_path):
    b = tmp_path / "backups"
    b.mkdir()
    # 5 backups, oldest first by timestamp prefix
    for i in range(5):
        _touch(b, f"invest_2026080{1 + i}_120000.db.bak")
    # a non-backup file must survive rotation
    _touch(b, "keep_me.log")
    (b / "invest_20260803_120000_oldlabel.db.bak").unlink(missing_ok=True)

    deleted = backup_mod.rotate_backups(b, retain=2)

    remaining = sorted(p.name for p in b.iterdir())
    # 3 deleted (5 - 2), keep_me.log untouched
    assert deleted == 3
    assert remaining == [
        "invest_20260804_120000.db.bak",
        "invest_20260805_120000.db.bak",
        "keep_me.log",
    ]


def test_rotate_retain_zero_does_nothing(backup_mod, tmp_path):
    b = tmp_path / "backups"
    b.mkdir()
    for i in range(4):
        _touch(b, f"invest_2026080{1 + i}_120000.db.bak")

    assert backup_mod.rotate_backups(b, retain=0) == 0
    assert len(list(b.iterdir())) == 4


def test_backup_db_with_retain_rotates(backup_mod, tmp_path):
    db = tmp_path / "data" / "invest.db"
    db.parent.mkdir()
    b = tmp_path / "backups"
    b.mkdir()
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    # Pre-existing backups
    _touch(b, "invest_20260801_120000.db.bak")
    _touch(b, "invest_20260802_120000.db.bak")

    target = backup_mod.backup_db(db, b, retain=1)

    assert target.exists()
    remaining = sorted(p.name for p in b.iterdir())
    # newest 1 kept, 2 old rotated away
    assert remaining == [target.name]
    assert backup_mod._is_backup_file(target.name)