import sqlite3

try:
    from .cash import ensure_cash_base, set_setting
    from .database import open_db
    from .holdings import ensure_holding_return_columns
    from .market import ensure_alert_tables
    from .snapshots import ensure_snapshot_columns, ensure_portfolio_cash_flows_table
except ImportError:
    from cash import ensure_cash_base, set_setting
    from database import open_db
    from holdings import ensure_holding_return_columns
    from market import ensure_alert_tables
    from snapshots import ensure_snapshot_columns, ensure_portfolio_cash_flows_table


SCHEMA_VERSION = 5
SCHEMA_VERSION_KEY = "schema_version"


def table_columns(conn, table_name):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def ensure_metadata_table(conn):
    """Create the key-value metadata/settings table used by migrations and app config."""
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")


def get_schema_version(conn):
    ensure_metadata_table(conn)
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (SCHEMA_VERSION_KEY,)).fetchone()
    if not row:
        return 0
    value = row["value"] if isinstance(row, sqlite3.Row) else row[0]
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def set_schema_version(conn, version):
    set_setting(conn, SCHEMA_VERSION_KEY, int(version))


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


def ensure_app_tables(conn):
    """Create all current tables. Column backfills are handled by versioned migrations."""
    ensure_core_tables(conn)
    ensure_metadata_table(conn)
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
    ensure_alert_tables(conn)


def migrate_to_v1_core_compat(conn):
    """Backfill columns introduced while moving to the current core table shape."""
    transaction_cols = table_columns(conn, "transactions")
    if "category" not in transaction_cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN category TEXT")
    if "account" not in transaction_cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN account TEXT")
    conn.execute("UPDATE transactions SET account = '华泰证券' WHERE account IS NULL OR TRIM(account) = ''")


def migrate_to_v2_holdings_and_snapshots(conn):
    """Ensure derived holding return fields and snapshot pending purchase field exist."""
    ensure_holding_return_columns(conn)
    ensure_snapshot_columns(conn)


def migrate_to_v3_performance_cash_flows(conn):
    """Ensure portfolio-level external cash flow table exists for performance analysis."""
    ensure_portfolio_cash_flows_table(conn)


def migrate_to_v4_cash_settings(conn):
    """Ensure securities cash settings use the newer cash-base model."""
    row = conn.execute("SELECT value FROM settings WHERE key='securities_cash'").fetchone()
    if not row:
        set_setting(conn, "securities_cash", 0)
    ensure_cash_base(conn)


def migrate_to_v5_market_alerts(conn):
    """Market summary + price alert tables (read-only observer)."""
    ensure_alert_tables(conn)


MIGRATIONS = [
    (1, migrate_to_v1_core_compat),
    (2, migrate_to_v2_holdings_and_snapshots),
    (3, migrate_to_v3_performance_cash_flows),
    (4, migrate_to_v4_cash_settings),
    (5, migrate_to_v5_market_alerts),
]


def apply_schema_migrations(conn):
    """Run pending schema/data migrations once, tracked by settings.schema_version."""
    current = get_schema_version(conn)
    for version, migration in MIGRATIONS:
        if current < version:
            migration(conn)
            set_schema_version(conn, version)
            current = version
    return current


def ensure_app_schema(conn):
    ensure_app_tables(conn)
    apply_schema_migrations(conn)


def initialize_database():
    with open_db() as conn:
        ensure_app_schema(conn)
        conn.commit()


def run_startup_migrations():
    """Initialize schema and run versioned migrations needed by older local databases."""
    initialize_database()
