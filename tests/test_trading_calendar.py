"""交易日历自检：硬编码节假日表过期后会静默退化，这里把它钉住。

``BUILTIN_CLOSED_DAYS`` 越过最后一年之后不抛错，只让春节、国庆这些休市日重新
算成「交易日」；cron 于是在假期照常生成快照，净值曲线多出几个和前一天一模一
样的点。``calendar_staleness()`` 就是把这个失效点显式化 —— 下面这些测试保证
它该报的时候一定报、不该吵的时候别吵。

断言里的年份一律从 ``calendar_coverage_years()`` 推出来，不写死 —— 补表之后
这些测试仍然成立，不需要跟着改。
"""
from datetime import date, timedelta

from trading_calendar import (
    BUILTIN_CLOSED_DAYS,
    calendar_coverage_years,
    calendar_staleness,
    is_a_share_trading_day,
    trading_day_status,
)


def _last_year() -> int:
    return calendar_coverage_years()[-1]


def _first_weekday(year: int) -> date:
    """该年第一个工作日，用来构造「表外但看着很正常」的日期。"""
    day = date(year, 1, 1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def test_coverage_years_are_sorted_and_contiguous():
    years = calendar_coverage_years()

    assert years == sorted(years)
    # 中间缺一年会让 stale/expiring 的判断错位，连续性不是可有可无的洁癖
    assert years == list(range(years[0], years[-1] + 1))


def test_last_covered_year_is_expiring_not_stale():
    last = _last_year()

    info = calendar_staleness(date(last, 6, 3))

    assert info["stale"] is False
    assert info["expiring"] is True
    assert info["years_remaining"] == 0
    assert str(last) in info["message"]


def test_year_past_coverage_is_stale():
    last = _last_year()

    info = calendar_staleness(date(last + 1, 6, 3))

    assert info["stale"] is True
    assert info["expiring"] is False
    assert info["years_remaining"] == -1
    assert str(last) in info["message"]
    assert str(last + 1) in info["message"]


def test_year_before_last_coverage_is_quiet():
    last = _last_year()

    info = calendar_staleness(date(last - 1, 6, 3))

    assert info["stale"] is False
    assert info["expiring"] is False
    assert info["message"] == ""


def test_empty_table_is_reported_as_stale(monkeypatch):
    """表被清空是最坏情况：每个工作日都会被当成交易日。"""
    monkeypatch.setattr("trading_calendar.BUILTIN_CLOSED_DAYS", set())

    info = calendar_staleness(date(2026, 6, 3))

    assert info["stale"] is True
    assert info["covered_years"] == []
    assert info["last_covered_year"] is None
    assert info["years_remaining"] is None
    assert info["message"]


def test_expired_calendar_quietly_treats_holidays_as_trading_days():
    """表过期后最危险的形态：判定看起来正常，其实已经错了。

    这里不写死具体节日（表一更新就漂），只钉住机制 —— 表外年份的工作日会被
    判成交易日，同时 calendar_staleness 必须报 stale。两者同时成立，才说明
    「静默退化」确实被监控到了，而不是判定错了还没人知道。
    """
    last = _last_year()
    day = _first_weekday(last + 1)

    assert is_a_share_trading_day(day) is True
    assert calendar_staleness(day)["stale"] is True


def test_trading_day_status_carries_calendar_flags():
    """cron 每天调这个接口，日历状态必须跟着回去，否则日志里看不到。"""
    last = _last_year()

    fresh = trading_day_status(date(last - 1, 6, 3).isoformat())
    assert fresh["calendar_stale"] is False
    assert fresh["calendar_expiring"] is False
    assert fresh["calendar_note"] == ""

    expiring = trading_day_status(date(last, 6, 3).isoformat())
    assert expiring["calendar_stale"] is False
    assert expiring["calendar_expiring"] is True
    assert expiring["calendar_note"]

    stale = trading_day_status(date(last + 1, 6, 3).isoformat())
    assert stale["calendar_stale"] is True
    assert stale["calendar_note"]


def test_staleness_is_recomputed_not_cached(monkeypatch):
    """补表之后必须立刻反映；缓存住会让「已经修好」和「还没修」看起来一样。"""
    before = calendar_staleness(date(2030, 6, 3))
    assert before["stale"] is True

    monkeypatch.setattr(
        "trading_calendar.BUILTIN_CLOSED_DAYS",
        set(BUILTIN_CLOSED_DAYS) | {"2030-01-01"},
    )

    after = calendar_staleness(date(2030, 6, 3))
    assert after["stale"] is False
    assert 2030 in after["covered_years"]
