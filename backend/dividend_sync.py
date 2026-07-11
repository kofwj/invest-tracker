"""Semi-automatic cash dividend drafts for A-share equity holdings.

Flow:
1. Scan current holdings (A股权益) against Eastmoney share-bonus data
2. Estimate cash dividend amount from equity-record-date quantity
3. Mark drafts that already match existing 分红/分红再投资 ledger rows
4. User confirms selected drafts -> insert 分红 transactions

ETF / fund / REIT automatic dividends are out of scope for v1.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

try:
    from .database import LOCAL_TZ
    from .holding_calculator import infer_category, latest_holding_corrections
except ImportError:
    from database import LOCAL_TZ
    from holding_calculator import infer_category, latest_holding_corrections

logger = logging.getLogger(__name__)

DIVIDEND_DIRECTIONS = ("分红", "分红再投资")
DEFAULT_LOOKBACK_DAYS = 400
DATE_MATCH_WINDOW_DAYS = 3
AMOUNT_MATCH_TOLERANCE = 0.08  # 8% amount tolerance for fuzzy dedupe
EASTMONEY_SHAREBONUS_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def normalize_code(code: Any) -> str:
    return str(code or "").strip()


def pure_security_code(code: Any) -> str:
    c = normalize_code(code).lower().replace("f", "")
    return c


def is_a_share_equity(code: str, category: Optional[str] = None, name: str = "") -> bool:
    """Return True when code looks like a pure A-share stock (not ETF/fund/REIT)."""
    cat = str(category or "").strip()
    if cat and cat != "A股权益":
        # Explicit non-equity category from holdings wins.
        if cat in {"A股ETF", "港股ETF", "债基", "REITs", "黄金", "其他"}:
            return False
    c = pure_security_code(code)
    if not (len(c) == 6 and c.isdigit()):
        return False
    # ETF / fund / REIT / gold ETF prefixes on A-share market.
    if c.startswith(("15", "16", "18", "50", "51", "52", "56", "58", "159")):
        return False
    if c.startswith("508"):  # REITs
        return False
    if cat == "A股权益":
        return True
    # Heuristic for uncategorized rows.
    inferred = infer_category(c, name)
    return inferred == "A股权益"


def parse_date_value(raw: Any) -> Optional[date]:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if not text or text in {"None", "null", "-"}:
        return None
    text = text.replace("/", "-")
    text = text[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def holding_quantity_as_of(conn, code: str, as_of: date) -> float:
    """Holding quantity on as_of date (inclusive), using correction anchors when present."""
    code = normalize_code(code)
    if not code or as_of is None:
        return 0.0
    as_of_s = as_of.isoformat()
    corrections = latest_holding_corrections(conn)
    correction = corrections.get(code)
    qty = 0.0
    anchor = None
    if correction:
        c_date = str(correction.get("date") or "")
        if c_date and c_date <= as_of_s:
            qty = float(correction.get("actual_quantity") or 0)
            anchor = c_date

    rows = conn.execute(
        """
        SELECT date, direction, quantity
        FROM transactions
        WHERE code = ? AND TRIM(code) != ''
        ORDER BY date, id
        """,
        (code,),
    ).fetchall()
    for t in rows:
        direction = t["direction"] if isinstance(t, sqlite3.Row) else t[1]
        t_date = str((t["date"] if isinstance(t, sqlite3.Row) else t[0]) or "")
        t_qty = float((t["quantity"] if isinstance(t, sqlite3.Row) else t[2]) or 0)
        if direction in ("申购待确认", "待确认申购"):
            continue
        if t_date > as_of_s:
            continue
        if anchor is not None and t_date <= anchor:
            continue
        if direction in ("买入", "分红再投资"):
            qty += t_qty
        elif direction == "卖出":
            qty = max(0.0, qty - t_qty)
    return float(qty)


def _date_window(center: date, days: int = DATE_MATCH_WINDOW_DAYS) -> Tuple[str, str]:
    start = (center - timedelta(days=days)).isoformat()
    end = (center + timedelta(days=days)).isoformat()
    return start, end


def existing_dividend_rows(conn, code: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, date, code, name, direction, quantity, price, amount, fee, remark, account, category
        FROM transactions
        WHERE code = ? AND direction IN (?, ?)
        ORDER BY date DESC, id DESC
        """,
        (normalize_code(code), *DIVIDEND_DIRECTIONS),
    ).fetchall()
    return [dict(r) for r in rows]


