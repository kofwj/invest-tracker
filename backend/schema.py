import json
import sqlite3

try:
    from .cash import ensure_cash_base, set_setting, ensure_cash_flow_indexes
    from .database import open_db
    from .discipline import ensure_discipline_tables
    from .holding_calculator import ensure_holding_correction_indexes
    from .holdings import ensure_holding_return_columns
    from .kline_cache import ensure_kline_cache_table
    from .market import ensure_alert_tables
    from .notify import ensure_notify_tables
    from .broker_reconcile import ensure_broker_reconcile_history_table
    from .snapshots import ensure_snapshot_columns, ensure_portfolio_cash_flows_table, ensure_reconcile_table
    from .ai_client import ensure_ai_tables
    from .reason_cache import ensure_reason_tables
    from .dividend_calendar import ensure_dividend_event_tables
except ImportError:
    from cash import ensure_cash_base, set_setting, ensure_cash_flow_indexes
    from database import open_db
    from discipline import ensure_discipline_tables
    from holding_calculator import ensure_holding_correction_indexes
    from holdings import ensure_holding_return_columns
    from kline_cache import ensure_kline_cache_table
    from market import ensure_alert_tables
    from notify import ensure_notify_tables
    from broker_reconcile import ensure_broker_reconcile_history_table
    from snapshots import ensure_snapshot_columns, ensure_portfolio_cash_flows_table, ensure_reconcile_table
    from ai_client import ensure_ai_tables
    from reason_cache import ensure_reason_tables
    from dividend_calendar import ensure_dividend_event_tables


SCHEMA_VERSION = 20
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
        start_date TEXT,
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
        lifetime_profit REAL DEFAULT 0,
        holdings_count INTEGER,
        equity_mv REAL DEFAULT 0,
        bond_mv REAL DEFAULT 0,
        reit_mv REAL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    ensure_snapshot_columns(conn)
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
    ensure_discipline_tables(conn)
    ensure_notify_tables(conn)
    ensure_kline_cache_table(conn)
    ensure_broker_reconcile_history_table(conn)
    ensure_cash_flow_indexes(conn)
    ensure_holding_correction_indexes(conn)
    ensure_ai_tables(conn)
    ensure_reason_tables(conn)


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


def migrate_to_v6_snapshot_lifetime_and_watchlist(conn):
    """Snapshot lifetime_profit column + market watchlist setting defaults."""
    ensure_snapshot_columns(conn)
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("market_watchlist",),
    ).fetchone()
    if not row:
        set_setting(conn, "market_watchlist", "[]")
    row2 = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("market_extra_closed_dates",),
    ).fetchone()
    if not row2:
        set_setting(conn, "market_extra_closed_dates", "[]")
    # alert cooldown minutes (per rule, default 240)
    row3 = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("alert_cooldown_minutes",),
    ).fetchone()
    if not row3:
        set_setting(conn, "alert_cooldown_minutes", "240")


def migrate_to_v7_discipline(conn):
    """Discipline rules + rebalance drafts (real portfolio, no auto-trade)."""
    ensure_discipline_tables(conn)
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("discipline_policy",),
    ).fetchone()
    if not row:
        # empty → runtime DEFAULT_POLICY used until user saves
        set_setting(conn, "discipline_policy", "{}")


def migrate_to_v8_deposit_start_date(conn):
    """Optional deposit start_date for full-term interest estimates."""
    cols = table_columns(conn, "deposits")
    if "start_date" not in cols:
        conn.execute("ALTER TABLE deposits ADD COLUMN start_date TEXT")


def migrate_to_v9_notify(conn):
    """Multi-channel notify log + default settings keys."""
    ensure_notify_tables(conn)
    for key, default in (
        ("notify_enabled", "1"),
        ("notify_cooldown_minutes", "240"),
        ("notify_template", "medium"),
        ("notify_event_channels", "{}"),
    ):
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            set_setting(conn, key, default)


def migrate_to_v10_kline_cache(conn):
    """日K缓存表，用于持仓 K线图与未来技术指标。"""
    ensure_kline_cache_table(conn)


def migrate_to_v11_reconcile(conn):
    """人工对账表：手录实盘总资产与计算快照对比。"""
    ensure_reconcile_table(conn)


# 通用化：个人默认从代码 DEFAULT_POLICY 里移走后，这里保留"王此前默认的行为"，
# 仅给「已有持仓但 focus 从未自定义」的库固化，避免升级丢失；全新空库不注入。
LEGACY_FOCUS_DEFAULTS = {
    "dividend_bucket_codes": ["601288", "600028", "513530"],  # 农行/石化/港股红利
    "dividend_bucket_equity_max_pct": 50.0,  # 占权益上限 %
    "reduce_tasks": [
        {"code": "600028", "kind": "clear", "label": "石化清仓"},
        {"code": "508056", "kind": "clear", "label": "REIT 转化"},
        {"code": "000651", "kind": "reduce", "target_pct": 11.0, "label": "格力减仓"},
    ],
    "gold_codes": ["518880"],
    "gold_target_min_pct": 3.0,
    "gold_target_max_pct": 5.0,
}


def migrate_to_v13_broker_reconcile_history(conn):
    """券商对账运行历史：预览/应用各记一条，便于回看上次差异。"""
    ensure_broker_reconcile_history_table(conn)


