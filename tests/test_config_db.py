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
    rows = app_module.fetch_all_as_dicts(
        app_module.DB_PATH,
        'SELECT value FROM settings WHERE key = ?',
        ('schema_version',),
    )

    assert rows == [{'value': '7'}]


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
