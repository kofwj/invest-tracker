def test_backend_exposes_centralized_config(app_module):
    assert app_module.APP_CONFIG.db_path.endswith('test.db')
    assert str(app_module.APP_CONFIG.local_timezone) == 'Asia/Shanghai'


def test_health_endpoint_uses_database_probe(app_module):
    result = app_module.check_database_health()

    assert result == 'ok'


def test_database_fetch_helper_returns_dict_rows(app_module):
    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        app_module.set_setting(conn, 'health_probe_key', 'ready')
        conn.commit()

    rows = app_module.fetch_all_as_dicts(
        app_module.DB_PATH,
        'SELECT key, value FROM settings WHERE key = ?',
        ('health_probe_key',),
    )

    assert rows == [{'key': 'health_probe_key', 'value': 'ready'}]


def test_database_initialization_records_schema_version(app_module):
    import schema
    rows = app_module.fetch_all_as_dicts(
        app_module.DB_PATH,
        'SELECT value FROM settings WHERE key = ?',
        ('schema_version',),
    )

    assert rows == [{'value': str(schema.SCHEMA_VERSION)}]


def test_migrate_v12_focus_generalizes(app_module):
    import json

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        # 全新库(无持仓)运行迁移 -> 不注入
        from schema import migrate_to_v12_focus_defaults
        migrate_to_v12_focus_defaults(conn)
        row = conn.execute(
            "SELECT value FROM settings WHERE key='discipline_policy'"
        ).fetchone()
        assert row is None or json.loads(row[0] or '{}') == {}

        # 有持仓但 focus 未自定义 -> 固化 legacy
        conn.execute(
            "INSERT INTO holdings(code,name,category,quantity,last_price,avg_cost,diluted_cost,total_dividend) "
            "VALUES ('600028','中国石化','A股权益',100000,6.0,5.0,5.0,0)"
        )
        migrate_to_v12_focus_defaults(conn)
        row = conn.execute(
            "SELECT value FROM settings WHERE key='discipline_policy'"
        ).fetchone()
        focus = json.loads(row[0]).get('focus', {})
        assert '601288' in (focus.get('dividend_bucket_codes') or [])
        assert focus.get('gold_codes') == ['518880']


def test_migrate_v21_discipline_defaults_generalizes(app_module):
    import json

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        from schema import migrate_to_v21_discipline_defaults
        # 空库不注入
        conn.execute("DELETE FROM holdings")
        conn.execute("DELETE FROM settings WHERE key='discipline_policy'")
        migrate_to_v21_discipline_defaults(conn)
        row = conn.execute("SELECT value FROM settings WHERE key='discipline_policy'").fetchone()
        assert row is None

        # 有持仓但未自定义 -> 固化 legacy 个人默认
        conn.execute(
            "INSERT INTO holdings(code,name,category,quantity,last_price,avg_cost,diluted_cost,total_dividend) "
            "VALUES ('600028','中国石化','A股权益',100000,6.0,5.0,5.0,0)"
        )
        migrate_to_v21_discipline_defaults(conn)
        row = conn.execute("SELECT value FROM settings WHERE key='discipline_policy'").fetchone()
        assert row is not None
        pol = json.loads(row[0])
        assert pol.get("preferred_buy_code") == "159352"
        assert pol.get("plans", {}).get("batch_buy_code") == "159352"


def test_database_initialization_migrates_missing_transaction_account(app_module):
    import sqlite3

    with app_module.get_db_connection(app_module.DB_PATH) as conn:
        conn.execute('DROP TABLE transactions')
        conn.execute('''
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE,
                code TEXT,
                name TEXT,
                direction TEXT,
                quantity REAL DEFAULT 0,
                price REAL DEFAULT 0,
                amount REAL DEFAULT 0,
                fee REAL DEFAULT 0,
                remark TEXT
            )
        ''')
        conn.execute(
            'INSERT INTO transactions (date, code, name, direction, quantity, price, amount) VALUES (?, ?, ?, ?, ?, ?, ?)',
            ('2026-05-19', '600000', '浦发银行', '买入', 100, 10, 1000),
        )
        app_module.set_setting(conn, 'schema_version', 0)
        conn.commit()

    app_module.initialize_database()

    with app_module.get_db_connection(app_module.DB_PATH, row_factory=sqlite3.Row) as conn:
        cols = [row[1] for row in conn.execute('PRAGMA table_info(transactions)').fetchall()]
        row = conn.execute('SELECT account FROM transactions').fetchone()

    assert 'category' in cols
    assert 'account' in cols
    assert row['account'] == '华泰证券'


def test_database_file_is_owner_only(app_module, client):
    """账本库里存着明文凭据（AI API key、推送通道 secret），权限必须是 0600。

    sqlite3 建出来的文件权限跟着 umask 走、默认 0644 —— 同机任何用户都能读。
    open_db() 首次打开时会收成 0600，这条测试盯着那段逻辑别被删掉。
    """
    import os

    path = str(app_module.DB_PATH)
    assert os.path.exists(path)
    assert os.stat(path).st_mode & 0o777 == 0o600