def match_existing_dividend(
    existing: Sequence[Dict[str, Any]],
    *,
    event_date: Optional[date],
    amount: Optional[float],
) -> Optional[Dict[str, Any]]:
    """Find an existing ledger dividend that likely covers this market event."""
    if not existing:
        return None

    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for row in existing:
        row_date = parse_date_value(row.get("date"))
        row_amount = float(row.get("amount") or 0)
        score = 0.0

        if event_date and row_date:
            delta = abs((row_date - event_date).days)
            if delta <= DATE_MATCH_WINDOW_DAYS:
                score += 100 - delta * 10
            elif delta <= 10:
                score += 40 - delta
            else:
                # far away date is weak evidence only when amount is very close
                pass
        elif event_date is None and row_date is None:
            score += 5

        if amount is not None and amount > 0 and row_amount > 0:
            rel = abs(row_amount - amount) / max(amount, row_amount)
            if rel <= AMOUNT_MATCH_TOLERANCE:
                score += 50 - rel * 100
            elif rel <= 0.2:
                score += 15
        if score >= 90:
            candidates.append((score, row))
        elif score >= 70 and event_date and row_date and abs((row_date - event_date).days) <= DATE_MATCH_WINDOW_DAYS:
            candidates.append((score, row))

    if not candidates:
        # Fallback: same day exact date match regardless of amount (manual amount may differ after tax)
        if event_date:
            for row in existing:
                if parse_date_value(row.get("date")) == event_date:
                    return row
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def fetch_eastmoney_share_bonus(code: str, page_size: int = 30) -> List[Dict[str, Any]]:
    """Fetch dividend plan/implementation rows for one A-share stock."""
    security_code = pure_security_code(code)
    if not (len(security_code) == 6 and security_code.isdigit()):
        return []
    params = {
        "sortColumns": "NOTICE_DATE,EX_DIVIDEND_DATE",
        "sortTypes": "-1,-1",
        "pageSize": str(page_size),
        "pageNumber": "1",
        "reportName": "RPT_SHAREBONUS_DET",
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
        "filter": f'(SECURITY_CODE="{security_code}")',
    }
    res = requests.get(
        EASTMONEY_SHAREBONUS_URL,
        params=params,
        timeout=12,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com/",
        },
    )
    res.raise_for_status()
    payload = res.json() or {}
    result = payload.get("result") or {}
    data = result.get("data") or []
    return list(data)


def _cash_per_share(row: Dict[str, Any]) -> Optional[float]:
    """Eastmoney PRETAX_BONUS_RMB is cash dividend per 10 shares."""
    raw = row.get("PRETAX_BONUS_RMB")
    if raw in (None, "", "-"):
        # try parse from plan text: 10派1.30元
        profile = str(row.get("IMPL_PLAN_PROFILE") or "")
        m = re.search(r"10派\s*([0-9]+(?:\.[0-9]+)?)\s*元", profile)
        if not m:
            return None
        return float(m.group(1)) / 10.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value / 10.0


def _event_usable(row: Dict[str, Any]) -> bool:
    progress = str(row.get("ASSIGN_PROGRESS") or "")
    # Prefer implemented distributions; still allow ones with concrete dates.
    has_date = bool(parse_date_value(row.get("EX_DIVIDEND_DATE")) or parse_date_value(row.get("EQUITY_RECORD_DATE")))
    if not has_date:
        return False
    if "实施" in progress:
        return True
    # Some rows may only say 股东大会决议通过 but already have schedule dates.
    if parse_date_value(row.get("EX_DIVIDEND_DATE")):
        return True
    return False


