#!/usr/bin/env python3
"""Legacy Excel migration helper.

This script is intentionally disabled by default because it was created for a
one-off historical Excel import/update flow and can overwrite deposits data.

Use only after creating a DB backup and only with an explicit Excel file path:
  python3 scripts/legacy_update_db.py --excel /path/to/file.xlsm --db data/invest.db --yes-i-understand
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "invest.db"


def update_data(db_path: Path, excel_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))

    # Add category column if missing.
    try:
        conn.execute("ALTER TABLE holdings ADD COLUMN category TEXT")
    except sqlite3.OperationalError:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT,
            amount REAL,
            interest_rate REAL,
            due_date TEXT,
            remark TEXT
        )
    """)

    df = pd.read_excel(str(excel_path), sheet_name="持仓明细")

    updated = 0
    for _, row in df.iterrows():
        cat = row.iloc[0]
        code = str(row.iloc[2])
        if pd.notna(cat) and pd.notna(code) and code != "nan":
            conn.execute("UPDATE holdings SET category = ? WHERE code = ?", (cat, code))
            if conn.total_changes > 0:
                updated += 1
    print(f"Categories updated: {updated}")

    # Destructive legacy behavior: replace deposits with rows from Excel cash section.
    cash_rows = df[df.iloc[:, 0] == "现金"]
    bank_rows = cash_rows[(cash_rows.iloc[:, 1] != "银行存款") & (cash_rows.iloc[:, 1] != "证券资金")]

    conn.execute("DELETE FROM deposits")
    imported = 0
    for _, row in bank_rows.iterrows():
        bank_name = str(row.iloc[1])
        amount = float(row.iloc[4])
        rate_raw = row.iloc[6]
        rate = float(rate_raw) * 100 if pd.notna(rate_raw) else None
        conn.execute(
            "INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark) VALUES (?, ?, ?, ?, ?)",
            (bank_name, amount, rate, None, None),
        )
        imported += 1
    print(f"Deposits imported: {imported}")

    conn.commit()
    conn.close()
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Disabled legacy Excel update helper")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="target SQLite DB path")
    parser.add_argument("--excel", required=True, help="source Excel .xlsm/.xlsx path")
    parser.add_argument(
        "--yes-i-understand",
        action="store_true",
        help="required: confirms this legacy script may overwrite deposits",
    )
    args = parser.parse_args()

    if not args.yes_i_understand:
        raise SystemExit("Refusing to run legacy destructive update without --yes-i-understand")

    db_path = Path(args.db).expanduser().resolve()
    excel_path = Path(args.excel).expanduser().resolve()
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    update_data(db_path, excel_path)


if __name__ == "__main__":
    main()
