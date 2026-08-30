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


def test_import_oversized_csv_rejected_413(client, monkeypatch):
    """超大 CSV 上传必须被 413 拒绝（防内存 DoS 的大小上限）。"""

    import csv_utils  # top-level module copy loaded by conftest

    monkeypatch.setattr(csv_utils, "MAX_CSV_UPLOAD_BYTES", 1024)  # 1KB 上限便于测试
    big_csv = (
        'date,account,code,name,category,direction,quantity,price,amount,fee,remark\n'
        + ('2026-05-19,华泰证券,600000,浦发银行,A股权益,买入,100,10,1000,5,x\n' * 500)
    ).encode('utf-8')
    assert len(big_csv) > 1024

    resp = client.post(
        '/transactions/import',
        files={'file': ('big.csv', big_csv, 'text/csv')}
    )
    assert resp.status_code == 413
    assert '超过大小限制' in resp.json()['detail']


def test_csv_export_sanitizes_formula_cells(client):
    """导出 CSV 时，以 = + - @ 开头的文本必须加单引号前缀防公式注入。"""
    import csv
    import io

    # 先写入一条 name 以 = 开头的交易
    client.post('/transactions', json={
        'date': '2026-05-19', 'code': '600001', 'name': '=HYPERLINK("http://evil","x")',
        'category': 'A股权益', 'account': '华泰证券', 'direction': '买入',
        'quantity': 100, 'price': 10, 'amount': 1000, 'fee': 0, 'remark': '',
    })
    resp = client.get('/transactions/export')
    assert resp.status_code == 200
    content = resp.content.decode('utf-8-sig')
    rows = list(csv.reader(io.StringIO(content)))
    names = [r[3] for r in rows[1:]]
    assert all(not n.startswith('=') and n.startswith("'=") for n in names)
