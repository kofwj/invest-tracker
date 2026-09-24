import ast
import inspect
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from reason_sources import (
    _with_deadline,
    fetch_global_news,
    fetch_intraday_moves,
    fetch_notices,
    fetch_stock_news,
    notice_lookback_days,
)


def _df(rows, columns):
    return pd.DataFrame(rows, columns=columns)


def test_fetch_stock_news_parses_dataframe():
    df = _df(
        [["000651", "格力电器发布新闻", "正文", "2026-09-24 10:00:00", "东财", "http://x"]],
        ["代码", "新闻标题", "新闻内容", "发布时间", "文章来源", "新闻链接"],
    )
    fake = MagicMock()
    fake.stock_news_em.return_value = df
    with patch.dict(sys.modules, {"akshare": fake}):
        items = fetch_stock_news("000651")
    assert items and items[0]["title"] == "格力电器发布新闻"
    assert items[0]["kind"] == "news"
    assert items[0]["code"] == "000651"


def test_akshare_exception_returns_empty():
    fake = MagicMock()
    fake.stock_news_em.side_effect = RuntimeError("boom")
    fake.stock_notice_report.side_effect = RuntimeError("boom")
    fake.stock_info_global_cls.side_effect = RuntimeError("boom")
    fake.stock_changes_em.side_effect = RuntimeError("boom")
    with patch.dict(sys.modules, {"akshare": fake}):
        assert fetch_stock_news("000651") == []
        assert fetch_notices("2026-09-24") is None
        assert fetch_global_news("2026-09-24") is None
        assert fetch_intraday_moves(["大笔卖出"], "2026-09-24") is None


def test_none_or_empty_dataframe_returns_empty():
    fake = MagicMock()
    fake.stock_news_em.return_value = None
    with patch.dict(sys.modules, {"akshare": fake}):
        assert fetch_stock_news("000651") == []
    fake.stock_news_em.return_value = pd.DataFrame()
    with patch.dict(sys.modules, {"akshare": fake}):
        assert fetch_stock_news("000651") == []


def test_missing_column_falls_back_to_position():
    df = _df(
        [["000651", "标题在第二列", "正文", "2026-09-24", "源", "u"]],
        ["col0", "col1", "col2", "发布时间", "col4", "col5"],
    )
    fake = MagicMock()
    fake.stock_news_em.return_value = df
    with patch.dict(sys.modules, {"akshare": fake}):
        items = fetch_stock_news("651")
    assert items
    assert items[0]["title"] == "标题在第二列"


def test_all_columns_renamed_returns_empty():
    df = _df([["a", "b", "c"]], ["foo", "bar", "baz"])
    fake = MagicMock()
    fake.stock_news_em.return_value = df
    with patch.dict(sys.modules, {"akshare": fake}):
        assert fetch_stock_news("000651") == []


def test_with_deadline_timeout_returns_default():
    def slow():
        time.sleep(1)
        return "nope"

    result = _with_deadline(slow, deadline_s=0.05, default=[])
    assert result == []


def test_fetchers_never_raise():
    fake = MagicMock()
    fake.stock_news_em.return_value = None
    fake.stock_notice_report.return_value = None
    fake.stock_info_global_cls.return_value = None
    fake.stock_changes_em.return_value = None
    with patch.dict(sys.modules, {"akshare": fake}):
        assert fetch_stock_news("000651") == []
        assert fetch_notices("2026-09-24") is None
        assert fetch_global_news("2026-09-24") is None
        assert fetch_intraday_moves(["火箭发射"], "2026-09-24") is None


def test_lazy_import_akshare():
    path = Path(inspect.getfile(sys.modules["reason_sources"]))
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(alias.name != "akshare" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "akshare"
    assert "import akshare" in src


def test_fetch_notices_passes_yyyymmdd_to_akshare():
    fake = MagicMock()
    fake.stock_notice_report.return_value = pd.DataFrame()
    with patch.dict(sys.modules, {"akshare": fake}):
        fetch_notices("2026-09-24")
    dates = []
    for call in fake.stock_notice_report.call_args_list:
        args, kwargs = call
        date_arg = kwargs.get("date") if kwargs else None
        if date_arg is None and args:
            date_arg = args[0]
        dates.append(date_arg)
    assert dates == ["20260922", "20260923", "20260924"]
    assert all(isinstance(d, str) and len(d) == 8 and d.isdigit() for d in dates)


def test_global_news_combines_date_and_time():
    import datetime as dt

    df = _df(
        [["标题A", "正文", dt.time(9, 30, 0), dt.date(2026, 9, 24)]],
        ["标题", "内容", "发布时间", "发布日期"],
    )
    fake = MagicMock()
    fake.stock_info_global_cls.return_value = df
    with patch.dict(sys.modules, {"akshare": fake}):
        items = fetch_global_news("2026-09-24")
    assert items
    assert items[0]["published_at"] == "2026-09-24 09:30:00"


def test_notice_lookback_days_covers_three_days():
    assert notice_lookback_days("2026-09-24") == ["20260922", "20260923", "20260924"]
    assert notice_lookback_days("20260924", lookback_days=1) == ["20260924"]


def test_fetch_notices_keeps_partial_when_one_day_times_out():
    import reason_sources as rs

    def impl(day):
        if day == "20260923":
            time.sleep(0.2)
            return [{
                "code": "000001", "title": "slow", "kind": "notice",
                "date": "2026-09-23", "name": "", "notice_type": "", "url": "",
            }]
        return [{
            "code": "000001", "title": day, "kind": "notice",
            "date": rs.iso_day(day), "name": "", "notice_type": "", "url": "",
        }]

    with patch.object(rs, "_fetch_notices_impl", side_effect=impl), \
         patch.object(rs, "NOTICE_DEADLINE_S", 0.05):
        items = rs.fetch_notices("2026-09-24")
    assert items is not None
    titles = {row["title"] for row in items}
    assert "20260922" in titles
    assert "20260924" in titles
    assert "slow" not in titles


def test_intraday_empty_df_is_success():
    fake = MagicMock()
    fake.stock_changes_em.return_value = pd.DataFrame()
    with patch.dict(sys.modules, {"akshare": fake}):
        assert fetch_intraday_moves(["大笔卖出"], "2026-09-24") == []


def test_intraday_renamed_columns_is_failure():
    fake = MagicMock()
    fake.stock_changes_em.return_value = pd.DataFrame([["a", "b"]], columns=["foo", "bar"])
    with patch.dict(sys.modules, {"akshare": fake}):
        assert fetch_intraday_moves(["大笔卖出"], "2026-09-24") is None



def test_fetch_notices_stops_when_total_budget_exceeded():
    import reason_sources as rs

    seen = []

    def impl(day):
        seen.append(day)
        time.sleep(0.12)
        return [{
            "code": "000001", "title": day, "kind": "notice",
            "date": rs.iso_day(day), "name": "", "notice_type": "", "url": "",
        }]

    with patch.object(rs, "_fetch_notices_impl", side_effect=impl), \
         patch.object(rs, "NOTICE_DEADLINE_S", 1.0), \
         patch.object(rs, "NOTICE_TOTAL_BUDGET_S", 0.08):
        items = rs.fetch_notices("2026-09-24")
    assert items is not None
    assert seen == ["20260922"]
    assert items[0]["title"] == "20260922"

