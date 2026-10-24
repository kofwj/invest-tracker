def test_health_endpoint_reports_ok(client):
    response = client.get('/api/health')

    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'
    assert data['database'] == 'ok'
    assert data['timezone'] == 'Asia/Shanghai'
    assert data['version']
    assert 'db_path' not in data


def test_proxied_health_endpoint_same_shape(client):
    response = client.get('/health')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'
    assert data['version']
    assert 'db_path' not in data


def test_health_version_matches_backend_version(app_module, client):
    from version import APP_VERSION

    assert client.get('/api/health').json()['version'] == APP_VERSION


def test_health_reports_trading_calendar_coverage(client):
    """节假日表过期要在 /health 上看得见，别等净值曲线出现重复点才发现。"""
    calendar = client.get('/api/health').json()['trading_calendar']

    assert calendar['covered_years']
    assert calendar['last_covered_year'] == calendar['covered_years'][-1]
    assert isinstance(calendar['stale'], bool)
    assert isinstance(calendar['expiring'], bool)
    # message 非空当且仅当需要有人动手，别在正常年份天天喊
    assert bool(calendar['message']) == (calendar['stale'] or calendar['expiring'])
