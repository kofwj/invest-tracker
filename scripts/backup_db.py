#!/usr/bin/env python3
"""Create a timestamped backup of the Invest Tracker SQLite database.

Default:
  source: data/invest.db
  target: backups/invest_YYYYmmdd_HHMMSS.db.bak

The script uses sqlite3 online backup API when possible, so it is safer than
plain file copy while the app is running.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "invest.db"
DEFAULT_BACKUP_DIR = ROOT / "backups"


def backup_db(source: Path, backup_dir: Path, label: str | None = None) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"database not found: {source}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = ""
    if label:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label.strip())
        safe_label = f"_{safe}" if safe else ""
    target = backup_dir / f"invest_{ts}{safe_label}.db.bak"

    # SQLite backup API: consistent backup even if DB is readable/live.
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
        src.backup(dst)

    # Quick integrity check on the backup.
    with sqlite3.connect(str(target)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result.lower() != "ok":
        target.unlink(missing_ok=True)
        raise RuntimeError(f"backup integrity check failed: {result}")

    print(target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup Invest Tracker SQLite DB")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="source SQLite DB path")
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR), help="backup output directory")
    parser.add_argument("--label", default=None, help="optional label appended to filename")
    args = parser.parse_args()

    backup_db(Path(args.db).expanduser().resolve(), Path(args.backup_dir).expanduser().resolve(), args.label)


if __name__ == "__main__":
    main()
