"""公司简报 + 历史分红：补充 K 线页的基本面信息。

数据源：
- 历史分红：东财 ak.stock_fhps_detail_em —— 完整历史送转+现金分红（含近三年）
- 公司简报：巨潮 ak.stock_profile_cninfo —— 公司名/行业/法人/上市日期/主营/官网

约定：这俩只对 A 股个股有意义。ETF/基金/场外基金拉不到就静默返回空，
不报错不挂页面，跟基本面体检同一套思路。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_company_profile(code: str) -> dict | None:
    """返回公司简报 {}（拉不到/ETF 返回 None）。"""
    c = str(code or "").strip()
    if not c:
        return None
    try:
        import akshare as ak

        df = ak.stock_profile_cninfo(symbol=c)
        if df is None or df.empty:
            return None
        row = df.iloc[0]
        main_biz = str(row.get("主营业务") or "").strip()
        # 主营业务只取第一句，太长截断
        if len(main_biz) > 60:
            main_biz = main_biz[:60] + "…"
        return {
            "name": str(row.get("公司名称") or "").strip(),
            "short_name": str(row.get("A股简称") or "").strip(),
            "industry": str(row.get("所属行业") or "").strip(),
            "legal_rep": str(row.get("法人代表") or "").strip(),
            "founded": str(row.get("成立日期") or "").strip() or None,
            "listed": str(row.get("上市日期") or "").strip() or None,
            "main_biz": main_biz or None,
            "website": str(row.get("官方网站") or "").strip() or None,
            "market": str(row.get("所属市场") or "").strip() or None,
            "scope": str(row.get("经营范围") or "").strip() or None,
        }
    except Exception as exc:
        logger.info("公司简报 %s 获取失败: %s", c, exc)
        return None


def build_dividend_history(code: str, limit: int = 6):
    """返回最近 N 次已实施分红 []（拉不到/无分红返回空列表）。

    每项：{report, desc('每10股派…'), yield_pct, record_date, ex_date}。
    """
    c = str(code or "").strip()
    if not c:
        return []
    try:
        import akshare as ak

        df = ak.stock_fhps_detail_em(symbol=c)
        if df is None or df.empty:
            return []
        # 只看已实施/已实施的方案
        mask = df.get("方案进度", "").astype(str).str.contains("实施", na=False)
        df = df[mask]
        df = df.sort_values(by="除权除息日", ascending=False)
        out = []
        for _, r in df.head(limit).iterrows():
            report = str(r.get("报告期") or "")[:7]  # 2024-12-31 -> 2024-12
            desc = str(r.get("现金分红-现金分红比例描述") or "").strip()
            ex = str(r.get("除权除息日") or "").strip() or None
            record = str(r.get("股权登记日") or "").strip() or None
            yield_pct = r.get("现金分红-股息率")
            try:
                yield_pct = round(float(yield_pct) * 100, 2) if yield_pct is not None else None
            except (TypeError, ValueError):
                yield_pct = None
            if report.startswith(("NaT", "None", "nan")):
                report = None
            out.append({
                "report": report,
                "desc": desc,
                "yield_pct": yield_pct,
                "record_date": record,
                "ex_date": ex,
            })
        return out
    except Exception as exc:
        logger.info("历史分红 %s 获取失败: %s", c, exc)
        return []


def build_company_extras(code: str) -> dict:
    """合并简报 + 分红，供 /analysis 接口返回：
    {'profile': {...} | None, 'dividends': [...]}"""
    return {
        "profile": build_company_profile(code),
        "dividends": build_dividend_history(code),
    }