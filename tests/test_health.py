def test_health_endpoint_reports_ok(client):
    response = client.get('/api/health')

    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'
    assert data['database'] == 'ok'
    assert data['timezone'] == 'Asia/Shanghai'
    assert data['db_path'].endswith('test.db')
