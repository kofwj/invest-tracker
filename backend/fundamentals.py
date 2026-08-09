"""基本面体检：从 akshare 拉估值 + 财务指标，组装成 估值/盈利/杠杆/现金 四块。

按巴菲特/段永平式\"体检表\"拆——只给指标和白话提示，不给买/卖结论。
每个指标带 status 判读标签（ok 正常 / high 偏高 / low 偏低）+ 一句白话，
前端一扫就知道哪块亮灯。akshare 是 lazy import（应用启动/单测不依赖）；
任一块拉不到就返回空说明，不因网络或对象缺数据让整页挂掉。
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

# 体检报告四块的展示顺序与中文标签
SECTIONS = [
    {"key": "valuation", "label": "估值（便不便宜）"},
    {"key": "profit", "label": "盈利（赚不赚钱）"},
    {"key": "leverage", "label": "杠杆（风险高不高）"},
    {"key": "cash", "label": "现金（钱真不真）"},
]


def _num(v):
    """稳健转 float；空 / '--' / 非数 / 非有限值返回 None。"""
    if v is None:
        return None
    try:
        n = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n):
        return None
    return n


def _latest_report_col(columns):
    """financial_abstract 宽表里，第 3 列起是历史报告期（最早在前→最新在后？实测最新在最左）。
    取最新一期的列名（第 3 个列名）。"""
    if len(columns) < 3:
        return None
    # 实测列序为 最新报告期在前（20260331, 20251231, 20250930…）
    return columns[2]


def _pick_metric(df, section, metric):
    """在 financial_abstract 里按 (选项, 指标) 找一行，返回最新一期数值。"""
    if df is None or df.empty:
        return None
    try:
        row = df.loc[(df["选项"] == section) & (df["指标"] == metric)]
        if row.empty:
            return None
        col = _latest_report_col(list(df.columns))
        if not col or col not in row.columns:
            return None
        return _num(row.iloc[0][col])
    except Exception as exc:
        logger.debug("pick_metric(%s/%s) failed: %s", section, metric, exc)
        return None


def _pct(v):
    if v is None:
        return None
    return round(v, 2)


# ---- 判读标签 ----
# status: "ok" 正常 / "high" 偏高(红) / "low" 偏低(黄)；None 不给标签(中性数值项)。
def _mk(label, value, status=None, note=None):
    return {"label": label, "value": value, "status": status, "note": note}


def _judge_pe(pe):
    if pe is None:
        return None, None
    if pe <= 0:
        return "high", "负 PE = 近一年亏钱，先看亏在哪"
    if pe <= 15:
        return "ok", "15 以内相对不贵（还要结合行业看）"
    if pe <= 30:
        return "ok", "十几到三十，中性区间"
    return "high", "超过 30 偏贵（高成长股除外）"


def _judge_pb(pb):
    if pb is None:
        return None, None
    if pb < 1:
        return "low", "跌破净资产，先看资产质量（银行/地产另算）"
    if pb <= 5:
        return "ok", "净值的一到五倍，中性"
    return "high", "超过净值 5 倍偏贵（轻资产高 ROE 的除外）"


def _judge_ps(ps):
    if ps is None:
        return None, None
    if ps <= 1:
        return "ok", "营收一倍以内，相对便宜"
    if ps <= 5:
        return "ok", "一到五倍，中性"
    return "high", "超过营收 5 倍偏贵（成长/互联网另说）"


def _judge_peg(peg):
    if peg is None:
        return None, None
    if peg < 0:
        return None, "负 PEG：利润在缩或刚亏过，参考意义弱"
    if peg < 1:
        return "ok", "成长相对便宜"
    if peg < 2:
        return "ok", "成长价合理"
    return "high", "成长价不便宜"


def _judge_roe(roe):
    if roe is None:
        return None, None
    if roe <= 0:
        return "high", "股东钱在亏，难以为继"
    if roe >= 15:
        return "ok", "股东钱回报率高，段永平式的优等生"
    if roe >= 10:
        return "ok", "回报不错"
    return "low", "回报一般，长期上不去要警惕"


def _judge_gm(gm):
    if gm is None:
        return None, None
    if gm >= 40:
        return "ok", "毛利厚，有『墙』（护城河）"
    if gm >= 20:
        return "ok", "正常水平"
    return "low", "毛利薄，行业竞争激烈"


def _judge_nm(nm):
    if nm is None:
        return None, None
    if nm <= 0:
        return "high", "净利率为负，在亏钱"
    if nm >= 20:
        return "ok", "很能赚"
    if nm >= 10:
        return "ok", "不错"
    return "low", "偏薄"


def _judge_dar(dar):
    if dar is None:
        return None, None
    if dar <= 30:
        return "ok", "负债低，稳"
    if dar <= 50:
        return "ok", "正常范围"
    return "high", "负债偏高（金融/地产本来就高，另看）"


def _judge_em(em):
    """权益乘数 = 总资产/净资产，越大杠杆越高。"""
    if em is None:
        return None, None
    if em <= 2:
        return "ok", "杠杆低"
    if em <= 3.3:
        return "ok", "正常（约对应负债率 50% 内）"
    return "high", "杠杆高（约对应负债率 70% 以上）"


def _judge_cr(cr):
    if cr is None:
        return None, None
    if cr >= 2:
        return "ok", "短期偿债充裕"
    if cr >= 1:
        return "ok", "够用"
    return "high", "不到 1，短期偿债偏紧"


def _judge_cf(cf):
    """现金/净利润：赚的钱真到账没。"""
    if cf is None:
        return None, None
    if cf >= 1:
        return "ok", "利润是真钱，真到账"
    if cf >= 0.6:
        return "ok", "基本合格"
    return "low", "利润多是纸面（压货/应收），查账"


def _fetch_value(code):
    import akshare as ak

    df = ak.stock_value_em(symbol=code)
    if df is None or df.empty:
        return None
    row = df.iloc[-1]  # 最新一行
    return {
        "pe_ttm": _num(row.get("PE(TTM)")),
        "pe_static": _num(row.get("PE(静)")),
        "pb": _num(row.get("市净率")),
        "peg": _num(row.get("PEG值")),
        "ps": _num(row.get("市销率")),
        "pcf": _num(row.get("市现率")),
        "market_cap": _num(row.get("总市值")),
    }


def _fetch_abstract(code):
    import akshare as ak

    df = ak.stock_financial_abstract(symbol=code)
    return df if (df is not None and not df.empty) else None


def build_fundamental_check(code: str) -> dict:
    """返回 {code, sections: [{key,label,items:[{label,value,status,note}]}], error?}。"""

    out = {"code": str(code or "").strip(), "sections": [], "source_time": None}
    c = str(code or "").strip().lower()

    value = None
    abs_df = None
    try:
        value = _fetch_value(c)
    except Exception as exc:
        logger.info("估值获取失败 %s: %s", c, exc)
    try:
        abs_df = _fetch_abstract(c)
    except Exception as exc:
        logger.info("财务摘要获取失败 %s: %s", c, exc)

    if not value and abs_df is None:
        out["error"] = "取不到数据（可能是 ETF/指数或数据源暂不可用）"
        return out

    # ---- 估值（便不便宜）----
    val_items = []
    if value:
        st, note = _judge_pe(value["pe_ttm"])
        val_items.append(_mk("市盈率 PE(TTM)", round(value["pe_ttm"], 1) if value["pe_ttm"] is not None else None, st, note))
        st, note = _judge_pb(value["pb"])
        val_items.append(_mk("市净率 PB", value["pb"], st, note))
        st, note = _judge_ps(value["ps"])
        val_items.append(_mk("市销率 PS", value["ps"], st, note))
        st, note = _judge_peg(value["peg"])
        val_items.append(_mk("PEG", value["peg"], st, note))
        if value["market_cap"]:
            val_items.append(_mk("总市值", round(value["market_cap"] / 1e8, 0), None, "亿元"))
    out["sections"].append({"key": "valuation", "label": "估值（便不便宜）", "items": val_items})

    # ---- 盈利（赚不赚钱）----
    profit_items = []
    roe = _pick_metric(abs_df, "盈利能力", "净资产收益率(ROE)")
    gm = _pick_metric(abs_df, "盈利能力", "毛利率")
    nm = _pick_metric(abs_df, "盈利能力", "销售净利率")
    ngm = _pick_metric(abs_df, "常用指标", "归母净利润")
    rev = _pick_metric(abs_df, "常用指标", "营业总收入")
    st, note = _judge_roe(roe)
    profit_items.append(_mk("净资产收益率 ROE", _pct(roe), st, note))
    st, note = _judge_gm(gm)
    profit_items.append(_mk("毛利率", _pct(gm), st, note))
    st, note = _judge_nm(nm)
    profit_items.append(_mk("销售净利率", _pct(nm), st, note))
    if ngm is not None:
        profit_items.append(_mk("归母净利润", round(ngm / 1e8, 1), None, "亿元（最近报告期）"))
    if rev is not None:
        profit_items.append(_mk("营业总收入", round(rev / 1e8, 1), None, "亿元（最近报告期）"))
    out["sections"].append({"key": "profit", "label": "盈利（赚不赚钱）", "items": profit_items})

    # ---- 杠杆（风险高不高）----
    lev_items = []
    dar = _pick_metric(abs_df, "财务风险", "资产负债率")
    em = _pick_metric(abs_df, "财务风险", "权益乘数")
    cr = _pick_metric(abs_df, "财务风险", "流动比率")
    st, note = _judge_dar(dar)
    lev_items.append(_mk("资产负债率", _pct(dar), st, note))
    st, note = _judge_em(em)
    lev_items.append(_mk("权益乘数", em, st, note))
    st, note = _judge_cr(cr)
    lev_items.append(_mk("流动比率", cr, st, note))
    out["sections"].append({"key": "leverage", "label": "杠杆（风险高不高）", "items": lev_items})

    # ---- 现金（钱真不真）----
    cash_items = []
    ocf = _pick_metric(abs_df, "常用指标", "经营现金流量净额")
    cf = _pick_metric(abs_df, "收益质量", "经营活动净现金/归属母公司的净利润")
    pcf = _pick_metric(abs_df, "每股指标", "每股经营现金流")
    if ocf is not None:
        cash_items.append(_mk("经营现金流净额", round(ocf / 1e8, 1), None, "亿元（最近报告期）"))
    st, note = _judge_cf(cf)
    cash_items.append(_mk("现金/净利润", cf, st, note))
    if pcf is not None:
        cash_items.append(_mk("每股经营现金流", pcf))
    out["sections"].append({"key": "cash", "label": "现金（钱真不真）", "items": cash_items})

    # 去掉空块，避免前端一堆空卡片
    out["sections"] = [s for s in out["sections"] if s["items"]]
    return out