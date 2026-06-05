import json
import sqlite3
from datetime import date as dt_date
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from .cash import (
        DEFAULT_ACCOUNT,
        cash_flow_adjustment,
        calculated_securities_cash,
        normalize_cash_flow_amount,
        set_setting,
    )
    from .database import open_db
except ImportError:
    from cash import (
        DEFAULT_ACCOUNT,
        cash_flow_adjustment,
        calculated_securities_cash,
        normalize_cash_flow_amount,
        set_setting,
    )
    from database import open_db

router = APIRouter()


class SecuritiesCashUpdate(BaseModel):
    amount: float


class CashFlowBase(BaseModel):
    date: dt_date
    account: Optional[str] = None
    flow_type: str
    amount: float
    remark: Optional[str] = None


class CashFlowUpdate(BaseModel):
    date: Optional[dt_date] = None
    account: Optional[str] = None
    flow_type: Optional[str] = None
    amount: Optional[float] = None
    remark: Optional[str] = None


DEFAULT_FEE_RULES = {
    "A股权益": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0005, "transfer_fee_rate": 0.00001, "min_commission": 0.0},
    "A股ETF": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "港股ETF": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "REITs": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "黄金": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "债基": {"commission_rate": 0.0, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "其他": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
}


class FeeSettingsUpdate(BaseModel):
    accounts: Optional[List[str]] = None
    active_account: Optional[str] = None
    settings: dict


def normalize_fee_rule(rule=None, default=None):
    base = (default or {"commission_rate": 0.0, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0}).copy()
    if isinstance(rule, dict):
        for key in ["commission_rate", "stamp_tax_rate", "transfer_fee_rate", "min_commission"]:
            try:
                base[key] = float(rule.get(key, base.get(key, 0.0)) or 0.0)
            except Exception:
                pass
    return base


def normalize_category_settings(raw=None):
    merged = {k: v.copy() for k, v in DEFAULT_FEE_RULES.items()}
    if isinstance(raw, dict):
        for cat, rule in raw.items():
            merged[cat] = normalize_fee_rule(rule, merged.get(cat))
    return merged


def normalize_fee_settings(raw=None):
    if isinstance(raw, dict) and isinstance(raw.get("settings"), dict):
        explicit_accounts = "accounts" in raw and raw.get("accounts") is not None
        accounts = [str(a).strip() for a in raw.get("accounts", []) if str(a).strip()]
        if not explicit_accounts:
            accounts = [str(a).strip() for a in raw.get("settings", {}).keys() if str(a).strip()]
        accounts = list(dict.fromkeys(accounts))
        if not accounts:
            accounts = [DEFAULT_ACCOUNT]

        settings_by_account = {}
        for acc in accounts:
            rules = raw.get("settings", {}).get(acc, {})
            settings_by_account[acc] = normalize_category_settings(rules)

        active = str(raw.get("active_account") or accounts[0] or DEFAULT_ACCOUNT).strip()
        if active not in accounts:
            active = accounts[0]
        return {"accounts": accounts, "active_account": active, "settings": settings_by_account}

    flat = normalize_category_settings(raw if isinstance(raw, dict) else None)
    return {"accounts": [DEFAULT_ACCOUNT], "active_account": DEFAULT_ACCOUNT, "settings": {DEFAULT_ACCOUNT: flat}}


def get_fee_settings_from_conn(conn):
    row = conn.execute("SELECT value FROM settings WHERE key='fee_settings'").fetchone()
    raw = None
    if row:
        try:
            value = row["value"] if isinstance(row, sqlite3.Row) else row[0]
            raw = json.loads(value)
        except Exception:
            raw = None
    return normalize_fee_settings(raw)


@router.get("/fee-settings")
def get_fee_settings():
    conn = open_db(row_factory=sqlite3.Row)
    data = get_fee_settings_from_conn(conn)
    conn.close()
    return data


@router.put("/fee-settings")
def update_fee_settings(data: FeeSettingsUpdate):
    conn = open_db()
    normalized = normalize_fee_settings({
        "accounts": data.accounts or [],
        "active_account": data.active_account,
        "settings": data.settings,
    })
    set_setting(conn, 'fee_settings', json.dumps(normalized, ensure_ascii=False))
    conn.commit()
    conn.close()
    return {"status": "success", **normalized}


@router.post("/fee-settings/reset")
def reset_fee_settings():
    conn = open_db()
    normalized = normalize_fee_settings({"accounts": [DEFAULT_ACCOUNT], "active_account": DEFAULT_ACCOUNT, "settings": {DEFAULT_ACCOUNT: DEFAULT_FEE_RULES}})
    set_setting(conn, 'fee_settings', json.dumps(normalized, ensure_ascii=False))
    conn.commit()
    conn.close()
    return {"status": "success", **normalized}


