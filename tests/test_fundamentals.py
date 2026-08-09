import importlib
import sys


def _load_fundamentals_with_fake_akshare(monkeypatch, fake_ak):
    """把假 akshare 模块注入 sys.modules 后加载 fundamentals，返回模块。"""
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)
    for m in list(sys.modules):
        if m == "fundamentals":
            del sys.modules[m]
    return importlib.import_module("fundamentals")


def test_fundamentals_route_registered(app_module):
    """ /analysis/{code} 应挂载在 app 上（auth 已配置则直接能用）。"""
    app = app_module.app
    found = any(getattr(r, "path", "") == "/analysis/{code}" for r in app.routes)
    assert found, "未找到 /analysis/{code} 路由"


def test_fundamental_check_degrades_when_akshare_raises(monkeypatch):
    """数据源失败时应返回 sections=[] + error，而不抛异常。"""
    class _FakeAk:
        @staticmethod
        def stock_value_em(symbol=None, **kw):
            raise RuntimeError("network down")

        @staticmethod
        def stock_financial_abstract(symbol=None, **kw):
            raise RuntimeError("network down")

    fundamentals = _load_fundamentals_with_fake_akshare(monkeypatch, _FakeAk)
    result = fundamentals.build_fundamental_check("600519")
    assert result["sections"] == []
    assert result.get("error")


def test_fundamental_check_builds_sections(monkeypatch):
    """数据源正常时按四块组装（估值/盈利），空块被丢弃。"""
    import pandas as pd

    value_df = pd.DataFrame(
        [
            {
                "数据日期": "2026-08-07",
                "当日收盘价": 1309.0,
                "总市值": 1.636632e12,
                "PE(TTM)": 19.8,
                "PE(静)": 19.9,
                "市净率": 6.04,
                "PEG值": 1.0,
                "市销率": 9.3,
                "市现率": 20.5,
            }
        ]
    )
    abs_df = pd.DataFrame(
        [
            {"选项": "盈利能力", "指标": "净资产收益率(ROE)", "20260331": 10.57},
            {"选项": "盈利能力", "指标": "毛利率", "20260331": 89.76},
            {"选项": "盈利能力", "指标": "销售净利率", "20260331": 52.22},
            {"选项": "常用指标", "指标": "归母净利润", "20260331": 2.724e10},
            {"选项": "常用指标", "指标": "营业总收入", "20260331": 5.47e10},
            {"选项": "财务风险", "指标": "资产负债率", "20260331": 12.12},
            {"选项": "财务风险", "指标": "权益乘数", "20260331": 1.21},
            {"选项": "财务风险", "指标": "流动比率", "20260331": 7.06},
            {"选项": "常用指标", "指标": "经营现金流量净额", "20260331": 1.0e10},
            {"选项": "收益质量", "指标": "经营活动净现金/归属母公司的净利润", "20260331": 1.2},
        ]
    )

    class _FakeAk:
        @staticmethod
        def stock_value_em(symbol=None, **kw):
            return value_df

        @staticmethod
        def stock_financial_abstract(symbol=None, **kw):
            return abs_df

    fundamentals = _load_fundamentals_with_fake_akshare(monkeypatch, _FakeAk)
    result = fundamentals.build_fundamental_check("600519")
    assert "取不到" not in (result.get("error") or "")
    keys = [s["key"] for s in result["sections"]]
    assert "valuation" in keys
    assert "profit" in keys
    assert "leverage" in keys
    assert "cash" in keys
    # ROE 透出
    profit = next(s for s in result["sections"] if s["key"] == "profit")
    roe = next(i for i in profit["items"] if "ROE" in i["label"])
    assert roe["value"] == 10.57


def test_fundamental_check_status_tags(monkeypatch):
    """每项带 status 判读标签；高负债/低现金触发 high/low。"""
    import pandas as pd

    # 低负债、低现金/净利、高 PE —— 用于触发不同 status
    value_df = pd.DataFrame(
        [
            {
                "数据日期": "2026-08-07",
                "当日收盘价": 10.0,
                "总市值": 3e10,
                "PE(TTM)": 45.0,
                "PE(静)": 44.0,
                "市净率": 7.0,
                "PEG值": 2.5,
                "市销率": 8.0,
                "市现率": 30.0,
            }
        ]
    )
    abs_df = pd.DataFrame(
        [
            {"选项": "盈利能力", "指标": "净资产收益率(ROE)", "20260331": 20.0},
            {"选项": "财务风险", "指标": "资产负债率", "20260331": 65.0},
            {"选项": "收益质量", "指标": "经营活动净现金/归属母公司的净利润", "20260331": 0.3},
        ]
    )

    class _FakeAk:
        @staticmethod
        def stock_value_em(symbol=None, **kw):
            return value_df

        @staticmethod
        def stock_financial_abstract(symbol=None, **kw):
            return abs_df

    fundamentals = _load_fundamentals_with_fake_akshare(monkeypatch, _FakeAk)
    result = fundamentals.build_fundamental_check("600519")
    flat = {i["label"]: i for s in result["sections"] for i in s["items"]}

    assert flat["市盈率 PE(TTM)"]["status"] == "high"  # 45 > 30
    assert flat["资产负债率"]["status"] == "high"  # 65 > 50
    assert flat["现金/净利润"]["status"] == "low"  # 0.3 < 0.6
    assert flat["净资产收益率 ROE"]["status"] == "ok"  # 20 >= 15
    # 中性数值项不给标签
    assert flat["总市值"].get("status") is None


