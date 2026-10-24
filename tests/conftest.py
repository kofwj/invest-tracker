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

# 让 tests/ 里那几个直接 import 后端模块的文件（import dividend_sync / market / ...）
# 在两条路径下都能跑：
#   - `make test-local` → PYTHONPATH=backend python3 -m pytest -q tests
#   - 容器内 `pytest -q /app/tests` → 没有 PYTHONPATH，而且 pytest 控制台脚本只会把
#     测试文件所在目录塞进 sys.path，不会塞 cwd，于是那 8 个文件全是 collection error。
# 在这里兜底最稳：不管从哪条路进，后端目录都在 sys.path 上。
BACKEND_DIR = BACKEND_MAIN.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


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
        'discipline',
        'routers_discipline',
        'allocation_analysis',
        'routers_allocation',
        'trading_calendar',
        'broker_reconcile',
        'routers_broker_reconcile',
        'portfolio_helpers',
        'total_asset_calibration',
        'notify',
        'routers_notify',
        'routers_cron',
        'kline_cache',
        'routers_klines',
        'ai_client',
        'routers_ai',
        'ai_payload',
        'ai_brief',
        'reason_sources',
        'reason_cache',
        'ai_profile',
        'ai_entry',
        'ai_alert',
        'ai_weekly',
        'ai_nl_rule',
        'ai_usage',
        'ai_notice',
        'dividend_calendar',
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


def rebind_test_module_refs():
    """把测试模块里指向"已被重载掉的旧后端模块"的全局名字改指到新模块。

    app_module 每次都会把 60 个后端模块从 sys.modules 弹掉再重新加载；但测试文件在
    收集阶段就执行了 `from market import foo`，绑定的是旧模块里的那份对象。之后
    `patch("market.foo")` 打在重载后的新模块上，测试调的却还是旧模块里的函数 ——
    patch 静默落空（call_count 恒为 0），测试要么退化成恒真，要么悄悄读真实系统时间。
    重载完成后把名字改指到新模块，patch 语义才恢复正常。
    """
    import types

    for mod_name, test_mod in list(sys.modules.items()):
        if not (mod_name.startswith('test_') or mod_name.startswith('tests.')):
            continue
        for attr, value in list(vars(test_mod).items()):
            if isinstance(value, types.ModuleType):
                fresh = sys.modules.get(value.__name__)
                if fresh is not None and fresh is not value:
                    setattr(test_mod, attr, fresh)
                continue
            owner = getattr(value, '__module__', None)
            if not owner:
                continue
            fresh_mod = sys.modules.get(owner)
            if fresh_mod is None:
                continue
            candidate = getattr(fresh_mod, attr, None)
            # 只认同名且限定名一致的对象，避免把别的东西误绑过来
            if candidate is not None and getattr(candidate, '__qualname__', None) == getattr(
                value, '__qualname__', None
            ):
                setattr(test_mod, attr, candidate)


def boot_app(tmp_path, monkeypatch, *, extra_env=None):
    """按测试约定拉起一份后端：独立 data/backups + 显式 DB_PATH，然后重载模块。

    ``FRONTEND_DIST`` 默认指向一个不存在的目录，让测试跑「纯 API」形态
    （和 CI 一致）；要验证单进程托管前端时由调用方传真实 dist 进来。
    """
    data_dir = tmp_path / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / 'test.db'

    monkeypatch.setenv('DB_PATH', str(db_path))
    monkeypatch.setenv('BACKUP_DIR', str(backup_dir))
    monkeypatch.setenv('APP_TIMEZONE', 'Asia/Shanghai')
    monkeypatch.setenv('FRONTEND_DIST', str(tmp_path / 'no-frontend-dist'))
    for key, value in (extra_env or {}).items():
        monkeypatch.setenv(key, value)

    clear_backend_module_cache()

    module = load_backend_module()
    rebind_test_module_refs()
    create_tables(db_path)
    module.initialize_database()
    return module


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    return boot_app(tmp_path, monkeypatch)


@pytest.fixture
def spa_app(tmp_path, monkeypatch):
    """单进程形态：临时 dist 里有 index.html / assets，验证静态托管与 SPA 回落。"""
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<!doctype html><title>spa-index</title>', encoding='utf-8')
    (dist / 'assets' / 'app.js').write_text('console.log("spa-asset")', encoding='utf-8')
    return boot_app(tmp_path, monkeypatch, extra_env={'FRONTEND_DIST': str(dist)})


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)
