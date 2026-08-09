"""基本面体检：从 akshare 拉估值 + 财务指标，组装成 估值/盈利/杠杆/现金 四块。

按巴菲特/段永平式"体检表"拆——只给指标和白话提示，不给买/卖结论。
akshare 是 lazy import（应用启动/单测不依赖）；任一块拉不到就返回空说明，
不因网络或对象缺数据让整页挂掉。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 体检报告四块的展示顺序与中文标签
SECTIONS = [
    {"key": "valuation", "label": "估值（便不便宜）"},
    {"key": "profit", "label": "盈利（赚不赚钱）"},
    {"key": "leverage", "label": "杠杆（风险高不高）"},
    {"key": "cash", "label": "现金（钱真不真）"},
]


def _num(v):
    """稳健转 float；空 / '--' / 非数返回 None。"""
    if v is None:
        return None
    try:
        n = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
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
    """返回 {code, sections: [{key,label,items:[{label,value,note}]}], error?}。"""

    def _value_item(label, v, fmt="num"):
        if v is None:
            return {"label": label, "value": None}
        if fmt == "pct":
            return {"label": label, "value": round(v, 2)}
        return {"label": label, "value": v}

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

    # ---- 估值 ----
    val_items = []
    if value:
        pe = value["pe_ttm"]
        note = None
        if pe is not None:
            if pe > 0:
                note = "每年把这数换成一年利润要花多少年；太高通常偏贵，具体结合行业看"
            else:
                note = "负 PE = 近一年亏钱，先看亏在哪"
        val_items.append({"label": "市盈率 PE(TTM)", "value": round(pe, 1) if pe is not None else None, "note": note})
        val_items.append({
            "label": "市净率 PB", "value": value["pb"],
            "note": "股价是净资产的几倍；低不一定便宜，看资产质量" if value["pb"] is not None else None,
        })
        if value["ps"] is not None:
            val_items.append({"label": "市销率 PS", "value": value["ps"], "note": "股价是每年营收的几倍"})
        if value["peg"] is not None:
            val_items.append({"label": "PEG", "value": value["peg"], "note": "<1 常被认为成长相对便宜" if value["peg"] is not None and 0 <= value["peg"] < 1 else None})
        if value["market_cap"]:
            val_items.append({"label": "总市值", "value": round(value["market_cap"] / 1e8, 0), "note": "亿元"})
    out["sections"].append({"key": "valuation", "label": "估值（便不便宜）", "items": val_items})

    # ---- 盈利 ----
    profit_items = []
    roe = _pick_metric(abs_df, "盈利能力", "净资产收益率(ROE)")
    gm = _pick_metric(abs_df, "盈利能力", "毛利率")
    nm = _pick_metric(abs_df, "盈利能力", "销售净利率")
    ngm = _pick_metric(abs_df, "常用指标", "归母净利润")
    rev = _pick_metric(abs_df, "常用指标", "营业总收入")
    if roe is not None:
        profit_items.append({"label": "净资产收益率 ROE", "value": _pct(roe), "note": "股东钱的回报率，段永平最看重；长期稳在 10%+ 才算会赚钱"})
    if gm is not None:
        profit_items.append({"label": "毛利率", "value": _pct(gm), "note": "收入扣成本还留多少；高且稳一般说明有『墙』"})
    if nm is not None:
        profit_items.append({"label": "销售净利率", "value": _pct(nm)})
    if ngm is not None:
        profit_items.append({"label": "归母净利润", "value": round(ngm / 1e8, 1), "note": "亿元（最近报告期）"})
    if rev is not None:
        profit_items.append({"label": "营业总收入", "value": round(rev / 1e8, 1), "note": "亿元（最近报告期）"})
    out["sections"].append({"key": "profit", "label": "盈利（赚不赚钱）", "items": profit_items})

    # ---- 杠杆 ----
    lev_items = []
    dar = _pick_metric(abs_df, "财务风险", "资产负债率")
    em = _pick_metric(abs_df, "财务风险", "权益乘数")
    cr = _pick_metric(abs_df, "财务风险", "流动比率")
    if dar is not None:
        note = "借的钱占资产多少；越低越稳，高负债的利润要打个问号" if dar is not None else None
        lev_items.append({"label": "资产负债率", "value": _pct(dar), "note": note})
    if em is not None:
        lev_items.append({"label": "权益乘数", "value": em, "note": "总资产是净资产的几倍；越大杠杆越高"})
    if cr is not None:
        lev_items.append({"label": "流动比率", "value": cr, "note": "短期要还的钱能不能用流动资产顶上；<1 偏紧"})
    out["sections"].append({"key": "leverage", "label": "杠杆（风险高不高）", "items": lev_items})

    # ---- 现金 / 收益质量 ----
    cash_items = []
    ocf = _pick_metric(abs_df, "常用指标", "经营现金流量净额")
    cf = _pick_metric(abs_df, "收益质量", "经营活动净现金/归属母公司的净利润")
    pcf = _pick_metric(abs_df, "每股指标", "每股经营现金流")
    if ocf is not None:
        cash_items.append({"label": "经营现金流净额", "value": round(ocf / 1e8, 1), "note": "亿元（最近报告期）"})
    if cf is not None:
        note = "赚到的钱真到账没；>1 说明利润是真钱，长期 <<1 利润可能是纸面" if cf is not None else None
        cash_items.append({"label": "现金/净利润", "value": cf, "note": note})
    if pcf is not None:
        cash_items.append({"label": "每股经营现金流", "value": pcf})
    out["sections"].append({"key": "cash", "label": "现金（钱真不真）", "items": cash_items})

    # 去掉空块，避免前端一堆空卡片
    out["sections"] = [s for s in out["sections"] if s["items"]]
    return out