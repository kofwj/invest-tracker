#!/usr/bin/env python3
"""Restore Invest Tracker SQLite database from a backup file.

Safety behavior:
1. Refuses missing/non-SQLite-corrupt backup via PRAGMA integrity_check.
2. Creates a pre-restore backup of current data/invest.db first.
3. Atomically replaces data/invest.db.

Usage:
  python3 scripts/restore_db.py backups/invest_20260512_090000.db.bak
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

from backup_db import backup_db

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "invest.db"
DEFAULT_BACKUP_DIR = ROOT / "backups"


def check_sqlite(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"backup not found: {path}")
    with sqlite3.connect(str(path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result.lower() != "ok":
        raise RuntimeError(f"backup integrity check failed: {result}")


def restore_db(backup: Path, db: Path) -> None:
    check_sqlite(backup)
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        pre = backup_db(db.resolve(), DEFAULT_BACKUP_DIR.resolve(), "before_restore")
        print(f"pre-restore backup: {pre}")
    tmp = db.with_suffix(db.suffix + ".restore_tmp")
    shutil.copy2(str(backup), str(tmp))
    tmp.replace(db)
    check_sqlite(db)
    print(f"restored: {db} <- {backup}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore Invest Tracker SQLite DB")
    parser.add_argument("backup", help="backup file path, e.g. backups/invest_*.db.bak")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="target SQLite DB path")
    args = parser.parse_args()
    restore_db(Path(args.backup).expanduser().resolve(), Path(args.db).expanduser().resolve())


if __name__ == "__main__":
    main()