@router.get("/securities-cash")
def get_securities_cash():
    conn = open_db(row_factory=sqlite3.Row)
    amount, base, flow = calculated_securities_cash(conn)
    manual_flow = cash_flow_adjustment(conn)
    conn.commit()
    conn.close()
    return {"amount": amount, "base_amount": base, "cash_flow_adjustment": manual_flow, "transaction_cash_flow": flow}


@router.put("/securities-cash")
def update_securities_cash(data: SecuritiesCashUpdate):
    conn = open_db(row_factory=sqlite3.Row)
    current, base, tx_flow = calculated_securities_cash(conn)
    delta = float(data.amount or 0) - current
    if abs(delta) >= 0.005:
        conn.execute("""
            INSERT INTO cash_flows (date, account, flow_type, amount, balance_before, balance_after, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (dt_date.today().isoformat(), DEFAULT_ACCOUNT, '现金校准', delta, current, float(data.amount or 0), '现金设置页手动校准'))
    set_setting(conn, 'securities_cash', data.amount)
    manual_flow = cash_flow_adjustment(conn)
    conn.commit()
    conn.close()
    return {"status": "success", "amount": data.amount, "base_amount": base, "cash_flow_adjustment": manual_flow, "transaction_cash_flow": tx_flow, "delta": delta}


@router.get("/cash-flows")
def list_cash_flows(start_date: Optional[str] = None, end_date: Optional[str] = None, account: Optional[str] = None, flow_type: Optional[str] = None):
    conn = open_db(row_factory=sqlite3.Row)
    query = "SELECT * FROM cash_flows WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if account:
        query += " AND account = ?"
        params.append(account)
    if flow_type:
        query += " AND flow_type = ?"
        params.append(flow_type)
    query += " ORDER BY date DESC, id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.post("/cash-flows")
def add_cash_flow(flow_data: CashFlowBase):
    conn = open_db(row_factory=sqlite3.Row)
    before, _, _ = calculated_securities_cash(conn)
    amount = normalize_cash_flow_amount(flow_data.flow_type, flow_data.amount)
    after = before + amount
    conn.execute("""
        INSERT INTO cash_flows (date, account, flow_type, amount, balance_before, balance_after, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (flow_data.date.isoformat(), flow_data.account or DEFAULT_ACCOUNT, flow_data.flow_type, amount, before, after, flow_data.remark))
    set_setting(conn, 'securities_cash', after)
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"status": "success", "id": new_id, "amount": amount, "balance_before": before, "balance_after": after}


@router.put("/cash-flows/{flow_id}")
def update_cash_flow(flow_id: int, flow_data: CashFlowUpdate):
    conn = open_db(row_factory=sqlite3.Row)
    old = conn.execute("SELECT * FROM cash_flows WHERE id = ?", (flow_id,)).fetchone()
    if not old:
        conn.close()
        raise HTTPException(status_code=404, detail="Cash flow not found")
    updates = []
    vals = []
    if flow_data.date is not None:
        updates.append("date = ?")
        vals.append(flow_data.date.isoformat())
    if flow_data.account is not None:
        updates.append("account = ?")
        vals.append(flow_data.account or DEFAULT_ACCOUNT)
    new_type = flow_data.flow_type if flow_data.flow_type is not None else old['flow_type']
    if flow_data.flow_type is not None:
        updates.append("flow_type = ?")
        vals.append(flow_data.flow_type)
    if flow_data.amount is not None:
        updates.append("amount = ?")
        vals.append(normalize_cash_flow_amount(new_type, flow_data.amount))
    if flow_data.remark is not None:
        updates.append("remark = ?")
        vals.append(flow_data.remark)
    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")
    vals.append(flow_id)
    conn.execute(f"UPDATE cash_flows SET {', '.join(updates)} WHERE id = ?", vals)
    amount, _, _ = calculated_securities_cash(conn)
    set_setting(conn, 'securities_cash', amount)
    conn.commit()
    conn.close()
    return {"status": "success", "amount": amount}


@router.delete("/cash-flows/{flow_id}")
def delete_cash_flow(flow_id: int):
    conn = open_db(row_factory=sqlite3.Row)
    conn.execute("DELETE FROM cash_flows WHERE id = ?", (flow_id,))
    if conn.total_changes == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Cash flow not found")
    amount, _, _ = calculated_securities_cash(conn)
    set_setting(conn, 'securities_cash', amount)
    conn.commit()
    conn.close()
    return {"status": "success", "amount": amount}
