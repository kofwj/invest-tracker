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
