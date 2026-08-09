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