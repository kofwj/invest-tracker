def test_import_empty_csv_returns_clear_error(client):
    resp = client.post(
        '/transactions/import',
        files={'file': ('empty.csv', b'', 'text/csv')}
    )
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'CSV为空'


def test_import_bad_csv_reports_row_error(client):
    bad_csv = (
        'date,account,code,name,category,direction,quantity,price,amount,fee,remark\n'
        '2026-05-19,华泰证券,600000,浦发银行,A股权益,乱写,100,10,1000,5,bad direction\n'
    ).encode('utf-8')

    resp = client.post(
        '/transactions/import',
        files={'file': ('bad.csv', bad_csv, 'text/csv')}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data['imported'] == 0
    assert data['failed'] == 1
    assert data['errors'][0]['row'] == 2
    assert '方向必须是' in data['errors'][0]['error']
