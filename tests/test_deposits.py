def test_deposit_add_update_delete_reflects_in_dashboard(client):
    add_resp = client.post('/deposits', json={
        'bank_name': '招商银行',
        'amount': 100000,
        'interest_rate': 1.8,
        'due_date': '2026-12-31',
        'remark': 'first deposit'
    })
    assert add_resp.status_code == 200
    deposit_id = add_resp.json()['id']

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
