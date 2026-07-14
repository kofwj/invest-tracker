"""券商对账单导入与差异比对（只读 diff + 可选生成校正建议）。

支持：
1) 简化 CSV：code,name,quantity,avg_cost,total_dividend,category
2) 华泰常见导出（utf-8 / gbk）：自动识别「证券代码/股票代码」「证券名称」「证券数量/持仓数量/股份余额」「成本价/成本价(元)/参考成本价」等列
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

try:
    from .database import LOCAL_TZ
    from .holding_calculator import infer_category
except ImportError:
    from database import LOCAL_TZ
    from holding_calculator import infer_category


def _local_today_iso() -> str:
    return date.today().isoformat() if LOCAL_TZ is None else __import__("datetime").datetime.now(LOCAL_TZ).date().isoformat()


def _norm_header(h: str) -> str:
    s = str(h or "").strip().lower()
    s = s.replace(" ", "").replace("\u3000", "")
    s = s.replace("（", "(").replace("）", ")")
    return s


# header token -> field
_HEADER_MAP = {
    "code": {
        "code",
        "证券代码",
        "股票代码",
        "基金代码",
        "代码",
        "symbol",
        "证券代码(代码)",
    },
    "name": {
        "name",
        "证券名称",
        "股票名称",
        "基金名称",
        "名称",
        "证券简称",
    },
    "quantity": {
        "quantity",
        "qty",
        "证券数量",
        "持仓数量",
        "股份余额",
        "持仓股数",
        "库存数",
        "可用数量",
        "数量",
        "持仓量",
        "当前拥股",
    },
    "avg_cost": {
        "avg_cost",
        "cost",
        "成本价",
        "成本价(元)",
        "参考成本价",
        "买入均价",
        "成本",
        "摊薄成本",
        "保本价",
        "持仓成本",
    },
    "total_dividend": {
        "total_dividend",
        "dividend",
        "累计分红",
        "分红",
        "累计红利",
    },
    "category": {
        "category",
        "分类",
        "资产类别",
        "品种",
    },
    "market_value": {
        "market_value",
        "市值",
        "最新市值",
        "证券市值",
    },
    "last_price": {
        "last_price",
        "price",
        "现价",
        "最新价",
        "市价",
    },
}


def _match_field(header: str) -> Optional[str]:
    h = _norm_header(header)
    # also keep original Chinese form for set membership
    raw = str(header or "").strip()
    for field, aliases in _HEADER_MAP.items():
        norm_aliases = {_norm_header(a) for a in aliases} | set(aliases)
        if h in norm_aliases or raw in aliases:
            return field
    # fuzzy contains
    if "代码" in raw and "名称" not in raw:
        return "code"
    if "名称" in raw or "简称" in raw:
        return "name"
    if any(k in raw for k in ("持仓数量", "证券数量", "股份余额", "持仓股数", "库存")):
        return "quantity"
    if "成本" in raw and "市值" not in raw:
        return "avg_cost"
    if "分红" in raw or "红利" in raw:
        return "total_dividend"
    if "市值" in raw:
        return "market_value"
    if raw in ("现价", "最新价", "市价") or ("价" in raw and "成本" not in raw and "市值" not in raw):
        return "last_price"
    return None


def _parse_number(val: Any) -> Optional[float]:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s in ("-", "--", "—", "N/A", "null"):
        return None
    s = s.replace(",", "").replace("，", "").replace("%", "").replace("元", "")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in (".", "-", "-."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_code(code: Any) -> str:
    s = str(code or "").strip().upper()
    s = s.replace(" ", "")
    # strip exchange suffix SH/SZ/BJ
    s = re.sub(r"\.(SH|SZ|BJ|SS|HK)$", "", s, flags=re.I)
    s = re.sub(r"^(SH|SZ|BJ)", "", s, flags=re.I)
    # pure digits keep; pad common A-share to 6
    if re.fullmatch(r"\d{1,6}", s):
        return s.zfill(6)
    return s


def decode_upload_bytes(raw: bytes) -> str:
    if raw is None:
        return ""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_broker_csv_text(text: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse broker holdings CSV text into normalized rows."""
    text = (text or "").strip()
    if not text:
        return [], {"error": "文件为空"}

    # sniff delimiter
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = "," if sample.count(",") >= sample.count("\t") else "\t"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows_raw = [r for r in reader if any(str(c).strip() for c in r)]
    if not rows_raw:
        return [], {"error": "没有有效行"}

    # find header row: first row that maps >= 2 fields including code or quantity
    header_idx = 0
    field_index: Dict[str, int] = {}
    for i, row in enumerate(rows_raw[:15]):
        mapping = {}
        for j, header_cell in enumerate(row):
            f = _match_field(header_cell)
            if f and f not in mapping:
                mapping[f] = j
        if "code" in mapping and ("quantity" in mapping or "avg_cost" in mapping or "name" in mapping):
            header_idx = i
            field_index = mapping
            break
    if not field_index:
        # fallback: assume first row headers simple English
        header_idx = 0
        for j, header_cell in enumerate(rows_raw[0]):
            f = _match_field(header_cell) or (
                _norm_header(header_cell) if _norm_header(header_cell) in _HEADER_MAP else None
            )
            if f and f not in field_index:
                field_index[f] = j

    if "code" not in field_index:
        return [], {
            "error": "无法识别证券代码列，请导出含「证券代码/股票代码/code」的持仓表",
            "headers_seen": rows_raw[header_idx] if rows_raw else [],
        }

    parsed: List[Dict[str, Any]] = []
    for row in rows_raw[header_idx + 1 :]:
        if not row:
            continue

        def get_cell(field: str, _row=row) -> Any:
            idx = field_index.get(field)
            if idx is None or idx >= len(_row):
                return None
            return _row[idx]

        code = _normalize_code(get_cell("code"))
        if not code or code in ("合计", "小计", "总计"):
            continue
        # skip footer-like
        if any(k in code for k in ("合计", "小计", "总")):
            continue
        name = str(get_cell("name") or "").strip() or code
        qty = _parse_number(get_cell("quantity"))
        avg = _parse_number(get_cell("avg_cost"))
        div = _parse_number(get_cell("total_dividend"))
        cat = str(get_cell("category") or "").strip()
        if qty is None:
            # some exports only have market value + price
            mv = _parse_number(get_cell("market_value"))
            px = _parse_number(get_cell("last_price"))
            if mv is not None and px and px > 0:
                qty = mv / px
        if qty is None:
            continue
        if qty < 0:
            continue
        # zero qty rows still useful for "broker closed / app still holds"
        item = {
            "code": code,
            "name": name,
            "quantity": round(float(qty), 6),
            "avg_cost": round(float(avg), 6) if avg is not None else None,
            "total_dividend": round(float(div), 4) if div is not None else None,
            "category": cat or None,
        }
        parsed.append(item)

    meta = {
        "delimiter": delimiter,
        "header_row": header_idx,
        "mapped_fields": sorted(field_index.keys()),
        "row_count": len(parsed),
    }
    return parsed, meta


