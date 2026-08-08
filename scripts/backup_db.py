#!/usr/bin/env python3
"""Create a timestamped backup of the Invest Tracker SQLite database.

Default:
  source: data/invest.db
  target: backups/invest_YYYYmmdd_HHMMSS.db.bak

Optional:
  --retain N    after backing up, keep only the N most recent invest_*.db.bak
                backups under the backup dir (0 disables rotation, default).

The script uses sqlite3 online backup API when possible, so it is safer than
plain file copy while the app is running.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "invest.db"
DEFAULT_BACKUP_DIR = ROOT / "backups"
LOCAL_TZ = ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Shanghai"))

# invest_YYYYmmdd_HHMMSS[._label].db.bak
_BACKUP_RE = re.compile(r"^invest_\d{8}_\d{6}(?:[._].*)?\.db\.bak$")


def _is_backup_file(name: str) -> bool:
    return bool(_BACKUP_RE.match(name))


def rotate_backups(backup_dir: Path, retain: int) -> int:
    """Delete oldest invest_*.db.bak files so at most `retain` remain. Returns count deleted."""
    if not retain or retain <= 0:
        return 0
    files = sorted(
        (p for p in backup_dir.iterdir() if p.is_file() and _is_backup_file(p.name)),
        key=lambda p: p.name,  # timestamp prefix sorts chronologically
    )
    deleted = 0
    for stale in files[:-retain]:
        try:
            stale.unlink()
            deleted += 1
        except OSError as e:
            print(f"rotation skip {stale.name}: {e}", file=sys.stderr)
    return deleted


def backup_db(source: Path, backup_dir: Path, label: str | None = None, retain: int = 0) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"database not found: {source}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(LOCAL_TZ).strftime("%Y%m%d_%H%M%S")
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

    if retain and retain > 0:
        removed = rotate_backups(backup_dir, retain)
        if removed:
            print(f"rotated: removed {removed} old backup(s)")

    print(target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup Invest Tracker SQLite DB")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="source SQLite DB path")
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR), help="backup output directory")
    parser.add_argument("--label", default=None, help="optional label appended to filename")
    parser.add_argument(
        "--retain",
        type=int,
        default=int(os.environ.get("BACKUP_RETAIN", "0")),
        help="keep only the N most recent backups (0 disables rotation)",
    )
    args = parser.parse_args()

    backup_db(
        Path(args.db).expanduser().resolve(),
        Path(args.backup_dir).expanduser().resolve(),
        args.label,
        retain=args.retain,
    )


if __name__ == "__main__":
    main()
