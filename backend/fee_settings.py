import json
import sqlite3

try:
    from .cash import DEFAULT_ACCOUNT
except ImportError:
    from cash import DEFAULT_ACCOUNT


DEFAULT_FEE_RULES = {
    "A股权益": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0005, "transfer_fee_rate": 0.00001, "min_commission": 0.0},
    "A股ETF": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "港股ETF": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "REITs": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "黄金": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "债基": {"commission_rate": 0.0, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
    "其他": {"commission_rate": 0.00025, "stamp_tax_rate": 0.0, "transfer_fee_rate": 0.0, "min_commission": 0.0},
}


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
