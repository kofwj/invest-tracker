import csv
import io
import os
import sqlite3
from datetime import date as dt_date, datetime

from fastapi import HTTPException
from fastapi.responses import Response

try:
    from .database import BACKUP_DIR, DB_PATH, LOCAL_TZ, db_session
except ImportError:
    from database import BACKUP_DIR, DB_PATH, LOCAL_TZ, db_session


TRANSACTION_CSV_COLUMNS = ["date", "account", "code", "name", "category", "direction", "quantity", "price", "amount", "fee", "remark"]
DEPOSIT_CSV_COLUMNS = ["bank_name", "amount", "interest_rate", "due_date", "remark"]

TRANSACTION_CSV_HEADERS_CN = ["日期", "证券账户", "代码", "名称", "分类", "方向", "数量", "价格", "金额", "手续费", "备注"]
DEPOSIT_CSV_HEADERS_CN = ["银行", "金额", "年利率", "到期日", "备注"]

TRANSACTION_HEADER_ALIASES = {
    "date": "date", "日期": "date",
    "account": "account", "证券账户": "account", "账户": "account",
    "code": "code", "代码": "code",
    "name": "name", "名称": "name",
    "category": "category", "分类": "category",
    "direction": "direction", "方向": "direction",
    "quantity": "quantity", "数量": "quantity", "份额": "quantity",
    "price": "price", "价格": "price", "单价": "price", "净值": "price",
    "amount": "amount", "金额": "amount", "总金额": "amount",
    "fee": "fee", "手续费": "fee", "费用": "fee",
    "remark": "remark", "备注": "remark",
}

DEPOSIT_HEADER_ALIASES = {
    "bank_name": "bank_name", "银行": "bank_name", "银行名称": "bank_name",
    "amount": "amount", "金额": "amount", "本金": "amount",
    "interest_rate": "interest_rate", "年利率": "interest_rate", "利率": "interest_rate",
    "due_date": "due_date", "到期日": "due_date", "到期时间": "due_date",
    "remark": "remark", "备注": "remark",
}


def csv_response(filename: str, headers, rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    writer.writerows(rows)
    content = "\ufeff" + out.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def parse_float(value, default=0.0):
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "").replace("¥", "").strip())
    except Exception:
        raise ValueError(f"不是有效数字：{value}")


def normalize_date_string(value, required=True):
    v = str(value or "").strip()
    if not v:
        if required:
            raise ValueError("日期不能为空")
        return ""
    try:
        return dt_date.fromisoformat(v).isoformat()
    except Exception:
        raise ValueError(f"日期格式应为 YYYY-MM-DD：{v}")


def normalize_csv_row(raw_row, aliases):
    row = {}
    for key, value in (raw_row or {}).items():
        normalized_key = aliases.get(str(key or "").strip())
        if normalized_key:
            row[normalized_key] = str(value or "").strip()
    return row


def read_upload_csv(content: bytes):
    text = content.decode("utf-8-sig", errors="ignore")
    sample = text[:2048]
    dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return list(reader)


def _safe_backup_label(label: str):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(label or "manual").strip()) or "manual"


def create_safety_backup(label: str):
    """Create an integrity-checked SQLite backup before risky data mutations."""
    backup_dir = BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(LOCAL_TZ).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"invest_{ts}_{_safe_backup_label(label)}.db.bak")
    with db_session() as src, sqlite3.connect(backup_path) as dst:
        src.backup(dst)
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
    if ok != "ok":
        raise HTTPException(status_code=500, detail=f"操作前备份完整性检查失败：{ok}")
    return backup_path


def create_import_backup(label: str):
    return create_safety_backup(label)