def build_draft_from_market_row(
    conn,
    *,
    holding: Dict[str, Any],
    market_row: Dict[str, Any],
    lookback_start: date,
) -> Optional[Dict[str, Any]]:
    if not _event_usable(market_row):
        return None

    ex_date = parse_date_value(market_row.get("EX_DIVIDEND_DATE"))
    record_date = parse_date_value(market_row.get("EQUITY_RECORD_DATE"))
    event_date = ex_date or record_date
    if event_date is None:
        return None
    if event_date < lookback_start:
        return None

    per_share = _cash_per_share(market_row)
    if per_share is None or per_share <= 0:
        return None

    code = normalize_code(holding.get("code"))
    qty_date = record_date or ex_date
    quantity = holding_quantity_as_of(conn, code, qty_date) if qty_date else 0.0
    # Fall back to current holding if history rebuild is empty but still held.
    if quantity <= 0:
        current_qty = float(holding.get("quantity") or 0)
        # Only use current qty if event is recent (<= 14 days) to avoid huge mis-estimate.
        today = datetime.now(LOCAL_TZ).date()
        if current_qty > 0 and abs((today - event_date).days) <= 14:
            quantity = current_qty

    estimated_amount = round(quantity * per_share, 2) if quantity > 0 else 0.0
    existing = existing_dividend_rows(conn, code)
    matched = match_existing_dividend(existing, event_date=event_date, amount=estimated_amount or None)

    status = "new"
    reason = ""
    if matched:
        status = "already_recorded"
        reason = f"已有流水 #{matched.get('id')} {matched.get('date')} {matched.get('direction')} {matched.get('amount')}"
    elif quantity <= 0:
        status = "zero_qty"
        reason = f"股权登记日({qty_date})持仓数量为 0，跳过"
    elif estimated_amount <= 0:
        status = "zero_amount"
        reason = "估算金额为 0"

    plan = str(market_row.get("IMPL_PLAN_PROFILE") or "")
    name = holding.get("name") or market_row.get("SECURITY_NAME_ABBR") or code
    category = holding.get("category") or infer_category(code, name)
    account = "华泰证券"
    draft_key = f"{pure_security_code(code)}|{event_date.isoformat()}|{round(per_share, 6)}"
    remark = f"自动草稿|{plan}|每股{per_share:.4f}|登记日数量{round(quantity, 4)}"

    return {
        "draft_key": draft_key,
        "code": code,
        "name": name,
        "category": category,
        "account": account,
        "direction": "分红",
        "event_date": event_date.isoformat(),
        "ex_dividend_date": ex_date.isoformat() if ex_date else None,
        "equity_record_date": record_date.isoformat() if record_date else None,
        "plan_profile": plan,
        "assign_progress": market_row.get("ASSIGN_PROGRESS"),
        "cash_per_share": round(per_share, 6),
        "quantity_on_record_date": round(quantity, 6),
        "quantity": 0.0,
        "price": 0.0,
        "amount": estimated_amount,
        "fee": 0.0,
        "remark": remark,
        "status": status,
        "reason": reason,
        "matched_transaction_id": matched.get("id") if matched else None,
        "matched_transaction": matched,
        "source": "eastmoney_sharebonus",
        "selectable": status == "new" and estimated_amount > 0,
    }