def test_fundamental_check_sanitizes_nan(monkeypatch):
    """数据源返回 NaN（如银行不披露流动比率）不得泄到 JSON 成为非法 NaN 字面量。"""
    import json

    import pandas as pd

    value_df = pd.DataFrame(
        [{"数据日期": "2026-08-07", "当日收盘价": 5.0, "总市值": 2e12,
          "PE(TTM)": 7.7, "PE(静)": 7.5, "市净率": 0.8, "PEG值": 2.4,
          "市销率": 3.0, "市现率": 10.0}]
    )
    abs_df = pd.DataFrame(
        [
            {"选项": "盈利能力", "指标": "净资产收益率(ROE)", "20260331": 2.65},
            {"选项": "财务风险", "指标": "资产负债率", "20260331": 93.5},
            {"选项": "财务风险", "指标": "流动比率", "20260331": float("nan")},  # 银行常缺
        ]
    )

    class _FakeAk:
        @staticmethod
        def stock_value_em(symbol=None, **kw):
            return value_df

        @staticmethod
        def stock_financial_abstract(symbol=None, **kw):
            return abs_df

    fundamentals = _load_fundamentals_with_fake_akshare(monkeypatch, _FakeAk)
    result = fundamentals.build_fundamental_check("601288")
    # 前端 axios 用严格 JSON.parse；含 NaN 字面量会抛错 → 必须能标准反序列化
    json.loads(json.dumps(result, ensure_ascii=False))
    lev = next(s for s in result["sections"] if s["key"] == "leverage")
    cr = next(i for i in lev["items"] if "流动比率" in i["label"])
    assert cr["value"] is None  # NaN → None


def _load_company_extras_with_fake_akshare(monkeypatch, fake_ak):
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)
    return importlib.import_module("company_extras")


def test_company_extras_builds_profile_and_dividends(monkeypatch):
    """个股：公司简报 + 历史分红都应返回。"""
    import pandas as pd

    profile_df = pd.DataFrame([{
        "公司名称": "珠海格力电器股份有限公司", "A股简称": "格力电器",
        "所属行业": "电气机械和器材制造业", "法人代表": "董明珠",
        "成立日期": "1989-12-13", "上市日期": "1996-11-18",
        "主营业务": "空调、干衣机等家用电器。", "官方网站": "www.gree.com.cn",
        "所属市场": "深交所主板", "经营范围": "x",
    }])
    div_df = pd.DataFrame([{
        "报告期": "2025-09-30", "方案进度": "实施分配",
        "现金分红-现金分红比例描述": "10派10.00元(含税,扣税后9.00元)",
        "现金分红-股息率": 0.0245, "股权登记日": "2026-01-22",
        "除权除息日": "2026-01-23",
    }])

    class _FakeAk:
        @staticmethod
        def stock_profile_cninfo(symbol=None, **kw):
            return profile_df

        @staticmethod
        def stock_fhps_detail_em(symbol=None, **kw):
            return div_df

        @staticmethod
        def stock_main_stock_holder(stock=None, **kw):
            return pd.DataFrame([{
                "股东名称": "香港中央结算有限公司", "持股比例": None, "股本性质": "流通A股",
                "截至日期": "2026-06-23", "股东总数": "123456",
            }])

    mod = _load_company_extras_with_fake_akshare(monkeypatch, _FakeAk)
    r = mod.build_company_extras("000651")
    assert r["profile"]["name"] == "珠海格力电器股份有限公司"
    assert r["profile"]["listed"] == "1996-11-18"
    assert r["profile"]["main_biz"] == "空调、干衣机等家用电器。"
    # 前十大股东：北向资金应被识别
    assert r["profile"]["top_holders"][0]["kind"] == "north"
    assert r["profile"]["top_holders"][0]["pct"] is None  # NaN → None，非 JSON NaN
    assert r["profile"]["holder_count"] == 123456
    assert len(r["dividends"]) == 1
    d = r["dividends"][0]
    assert d["report"] == "2025-09"
    assert "10派10.00元" in d["desc"]
    assert d["yield_pct"] == 2.45  # 0.0245 -> 2.45
    assert d["ex_date"] == "2026-01-23"


def test_company_extras_degrades_for_etf(monkeypatch):
    """ETF（无财报/无公司信息）应静默返回空，不抛异常。"""
    class _FakeAk:
        @staticmethod
        def stock_profile_cninfo(symbol=None, **kw):
            raise IndexError("ETF 无公司资料")

        @staticmethod
        def stock_fhps_detail_em(symbol=None, **kw):
            raise TypeError("ETF 无分红")

    mod = _load_company_extras_with_fake_akshare(monkeypatch, _FakeAk)
    r = mod.build_company_extras("159352")
    assert r["profile"] is None
    assert r["dividends"] == []