def compare_holdings(
    broker_rows: List[Dict[str, Any]],
    app_rows: List[Dict[str, Any]],
    *,
    qty_tol: float = 0.01,
    cost_tol: float = 0.005,
    as_of_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare broker snapshot vs app holdings. Returns diffs + correction suggestions."""
    as_of = as_of_date or _local_today_iso()
    broker_map = {r["code"]: r for r in broker_rows if r.get("code")}
    app_map = {}
    for r in app_rows:
        code = _normalize_code(r.get("code"))
        if not code:
            continue
        app_map[code] = {
            "code": code,
            "name": (r.get("name") or code),
            "quantity": float(r.get("quantity") or 0),
            "avg_cost": float(r.get("avg_cost") or 0),
            "total_dividend": float(r.get("total_dividend") or 0),
            "category": r.get("category") or "",
            "last_price": float(r.get("last_price") or 0),
        }

    all_codes = sorted(set(broker_map) | set(app_map))
    matched = 0
    diffs: List[Dict[str, Any]] = []
    suggestions: List[Dict[str, Any]] = []

    for code in all_codes:
        b = broker_map.get(code)
        a = app_map.get(code)
        b_qty = float(b["quantity"]) if b else 0.0
        a_qty = float(a["quantity"]) if a else 0.0
        b_cost = b.get("avg_cost") if b else None
        a_cost = float(a["avg_cost"]) if a else None
        b_div = b.get("total_dividend") if b else None
        a_div = float(a["total_dividend"]) if a else None
        name = (b or a or {}).get("name") or code
        category = (b or {}).get("category") or (a or {}).get("category") or infer_category(code, name)

        qty_diff = b_qty - a_qty
        cost_diff = None
        if b_cost is not None and a_cost is not None:
            cost_diff = float(b_cost) - float(a_cost)

        status = "match"
        reasons = []
        if b is None:
            status = "only_app"
            reasons.append("券商表无此代码，本系统仍有持仓")
        elif a is None:
            status = "only_broker"
            reasons.append("券商有持仓，本系统无此持仓")
        else:
            if abs(qty_diff) > qty_tol:
                status = "mismatch"
                reasons.append(f"数量差 {qty_diff:+.4g}")
            if b_cost is not None and a_cost is not None and abs(float(b_cost) - float(a_cost)) > cost_tol:
                status = "mismatch"
                reasons.append(f"成本差 {float(b_cost) - float(a_cost):+.4g}")
            if status == "match":
                matched += 1

        if status == "match":
            continue

        row = {
            "code": code,
            "name": name,
            "status": status,
            "reasons": reasons,
            "broker_quantity": round(b_qty, 6) if b is not None else None,
            "app_quantity": round(a_qty, 6) if a is not None else None,
            "quantity_diff": round(qty_diff, 6),
            "broker_avg_cost": round(float(b_cost), 6) if b_cost is not None else None,
            "app_avg_cost": round(float(a_cost), 6) if a_cost is not None else None,
            "cost_diff": round(cost_diff, 6) if cost_diff is not None else None,
            "broker_total_dividend": round(float(b_div), 4) if b_div is not None else None,
            "app_total_dividend": round(float(a_div), 4) if a_div is not None else None,
            "category": category,
        }
        diffs.append(row)

        # correction suggestion: use broker as truth when broker has row; else zero out if only_app
        if b is not None:
            actual_qty = b_qty
            actual_cost = float(b_cost) if b_cost is not None else (float(a_cost) if a_cost is not None else 0.0)
            actual_div = float(b_div) if b_div is not None else (float(a_div) if a_div is not None else 0.0)
        else:
            actual_qty = 0.0
            actual_cost = float(a_cost) if a_cost is not None else 0.0
            actual_div = float(a_div) if a_div is not None else 0.0

        suggestions.append(
            {
                "date": as_of,
                "code": code,
                "name": name,
                "category": category,
                "actual_quantity": round(actual_qty, 6),
                "actual_avg_cost": round(actual_cost, 6),
                "actual_total_dividend": round(actual_div, 4),
                "remark": "券商对账单导入校正",
                "status": status,
            }
        )

    return {
        "as_of_date": as_of,
        "broker_count": len(broker_map),
        "app_count": len(app_map),
        "matched_count": matched,
        "diff_count": len(diffs),
        "diffs": diffs,
        "suggestions": suggestions,
        "summary_text": (
            f"券商 {len(broker_map)} 只 / 系统 {len(app_map)} 只 / 一致 {matched} 只 / 差异 {len(diffs)} 只"
        ),
    }