def migrate_to_v12_focus_defaults(conn):
    """把「已有持仓但 focus 未自定义」的库固化为 legacy 默认，保持行为；全新/空库不注入。"""
    try:
        has_holdings = conn.execute(
            "SELECT COUNT(*) FROM holdings WHERE quantity > 0"
        ).fetchone()[0] > 0
    except Exception:
        return
    if not has_holdings:
        return
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("discipline_policy",),
    ).fetchone()
    raw = {}
    if row and row[0]:
        try:
            raw = json.loads(row[0])
        except Exception:
            raw = {}
    focus = raw.get("focus")
    if isinstance(focus, dict) and (focus.get("dividend_bucket_codes") or focus.get("gold_codes")):
        # 已有用户自己的 focus，不动
        return
    raw["focus"] = LEGACY_FOCUS_DEFAULTS
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        ("discipline_policy", json.dumps(raw, ensure_ascii=False)),
    )


def migrate_to_v14_query_indexes(conn):
    """补查询索引（老库升级自动补齐；CREATE INDEX IF NOT EXISTS 幂等、不写数据）。

    背景：cash_flows / portfolio_cash_flows / holding_corrections / alert_events
    此前零索引，真实库上 EXPLAIN QUERY PLAN 证实为全表扫 + 临时 B 树排序。
    - daily_snapshots.unpriced_count 由 ensure_snapshot_columns 补列（缺价持仓只数）。
    """
    ensure_snapshot_columns(conn)
    ensure_portfolio_cash_flows_table(conn)
    ensure_alert_tables(conn)
    ensure_cash_flow_indexes(conn)
    ensure_holding_correction_indexes(conn)


def migrate_to_v15_snapshot_price_columns(conn):
    """快照价格新鲜度两列：price_date（价格日期）+ price_stale（低置信标记）。

    走 ensure_snapshot_columns 补列（幂等、不改已有数字），老库升级自动补；
    历史快照这两列为 NULL / 0，读出来回落成"不标记"。
    """
    ensure_snapshot_columns(conn)


def migrate_to_v16_snapshot_manual_price_column(conn):
    """快照人工价列：manual_price_count（该快照含人工价的持仓只数）。

    走 ensure_snapshot_columns 补列（幂等、不改已有数字），老库升级自动补；
    历史快照该列为 NULL，读出来回落成 0。
    """
    ensure_snapshot_columns(conn)


def migrate_to_v17_alert_rule_types(conn):
    """预警规则的种类与判定值：alert_rules.rule_type + alert_events.rule_type/value。

    老库里的规则全是绝对价格阈值，回填成 'price' → 行为完全不变；新类型
    （涨跌幅、组合当日盈亏）由用户自己新建。alert_events 那两列是为了让预警历史能
    区分"某标的价 12.5"和"组合当日盈亏 -1.5%" —— 光看 triggered_price 分不出。
    create table 里也带了同样的列，所以这条迁移只对已有库起作用。
    """
    ensure_alert_tables(conn)
    if "rule_type" not in table_columns(conn, "alert_rules"):
        conn.execute("ALTER TABLE alert_rules ADD COLUMN rule_type TEXT DEFAULT 'price'")
    conn.execute(
        "UPDATE alert_rules SET rule_type = 'price' WHERE rule_type IS NULL OR rule_type = ''"
    )
    event_cols = table_columns(conn, "alert_events")
    if "rule_type" not in event_cols:
        conn.execute("ALTER TABLE alert_events ADD COLUMN rule_type TEXT")
    if "value" not in event_cols:
        conn.execute("ALTER TABLE alert_events ADD COLUMN value REAL")


def migrate_to_v18_ai_and_reason_cache(conn):
    """AI 审计表 + 原因缓存四表，合并升到 v18。"""
    ensure_ai_tables(conn)
    ensure_reason_tables(conn)


def migrate_to_v19_ai_call_log_warnings(conn):
    """ai_call_log.warnings_json，影子模式一周要分项计数。"""
    ensure_ai_tables(conn)


def migrate_to_v20_dividend_events(conn):
    """除权除息日历本地表。幂等：CREATE TABLE IF NOT EXISTS。"""
    ensure_dividend_event_tables(conn)


MIGRATIONS = [
    (1, migrate_to_v1_core_compat),
    (2, migrate_to_v2_holdings_and_snapshots),
    (3, migrate_to_v3_performance_cash_flows),
    (4, migrate_to_v4_cash_settings),
    (5, migrate_to_v5_market_alerts),
    (6, migrate_to_v6_snapshot_lifetime_and_watchlist),
    (7, migrate_to_v7_discipline),
    (8, migrate_to_v8_deposit_start_date),
    (9, migrate_to_v9_notify),
    (10, migrate_to_v10_kline_cache),
    (11, migrate_to_v11_reconcile),
    (12, migrate_to_v12_focus_defaults),
    (13, migrate_to_v13_broker_reconcile_history),
    (14, migrate_to_v14_query_indexes),
    (15, migrate_to_v15_snapshot_price_columns),
    (16, migrate_to_v16_snapshot_manual_price_column),
    (17, migrate_to_v17_alert_rule_types),
    (18, migrate_to_v18_ai_and_reason_cache),
    (19, migrate_to_v19_ai_call_log_warnings),
    (20, migrate_to_v20_dividend_events),
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
