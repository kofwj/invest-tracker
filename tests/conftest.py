import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

THIS_FILE = Path(__file__).resolve()
if (THIS_FILE.parents[1] / 'backend' / 'main.py').exists():
    ROOT = THIS_FILE.parents[1]
    BACKEND_MAIN = ROOT / 'backend' / 'main.py'
elif (THIS_FILE.parents[1] / 'main.py').exists():
    ROOT = THIS_FILE.parents[1]
    BACKEND_MAIN = ROOT / 'main.py'
else:
    raise RuntimeError(f'Cannot locate backend main.py from {THIS_FILE}')


def load_backend_module():
    spec = importlib.util.spec_from_file_location('backend_main_test', BACKEND_MAIN)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Failed to load module spec from {BACKEND_MAIN}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def clear_backend_module_cache():
    """Ensure split backend modules reload after each test sets DB_PATH."""
    module_names = [
        'backend_main_test',
        'database',
        'csv_utils',
        'holdings',
        'cash',
        'dashboard',
        'portfolio_totals',
        'snapshots',
        'performance',
        'routers_deposits',
        'routers_transactions',
        'routers_cash',
        'routers_cash_flows',
        'routers_securities_cash',
        'routers_fee_settings',
        'fee_settings',
        'return_sync',
        'price_sync',
        'holding_calculator',
        'routers_snapshots',
        'routers_holdings',
        'routers_dividends',
        'dividend_sync',
        'routers_dashboard',
        'routers_performance',
        'schema',
        'routers_maintenance',
        'market',
        'routers_market',
    ]
    for name in module_names:
        sys.modules.pop(name, None)


def create_tables(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            code TEXT,
            name TEXT,
            category TEXT,
            account TEXT,
            direction TEXT,
            quantity REAL DEFAULT 0,
            price REAL DEFAULT 0,
            amount REAL,
            fee REAL DEFAULT 0,
            remark TEXT
        )'''
    )
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            category TEXT,
            quantity REAL,
            avg_cost REAL,
            diluted_cost REAL,
            total_dividend REAL DEFAULT 0,
            last_price REAL,
            updated_at DATETIME,
            expected_return REAL DEFAULT 0,
            trailing_return_1y REAL,
            trailing_return_1y_source TEXT,
            trailing_return_1y_updated_at DATETIME
        )'''
    )
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT,
            amount REAL,
            interest_rate REAL,
            due_date TEXT,
            remark TEXT
        )'''
    )
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            total_assets REAL,
            cash_total REAL,
            securities_market_value REAL,
            bank_deposits_total REAL,
            annualized_return REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )'''
    )
    conn.commit()
    conn.close()


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir()
    db_path = data_dir / 'test.db'

    monkeypatch.setenv('DB_PATH', str(db_path))
    monkeypatch.setenv('BACKUP_DIR', str(backup_dir))
    monkeypatch.setenv('APP_TIMEZONE', 'Asia/Shanghai')

    clear_backend_module_cache()

    module = load_backend_module()
    create_tables(db_path)
    module.initialize_database()
    return module


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)
