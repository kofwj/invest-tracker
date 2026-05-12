import sqlite3
import pandas as pd

DB_PATH = "/app/data/invest.db"
EXCEL_PATH = "/Users/jian/.hermes-web-ui/upload/8cdb9dd666abe1ba.xlsm"

def update_data():
    conn = sqlite3.connect("data/invest.db")
    
    # Add category column if missing
    try:
        conn.execute("ALTER TABLE holdings ADD COLUMN category TEXT")
    except:
        pass

    # Ensure deposits table exists
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

    df = pd.read_excel(EXCEL_PATH, sheet_name="持仓明细")

    # --- Fix: category = col 0 (资产大类), code = col 2 (代码) ---
    updated = 0
    for _, row in df.iterrows():
        cat = row.iloc[0]       # 资产大类 (was 1 → 名称)
        code = str(row.iloc[2]) # 代码 (was 3 → 当前价)
        if pd.notna(cat) and pd.notna(code) and code != 'nan':
            # Strip 'f' prefix for off-exchange fund codes
            conn.execute(
                "UPDATE holdings SET category = ? WHERE code = ?",
                (cat, code)
            )
            if conn.total_changes > 0:
                updated += 1
    print(f"Categories updated: {updated}")

    # --- Import bank deposits from Excel rows where 资产大类=='现金' ---
    cash_rows = df[df.iloc[:, 0] == '现金']
    # Skip aggregate "银行存款" row — only import individual bank rows
    bank_rows = cash_rows[
        (cash_rows.iloc[:, 1] != '银行存款') &
        (cash_rows.iloc[:, 1] != '证券资金')
    ]

    conn.execute("DELETE FROM deposits")
    imported = 0
    for _, row in bank_rows.iterrows():
        bank_name = str(row.iloc[1])      # 名称 → bank name
        amount = float(row.iloc[4])        # 持仓数量 → amount
        rate_raw = row.iloc[6]             # 摊薄成本价 → interest rate
        rate = float(rate_raw) * 100 if pd.notna(rate_raw) else None
        
        conn.execute(
            "INSERT INTO deposits (bank_name, amount, interest_rate, due_date, remark) VALUES (?, ?, ?, ?, ?)",
            (bank_name, amount, rate, None, None)
        )
        imported += 1
    print(f"Deposits imported: {imported}")

    conn.commit()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    update_data()