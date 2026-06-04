import sqlite3


def test_add_transaction_updates_holdings_and_securities_cash(client, app_module):
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    app_module.set_setting(conn, 'securities_cash_base', 10000)
    conn.commit()
    conn.close()

    resp = client.post('/transactions', json={
        'date': '2026-05-19',
        'code': '600000',
        'name': '浦发银行',
        'category': 'A股权益',
        'account': '华泰证券',
        'direction': '买入',
        'quantity': 100,
        'price': 10,
        'amount': 1000,
        'fee': 5,
        'remark': 'test buy'
    })
    assert resp.status_code == 200

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT code, quantity, avg_cost FROM holdings WHERE code = ?", ('600000',)).fetchone()
    conn.close()
    assert row is not None
    assert row['quantity'] == 100
    assert row['avg_cost'] == 10.05

    dashboard = client.get('/dashboard')
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data['securities_cash'] == 8995.0
    assert data['holdings_count'] == 1


def test_update_transaction_recalculates_holdings(client, app_module):
    create_resp = client.post('/transactions', json={
        'date': '2026-05-19',
        'code': '600002',
        'name': '测试编辑股票',
        'category': 'A股权益',
        'account': '华泰证券',
        'direction': '买入',
        'quantity': 100,
        'price': 10,
        'amount': 1000,
        'fee': 0,
        'remark': ''
    })
    assert create_resp.status_code == 200

    txs = client.get('/transactions').json()
    tx_id = next(t['id'] for t in txs if t['code'] == '600002')

    update_resp = client.put(f'/transactions/{tx_id}', json={
        'quantity': 200,
        'amount': 2200,
        'price': 11
    })
    assert update_resp.status_code == 200

    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT quantity, avg_cost FROM holdings WHERE code = ?", ('600002',)).fetchone()
    conn.close()
    assert row is not None
    assert row['quantity'] == 200
    assert row['avg_cost'] == 11.0


def test_delete_transaction_recalculates_holdings(client, app_module):
    create_resp = client.post('/transactions', json={
        'date': '2026-05-19',
        'code': '600001',
        'name': '测试股票',
        'category': 'A股权益',
        'account': '华泰证券',
        'direction': '买入',
        'quantity': 50,
        'price': 20,
        'amount': 1000,
        'fee': 0,
        'remark': ''
    })
    assert create_resp.status_code == 200

    txs = client.get('/transactions').json()
    tx_id = next(t['id'] for t in txs if t['code'] == '600001')

    delete_resp = client.delete(f'/transactions/{tx_id}')
    assert delete_resp.status_code == 200

    conn = sqlite3.connect(app_module.DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM holdings WHERE code = ?", ('600001',)).fetchone()[0]
    conn.close()
    assert count == 0
