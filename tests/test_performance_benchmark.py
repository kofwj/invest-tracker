"""基准指数取数：代码 → sh/sz 前缀必须按 secid 来，不能按"非 5/6/9 开头=深市"猜。

背景（真实故障）：收益分析页的三个基准走 `kline_cache` 的腾讯日K，
`_market_prefix` 只把 5/6/9 开头当沪市，于是
  · 000300（沪深300）→ sz000300 取不到 → 该基准整条消失；
  · 000012（上证国债指数）→ sz000012 = 南玻A → **基准数字静默变成一只股票的走势**；
  · 511880（货币ETF）本来就是沪市，碰巧对 → 所以只有它一直是对的。

修法：`fetch_tencent_kline_ohlc(..., symbol=...)` 显式给 sh/sz，基准表里存 secid（唯一真相）。
"""
import inspect

import pytest

TIMELINE = [
    {"date": "2026-09-24", "total_assets": 100000},
    {"date": "2026-09-25", "total_assets": 103000},
]


def _two_rows():
    return [
        {"date": "2026-09-24", "open": 100.0, "close": 100.0, "high": 101.0, "low": 99.0, "volume": 1.0, "amount": 1.0},
        {"date": "2026-09-25", "open": 100.0, "close": 110.0, "high": 111.0, "low": 99.0, "volume": 1.0, "amount": 1.0},
    ]


def test_bench_call_sites_pass_explicit_exchange_prefix(monkeypatch):
    """三个基准都要带上正确的 sh/sz 前缀（修前只有货币ETF 是对的）。"""
    import kline_cache
    from performance import build_benchmark_relative

    seen = {}

    def fake_fetch(code, count=420, symbol=None):
        seen[code] = symbol
        return _two_rows()

    monkeypatch.setattr(kline_cache, "fetch_tencent_kline_ohlc", fake_fetch)
    out = build_benchmark_relative(TIMELINE)

    assert seen == {"000300": "sh000300", "000012": "sh000012", "511880": "sh511880"}
    assert set(out) == {"hs300", "bond", "cash"}
    assert out["hs300"]["name"] == "沪深300"
    assert out["bond"]["name"] == "上证国债"
    assert out["hs300"]["bench_ret"] == pytest.approx(10.0)
    assert out["hs300"]["port_ret"] == pytest.approx(3.0)
    assert out["hs300"]["relative"] == pytest.approx(-7.0)


def test_benchmark_table_keeps_secids_not_bare_codes():
    """防回归：基准表里必须留着 secid（唯一真相），不许退回只有代码的二元组。"""
    from performance import build_benchmark_relative
    from price_sync import symbol_from_secid

    src = inspect.getsource(build_benchmark_relative)
    assert '"000300", "1.000300"' in src
    assert '"000012", "1.000012"' in src
    assert '"511880", "1.511880"' in src
    assert symbol_from_secid("1.000300") == "sh000300"
    assert symbol_from_secid("1.000012") == "sh000012"
    assert symbol_from_secid("1.511880") == "sh511880"


def test_kline_fetch_honours_explicit_symbol(monkeypatch):
    """`symbol=` 必须覆盖猜前缀：给 sh000300 就不能请求 sz000300。"""
    import kline_cache

    urls = []

    def fake_urlopen(req, timeout=0):
        urls.append(req.full_url)

        class _Resp:
            def read(self_inner):
                return b'{"data": {"sh000300": {"day": [["2026-09-25","1","2","3","0.5","9"]]}}}'

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        return _Resp()

    monkeypatch.setattr(kline_cache.urllib.request, "urlopen", fake_urlopen)
    rows = kline_cache.fetch_tencent_kline_ohlc("000300", count=1, symbol="sh000300")

    assert "param=sh000300,day" in urls[0]
    assert "sz000300" not in urls[0]
    assert rows and rows[0]["date"] == "2026-09-25"
