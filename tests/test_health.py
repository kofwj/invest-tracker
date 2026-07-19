def test_health_endpoint_reports_ok(client):
    response = client.get('/api/health')

    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'
    assert data['database'] == 'ok'
    assert data['timezone'] == 'Asia/Shanghai'
    assert 'db_path' not in data



def test_proxied_health_endpoint_same_shape(client):
    response = client.get('/health')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'
    assert 'db_path' not in data
