def test_deposit_add_update_delete_reflects_in_dashboard(client):
    add_resp = client.post('/deposits', json={
        'bank_name': '招商银行',
        'amount': 100000,
        'interest_rate': 1.8,
        'start_date': '2026-01-01',
        'due_date': '2026-12-31',
        'remark': 'first deposit'
    })
    assert add_resp.status_code == 200
    deposit_id = add_resp.json()['id']

    list_resp = client.get('/deposits')
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]['start_date'] == '2026-01-01'
    assert rows[0]['due_date'] == '2026-12-31'

    dashboard = client.get('/dashboard')
    assert dashboard.status_code == 200
    assert dashboard.json()['bank_balance'] == 100000

    update_resp = client.put(f'/deposits/{deposit_id}', json={'amount': 120000})
    assert update_resp.status_code == 200

    dashboard = client.get('/dashboard')
    assert dashboard.status_code == 200
    assert dashboard.json()['bank_balance'] == 120000

    delete_resp = client.delete(f'/deposits/{deposit_id}')
    assert delete_resp.status_code == 200

    dashboard = client.get('/dashboard')
    assert dashboard.status_code == 200
    assert dashboard.json()['bank_balance'] == 0


def test_deposit_start_date_optional_and_updateable(client):
    add_resp = client.post('/deposits', json={
        'bank_name': '交行',
        'amount': 200000,
        'interest_rate': 1.3,
        'due_date': '2026-07-18',
    })
    assert add_resp.status_code == 200
    deposit_id = add_resp.json()['id']

    row = client.get('/deposits').json()[0]
    assert row.get('start_date') in (None, '')

    upd = client.put(f'/deposits/{deposit_id}', json={'start_date': '2025-07-18'})
    assert upd.status_code == 200
    row = client.get('/deposits').json()[0]
    assert row['start_date'] == '2025-07-18'