def scan_dividend_drafts(
    conn,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    codes: Optional[Iterable[str]] = None,
    fetch_fn=None,
) -> Dict[str, Any]:
    if fetch_fn is None:
        fetch_fn = fetch_eastmoney_share_bonus
    today = datetime.now(LOCAL_TZ).date()
    lookback_start = today - timedelta(days=max(30, int(lookback_days or DEFAULT_LOOKBACK_DAYS)))
    code_filter = {normalize_code(c) for c in (codes or []) if normalize_code(c)}

    holdings = conn.execute(
        "SELECT code, name, category, quantity FROM holdings WHERE quantity > 0"
    ).fetchall()
    holding_rows = [dict(h) for h in holdings]
    if code_filter:
        holding_rows = [h for h in holding_rows if normalize_code(h.get("code")) in code_filter]

    drafts: List[Dict[str, Any]] = []
    skipped_unsupported: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    scanned = 0

    for h in holding_rows:
        code = normalize_code(h.get("code"))
        name = h.get("name") or code
        category = h.get("category")
        if not is_a_share_equity(code, category, name):
            skipped_unsupported.append(
                {
                    "code": code,
                    "name": name,
                    "category": category,
                    "reason": "暂仅支持 A 股个股现金分红自动草稿（ETF/债基/REIT/黄金需手工录入）",
                }
            )
            continue

        scanned += 1
        try:
            market_rows = fetch_fn(code)
        except Exception as exc:
            logger.exception("dividend scan failed for %s", code)
            failed.append({"code": code, "name": name, "reason": str(exc)})
            continue

        for market_row in market_rows:
            draft = build_draft_from_market_row(
                conn,
                holding=h,
                market_row=market_row,
                lookback_start=lookback_start,
            )
            if draft:
                drafts.append(draft)

    # de-dupe identical draft keys
    uniq: Dict[str, Dict[str, Any]] = {}
    for d in drafts:
        uniq[d["draft_key"]] = d
    drafts = sorted(
        uniq.values(),
        key=lambda x: (x.get("event_date") or "", x.get("code") or ""),
        reverse=True,
    )

    summary = {
        "scanned_holdings": scanned,
        "unsupported_holdings": len(skipped_unsupported),
        "draft_total": len(drafts),
        "new_count": sum(1 for d in drafts if d["status"] == "new"),
        "already_recorded_count": sum(1 for d in drafts if d["status"] == "already_recorded"),
        "zero_qty_count": sum(1 for d in drafts if d["status"] == "zero_qty"),
        "failed_count": len(failed),
        "lookback_days": int(lookback_days or DEFAULT_LOOKBACK_DAYS),
        "lookback_start": lookback_start.isoformat(),
        "as_of": today.isoformat(),
    }
    return {
        "status": "success",
        "summary": summary,
        "drafts": drafts,
        "unsupported": skipped_unsupported,
        "failed": failed,
    }


def confirm_dividend_drafts(
    conn,
    drafts: Sequence[Dict[str, Any]],
    *,
    recheck_existing: bool = True,
) -> Dict[str, Any]:
    """Insert confirmed drafts as 分红 transactions. Skips duplicates when recheck_existing."""
    created = []
    skipped = []
    errors = []

    for raw in drafts:
        try:
            code = normalize_code(raw.get("code"))
            name = str(raw.get("name") or code).strip() or code
            category = raw.get("category") or infer_category(code, name)
            account = raw.get("account") or "华泰证券"
            event_date = parse_date_value(raw.get("event_date") or raw.get("date"))
            amount = float(raw.get("amount") or 0)
            fee = float(raw.get("fee") or 0)
            remark = str(raw.get("remark") or "").strip()
            direction = str(raw.get("direction") or "分红").strip() or "分红"
            if direction != "分红":
                # v1 only supports cash dividend confirmation
                errors.append({"code": code, "reason": "半自动确认目前仅支持现金分红方向"})
                continue
            if not code:
                errors.append({"code": code, "reason": "代码为空"})
                continue
            if event_date is None:
                errors.append({"code": code, "reason": "缺少分红日期"})
                continue
            if amount <= 0:
                errors.append({"code": code, "reason": "金额必须大于0"})
                continue

            if recheck_existing:
                existing = existing_dividend_rows(conn, code)
                matched = match_existing_dividend(existing, event_date=event_date, amount=amount)
                if matched:
                    skipped.append(
                        {
                            "code": code,
                            "event_date": event_date.isoformat(),
                            "reason": f"已存在相近分红流水 #{matched.get('id')}",
                            "matched_transaction_id": matched.get("id"),
                        }
                    )
                    continue

            if not remark:
                plan = raw.get("plan_profile") or ""
                remark = f"自动确认分红|{plan}".strip("|")

            cur = conn.execute(
                """
                INSERT INTO transactions
                (date, code, name, category, account, direction, quantity, price, amount, fee, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_date.isoformat(),
                    code,
                    name,
                    category,
                    account,
                    "分红",
                    0.0,
                    0.0,
                    amount,
                    fee,
                    remark,
                ),
            )
            new_id = cur.lastrowid
            created.append(
                {
                    "id": new_id,
                    "code": code,
                    "name": name,
                    "date": event_date.isoformat(),
                    "amount": amount,
                    "remark": remark,
                }
            )
        except Exception as exc:
            logger.exception("confirm dividend draft failed")
            errors.append({"code": raw.get("code"), "reason": str(exc)})

    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "created_count": len(created),
        "skipped_count": len(skipped),
        "error_count": len(errors),
    }
