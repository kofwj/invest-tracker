#!/usr/bin/env python3
"""Create a pre-change safety snapshot: database backup + optional git commit.

This is intended to be run before risky changes:
  python3 scripts/safety_snapshot.py --label before_cash_formula_change

Behavior:
- Always creates a timestamped DB backup under backups/.
- If this directory is a git repository, stages code/docs/scripts/config files and
  creates a commit when there are changes. It intentionally does NOT add data/*.db
  or backups/*.bak because those are excluded by .gitignore.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from backup_db import backup_db

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "invest.db"
BACKUP_DIR = ROOT / "backups"


def run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=check)


def in_git_repo() -> bool:
    return run(["git", "rev-parse", "--is-inside-work-tree"]).returncode == 0


def git_snapshot(label: str) -> None:
    if not in_git_repo():
        print("git: skipped (not a git repository)")
        return
    run(["git", "add", "."], check=True)
    diff_cached = run(["git", "diff", "--cached", "--quiet"])
    if diff_cached.returncode == 0:
        print("git: no code/doc changes to commit")
        return
    msg = f"safety snapshot: {label}"
    run(["git", "commit", "-m", msg], check=True)
    print(f"git: committed '{msg}'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create DB backup and git safety commit")
    parser.add_argument("--label", default="manual", help="snapshot label")
    args = parser.parse_args()

    backup = backup_db(DB.resolve(), BACKUP_DIR.resolve(), args.label)
    print(f"db backup: {backup}")
    git_snapshot(args.label)


if __name__ == "__main__":
    main()
