import time

import dividend_sync as ds


def test_eastmoney_fetch_uses_ttl_cache(monkeypatch):
    ds.clear_dividend_http_cache()
    calls = {"n": 0}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"result": {"data": [{"SECURITY_CODE": "000651", "PRETAX_BONUS_RMB": 10}]}}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(ds._HTTP_SESSION, "get", fake_get)
    a = ds.fetch_eastmoney_share_bonus("000651")
    b = ds.fetch_eastmoney_share_bonus("000651")
    assert a == b
    assert calls["n"] == 1


def test_sina_fetch_uses_ttl_cache(monkeypatch):
    ds.clear_dividend_http_cache()
    calls = {"n": 0}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": {
                    "status": {"code": 0},
                    "data": {
                        "fhdata": [
                            {"djr": "2026-01-10", "fhr": "2026-01-12", "mffh": "0.05"},
                        ]
                    },
                }
            }

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(ds._HTTP_SESSION, "get", fake_get)
    a = ds.fetch_sina_fund_dividends("513530")
    b = ds.fetch_sina_fund_dividends("513530")
    assert len(a) == 1
    assert a == b
    assert calls["n"] == 1
