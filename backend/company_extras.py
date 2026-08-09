"""公司简报 + 历史分红：补充 K 线页的基本面信息。

数据源：
- 历史分红：东财 ak.stock_fhps_detail_em —— 完整历史送转+现金分红（含近三年）
- 公司简报：巨潮 ak.stock_profile_cninfo —— 公司名/行业/法人/上市日期/主营/官网

约定：这俩只对 A 股个股有意义。ETF/基金/场外基金拉不到就静默返回空，
不报错不挂页面，跟基本面体检同一套思路。
"""

from __future__ import annotations

import datetime
import logging
import math

logger = logging.getLogger(__name__)


def _fetch_top_holders(code: str, limit: int = 10):
    """最新一期前十大股东 + 股东户数 + 每期环比。

    东财 stock_main_stock_holder 返回多期（每期十大）：
      - 最新一期 = 截至日期最大的那组，即当前十大股东
      - 北向(香港中央结算)最新一期比例常为 NaN，取最近一期已披露的有效值补上
      - 环比 = 该股东最近两个已披露有效比例的差（上披露期 → 本期）
    返回 {holders:[{name,pct,type,kind,date,date_label,change}], holder_count}。
    change 单位与 pct 相同（百分比点），None 表示无从比较（只披露一期）。
    """
    c = str(code or "").strip()
    if not c:
        return None
    try:
        import akshare as ak

        df = ak.stock_main_stock_holder(stock=c)
        if df is None or df.empty:
            return None
        df = df.sort_values(by="截至日期", ascending=False).reset_index(drop=True)
        latest_date = df.iloc[0]["截至日期"]
        # 最新一期的这组股东（东财排名顺序：编号 1..10）
        latest_rows = df[df["截至日期"] == latest_date].copy()
        if "编号" in latest_rows.columns:
            latest_rows["_rank"] = latest_rows["编号"].astype(str).str.extract(r"(\d+)")[0].astype(float)
            latest_rows = latest_rows.sort_values("_rank").head(limit)
        else:
            latest_rows = latest_rows.head(limit)
        # 每个股东的所有 (披露比例, 日期)，按日期降序（去 NaN）
        by_name: dict[str, list] = {}
        for _, r in df.iterrows():
            name = str(r.get("股东名称") or "").strip()
            if not name:
                continue
            pct = r.get("持股比例")
            try:
                pct = float(pct) if pct is not None else None
            except (TypeError, ValueError):
                pct = None
            if pct is not None and not math.isfinite(pct):
                pct = None
            by_name.setdefault(name, []).append(
                (pct, r.get("截至日期"), str(r.get("股本性质") or ""))
            )
        holders = []
        for _, r in latest_rows.iterrows():
            name = str(r.get("股东名称") or "").strip()
            if not name:
                continue
            tail = str(r.get("股本性质") or "")
            # 北向资金 = 香港中央结算
            if "香港中央结算" in name:
                kind = "north"
            else:
                inst_key = ("基金", "证券", "银行", "保险", "资管", "信托",
                            "企业年金", "社保", "养老", "公司-", "投资管理", "有限合伙")
                if any(k in tail for k in ("国有", "国家")):
                    kind = "state"
                elif any(k in name for k in inst_key):
                    kind = "institution"
                elif "个人" in tail or "自然人" in tail:
                    kind = "person"
                else:
                    kind = "other"
            # 该股东最近两个已披露有效比例
            valid = [(p, d) for p, d, _ in by_name.get(name, []) if p is not None]
            pct = valid[0][0] if valid else None
            date = valid[0][1] if valid else latest_date
            prev_pct = valid[1][0] if len(valid) > 1 else None
            change = None
            if pct is not None and prev_pct is not None:
                change = round(pct - prev_pct, 2)
            holders.append({
                "name": name,
                "pct": pct,
                "type": tail or "",
                "kind": kind,
                "date": str(date),
                "change": change,
            })
        # 股东户数取最新一期的值
        holder_count = None
        try:
            hc = float(str(df.iloc[0].get("股东总数") or "").replace(",", ""))
            holder_count = int(hc)
        except (TypeError, ValueError):
            pass
        return {"holders": holders, "holder_count": holder_count}
    except Exception as exc:
        logger.info("前十大股东 %s 获取失败: %s", c, exc)
        return None


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

    每项：{report, desc('每10股派…'), per10, yield_pct, record_date, ex_date}。
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
        for _, r in df.iterrows():
            report = str(r.get("报告期") or "")[:7]  # 2024-12-31 -> 2024-12
            desc = str(r.get("现金分红-现金分红比例描述") or "").strip()
            ex = str(r.get("除权除息日") or "").strip() or None
            record = str(r.get("股权登记日") or "").strip() or None
            per10 = r.get("现金分红-现金分红比例")
            try:
                per10 = round(float(per10), 2) if per10 is not None and math.isfinite(float(per10)) else None
            except (TypeError, ValueError):
                per10 = None
            yield_pct = r.get("现金分红-股息率")
            try:
                yield_pct = (round(float(yield_pct) * 100, 2)
                             if yield_pct is not None and math.isfinite(float(yield_pct)) else None)
            except (TypeError, ValueError):
                yield_pct = None
            if report.startswith(("NaT", "None", "nan")):
                report = None
            out.append({
                "report": report,
                "desc": desc,
                "per10": per10,
                "yield_pct": yield_pct,
                "record_date": record,
                "ex_date": ex,
            })
        # limit=None/0 表示全量
        return out if limit in (0, None) else out[:limit]
    except Exception as exc:
        logger.info("历史分红 %s 获取失败: %s", c, exc)
        return []


def dividend_summary(rows: list) -> dict | None:
    """近一年已实施现金分红累计（拿真金白银）。

    以最新除息日为锚往前 365 天，累加 '每10股派X元' 的 per10；
    per_hand = 一手(100股)到手 = per10 * 10。
    rows 需含 per10 与 ex_date；算不出来返回 None。
    """
    dated = [
        r for r in rows
        if r.get("per10") is not None and r.get("ex_date")
    ]
    if not dated:
        return None
    parsed = []
    for r in dated:
        try:
            d = datetime.date.fromisoformat(r["ex_date"])
        except (TypeError, ValueError):
            continue
        parsed.append((r, d))
    if not parsed:
        return None
    _, newest = max(parsed, key=lambda x: x[1])
    cutoff = newest - datetime.timedelta(days=365)
    picked = [(r, d) for r, d in parsed if d >= cutoff]
    if not picked:
        return None
    per10 = round(sum(r["per10"] for r, _ in picked), 2)
    return {
        "per10_12m": per10,          # 每10股，近一年累计
        "per_hand": round(per10 * 10, 2),  # 一手(100股)到手
        "count": len(picked),        # 近一年分红了几次
        "newest": newest.isoformat(),
        "cutoff": cutoff.isoformat(),
    }


def build_company_extras(code: str) -> dict:
    """合并简报 + 分红 + 前十大股东，供 /analysis 接口返回：
    {'profile': {...} | None, 'dividends': [...]}"""
    profile = build_company_profile(code)
    holders = _fetch_top_holders(code)
    if profile is not None and holders is not None:
        profile["top_holders"] = holders.get("holders", [])
        profile["holder_count"] = holders.get("holder_count")
    all_divs = build_dividend_history(code, limit=0)  # 全量算近一年
    return {
        "profile": profile,
        "dividends": all_divs[:6],  # 列表只显示最近 6 次
        "dividend_summary": dividend_summary(all_divs),
    }