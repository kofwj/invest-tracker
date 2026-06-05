import sqlite3

try:
    from .cash import ensure_cash_base, set_setting
    from .database import open_db
    from .holdings import ensure_holding_return_columns
    from .snapshots import ensure_snapshot_columns, ensure_portfolio_cash_flows_table
except ImportError:
    from cash import ensure_cash_base, set_setting
    from database import open_db
    from holdings import ensure_holding_return_columns
    from snapshots import ensure_snapshot_columns, ensure_portfolio_cash_flows_table


def table_columns(conn, table_name):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def ensure_core_tables(conn):
    """Create the core application tables required for a fresh SQLite database."""
    conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        code TEXT,
        name TEXT,
        category TEXT,
        account TEXT DEFAULT '华泰证券',
        direction TEXT,
        quantity REAL DEFAULT 0,
        price REAL DEFAULT 0,
        amount REAL DEFAULT 0,
        fee REAL DEFAULT 0,
        remark TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        name TEXT,
        category TEXT,
        quantity REAL DEFAULT 0,
        avg_cost REAL DEFAULT 0,
        diluted_cost REAL DEFAULT 0,
        total_dividend REAL DEFAULT 0,
        last_price REAL DEFAULT 0,
        updated_at DATETIME,
        expected_return REAL DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bank_name TEXT,
        amount REAL,
        interest_rate REAL,
        due_date TEXT,
        remark TEXT
    )""")
    ensure_holding_return_columns(conn)


def ensure_app_schema(conn):
    ensure_core_tables(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cash_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE,
        account TEXT DEFAULT '华泰证券',
        flow_type TEXT,
        amount REAL,
        balance_before REAL,
        balance_after REAL,
        remark TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE UNIQUE,
        total_assets REAL,
        total_market_value REAL,
        bank_balance REAL,
        securities_cash REAL,
        pending_purchase REAL DEFAULT 0,
        total_profit REAL,
        holdings_count INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS holding_corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date DATE NOT NULL,
        code TEXT NOT NULL,
        name TEXT,
        category TEXT,
        actual_quantity REAL NOT NULL,
        actual_avg_cost REAL NOT NULL,
        actual_total_dividend REAL DEFAULT 0,
        remark TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    ensure_portfolio_cash_flows_table(conn)
    ensure_snapshot_columns(conn)


def initialize_database():
    with open_db() as conn:
        ensure_app_schema(conn)
        conn.commit()


def run_startup_migrations():
    """Initialize schema and run lightweight migrations needed by older local databases."""
    initialize_database()
    conn = open_db(row_factory=sqlite3.Row)
    cols = table_columns(conn, "transactions")
    if "account" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN account TEXT")
        conn.execute("UPDATE transactions SET account = '华泰证券' WHERE account IS NULL OR TRIM(account) = ''")
    row = conn.execute("SELECT value FROM settings WHERE key='securities_cash'").fetchone()
    if not row:
        set_setting(conn, 'securities_cash', 0)
    ensure_cash_base(conn)
    conn.commit()
    conn.close()
