import pandas as pd
import sqlite3
from datetime import datetime
import os

DB_PATH = "/Users/jian/invest-tracker/data/invest.db"
EXCEL_PATH = "/Users/jian/.hermes-web-ui/upload/8cdb9dd666abe1ba.xlsm"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        name TEXT,
        code TEXT UNIQUE,
        target_weight REAL,
        remark TEXT
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        code TEXT,
        name TEXT,
        direction TEXT,
        quantity REAL,
        price REAL,
        amount REAL,
        fee REAL,
        remark TEXT
    );
    CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        name TEXT,
        quantity REAL,
        avg_cost REAL,
        diluted_cost REAL,
        total_dividend REAL,
        last_price REAL,
        updated_at DATETIME
    );
    """)
    conn.commit()
    return conn

def import_data():
    conn = init_db()
    
    # 1. Import Transactions
    df_trans = pd.read_excel(EXCEL_PATH, sheet_name="交易记录")
    # Columns are exactly ['日期', '代码', '名称', '方向', '数量', '单价', '金额', '手续费', '备注']
    df_trans.columns = ['date', 'code', 'name', 'direction', 'quantity', 'price', 'amount', 'fee', 'remark']
    df_trans['date'] = pd.to_datetime(df_trans['date']).dt.strftime('%Y-%m-%d')
    # Drop rows with all NaN
    df_trans = df_trans.dropna(subset=['date', 'code', 'direction'])
    df_trans.to_sql('transactions', conn, if_exists='append', index=False)
    
    # 2. Import Assets from 持仓明细
    df_holdings = pd.read_excel(EXCEL_PATH, sheet_name="持仓明细")
    # Columns usually have a leading empty col if it was formatted as a table in Excel
    if df_holdings.columns[0].startswith('Unnamed'):
        df_holdings = df_holdings.iloc[:, 1:]
    
    # Expected columns based on header: 资产大类,名称,代码,当前价,持仓数量,买入均价,摊薄成本价,市值,累计分红,持仓总成本,累计总盈亏,盈亏比例,2025年每股分红,YOC,目标占比,持仓权重,动作建议,备注
    for _, row in df_holdings.iterrows():
        code = str(row['代码'])
        if pd.isna(row['代码']) or code == 'nan': continue
        
        # Insert asset
        try:
            conn.execute("INSERT INTO assets (category, name, code, target_weight, remark) VALUES (?, ?, ?, ?, ?)",
                        (row['资产大类'], row['名称'], code, row['目标占比'] if not pd.isna(row['目标占比']) else 0.0, row['备注']))
        except sqlite3.IntegrityError:
            pass
            
        # Insert initial holding state
        conn.execute("INSERT OR REPLACE INTO holdings (code, name, quantity, avg_cost, diluted_cost, total_dividend, last_price, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (code, row['名称'], row['持仓数量'], row['买入均价'], row['摊薄成本价'], row['累计分红'], row['当前价'], datetime.now()))

    conn.commit()
    print("Import completed.")

if __name__ == "__main__":
    import_data()
