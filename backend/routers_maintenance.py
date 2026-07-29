import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from .csv_utils import create_safety_backup
    from .database import BACKUP_DIR, DB_PATH, LOCAL_TZ, open_db
except ImportError:
    from csv_utils import create_safety_backup
    from database import BACKUP_DIR, DB_PATH, LOCAL_TZ, open_db

router = APIRouter()

BACKUP_PATH = Path(BACKUP_DIR)
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_BACKUP_UPLOAD_BYTES", str(200 * 1024 * 1024)))  # 200MB default


class RestoreRequest(BaseModel):
    filename: str


def safe_backup_path(filename: str) -> Path:
    name = Path(str(filename or "")).name
    if not name or name != filename or not name.endswith((".db.bak", ".bak")):
        raise HTTPException(status_code=400, detail="备份文件名无效")
    path = BACKUP_PATH / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    # Ensure resolved path stays inside backup dir
    try:
        path.resolve().relative_to(BACKUP_PATH.resolve())
    except Exception:
        raise HTTPException(status_code=400, detail="备份文件名无效")
    return path


REQUIRED_APP_COLUMNS = {
    "transactions": {
        "id", "date", "code", "name", "direction", "quantity", "price", "amount", "fee",
    },
    "holdings": {
        "id", "code", "name", "quantity", "avg_cost", "diluted_cost", "total_dividend", "last_price",
    },
    "deposits": {"id", "bank_name", "amount", "interest_rate", "due_date"},
    "settings": {"key", "value"},
}

CURRENT_SCHEMA_COLUMNS = {
    **REQUIRED_APP_COLUMNS,
    "cash_flows": {"id", "date", "account", "flow_type", "amount"},
    "daily_snapshots": {"id", "date", "total_assets", "pending_purchase", "lifetime_profit"},
    "holding_corrections": {"id", "date", "code", "actual_quantity", "actual_avg_cost"},
    "portfolio_cash_flows": {"id", "date", "flow_type", "amount"},
    "discipline_drafts": {"id", "date", "code", "side", "amount", "status", "transaction_id"},
    "alert_rules": {"id", "target_type", "code", "condition", "threshold"},
    "alert_events": {"id", "rule_id", "trigger_time", "target_code"},
    "notify_send_log": {"id", "event", "channel", "ok", "created_at"},
}


def _schema_helpers():
    try:
        from .schema import SCHEMA_VERSION, ensure_app_schema, get_schema_version
    except ImportError:
        from schema import SCHEMA_VERSION, ensure_app_schema, get_schema_version
    return SCHEMA_VERSION, ensure_app_schema, get_schema_version


def validate_restore_candidate(path: Path):
    """Migrate and query a disposable copy so the live DB is never the compatibility test."""
    schema_version, ensure_app_schema, get_schema_version = _schema_helpers()
    with sqlite3.connect(str(path)) as source:
        source.row_factory = sqlite3.Row
        candidate_version = get_schema_version(source)
        if candidate_version > schema_version:
            raise HTTPException(
                status_code=400,
                detail=f"备份版本过新（{candidate_version}），当前程序仅支持到 {schema_version}",
            )
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with sqlite3.connect(str(tmp_path)) as probe:
                source.backup(probe)
                ensure_app_schema(probe)
                for table, required in CURRENT_SCHEMA_COLUMNS.items():
                    columns = {str(row[1]) for row in probe.execute(f"PRAGMA table_info({table})").fetchall()}
                    missing = sorted(required - columns)
                    if missing:
                        raise ValueError(f"{table} 缺少列：{', '.join(missing)}")
                ok = probe.execute("PRAGMA integrity_check").fetchone()[0]
                if str(ok).lower() != "ok":
                    raise ValueError(f"迁移后完整性检查失败：{ok}")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"备份与当前版本不兼容：{exc}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)


def check_sqlite(path: Path):
    try:
        with sqlite3.connect(str(path)) as conn:
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {
                str(r[0])
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"备份文件无法读取：{e}")
    if str(ok).lower() != "ok":
        raise HTTPException(status_code=400, detail=f"备份完整性检查失败：{ok}")
    missing = [name for name in REQUIRED_APP_COLUMNS if name not in tables]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"不是本系统账本备份，缺少表：{', '.join(missing)}",
        )
    with sqlite3.connect(str(path)) as conn:
        for table, required in REQUIRED_APP_COLUMNS.items():
            columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            missing_columns = sorted(required - columns)
            if missing_columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"不是有效账本备份，{table} 缺少列：{', '.join(missing_columns)}",
                )
    validate_restore_candidate(path)


def restore_sqlite(source: Path, *, rollback_source: Optional[Path] = None):
    """Restore through SQLite's backup API, then migrate before serving requests."""
    try:
        with sqlite3.connect(str(source)) as src, open_db() as dst:
            src.backup(dst)
            _, ensure_app_schema, _ = _schema_helpers()
            ensure_app_schema(dst)
            ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
            if str(ok).lower() != "ok":
                raise ValueError(f"恢复后完整性检查失败：{ok}")
            dst.commit()
    except Exception as e:
        if rollback_source is not None:
            try:
                with sqlite3.connect(str(rollback_source)) as previous, open_db() as dst:
                    previous.backup(dst)
                    dst.commit()
            except Exception as rollback_exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"恢复备份失败且自动回滚失败：{e}；{rollback_exc}",
                ) from e
        raise HTTPException(status_code=500, detail=f"恢复备份失败：{e}") from e


@router.get("/maintenance/status")
def maintenance_status():
    BACKUP_PATH.mkdir(parents=True, exist_ok=True)
    backups = sorted(BACKUP_PATH.glob("*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
    latest = backups[0] if backups else None
    db = Path(DB_PATH)
    return {
        "db_path": str(db),
        "db_exists": db.exists(),
        "db_size": db.stat().st_size if db.exists() else 0,
        "latest_backup": latest.name if latest else None,
        "latest_backup_at": datetime.fromtimestamp(latest.stat().st_mtime, LOCAL_TZ).replace(tzinfo=None).isoformat(timespec="seconds") if latest else None,
        "backup_count": len(backups),
        "backup_dir": str(BACKUP_PATH),
    }


@router.get("/maintenance/backups")
def list_backups():
    BACKUP_PATH.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in sorted(BACKUP_PATH.glob("*.bak"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        rows.append({
            "filename": p.name,
            "size": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime, LOCAL_TZ).replace(tzinfo=None).isoformat(timespec="seconds"),
        })
    return rows


@router.post("/maintenance/backups")
def create_backup():
    path = Path(create_safety_backup("manual"))
    return {"status": "success", "filename": path.name, "path": str(path)}


@router.get("/maintenance/backups/{filename}/download")
def download_backup(filename: str):
    path = safe_backup_path(filename)
    return FileResponse(str(path), filename=path.name, media_type="application/octet-stream")


@router.delete("/maintenance/backups/{filename}")
def delete_backup(filename: str):
    path = safe_backup_path(filename)
    deleted = path.name
    try:
        path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除备份失败：{e}")
    return {"status": "success", "deleted": deleted}


@router.post("/maintenance/restore")
def restore_backup(payload: RestoreRequest):
    backup = safe_backup_path(payload.filename)
    check_sqlite(backup)
    pre_restore = Path(create_safety_backup("before_restore"))
    restore_sqlite(backup, rollback_source=pre_restore)
    return {"status": "success", "restored": backup.name, "pre_restore_backup": pre_restore.name}


@router.post("/maintenance/restore-upload")
async def restore_uploaded_backup(file: UploadFile = File(...)):
    original_name = Path(str(file.filename or "")).name
    if not original_name or not original_name.endswith((".db.bak", ".bak", ".db")):
        raise HTTPException(status_code=400, detail="请上传 .db.bak、.bak 或 .db 备份文件")

    BACKUP_PATH.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(LOCAL_TZ).strftime("%Y%m%d_%H%M%S")
    upload_path = BACKUP_PATH / f"uploaded_{ts}_{original_name}"

    size = 0
    try:
        with upload_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    out.close()
                    try:
                        upload_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=400,
                        detail=f"上传备份超过大小限制（{MAX_UPLOAD_BYTES} 字节）",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存上传备份失败：{e}")
    finally:
        await file.close()

    # Basic SQLite header check
    try:
        with upload_path.open("rb") as f:
            header = f.read(16)
        if not header.startswith(b"SQLite format 3"):
            upload_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="文件不是有效的 SQLite 数据库")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"备份文件校验失败：{e}")

    check_sqlite(upload_path)
    pre_restore = Path(create_safety_backup("before_restore_upload"))
    restore_sqlite(upload_path, rollback_source=pre_restore)
    return {
        "status": "success",
        "uploaded_backup": upload_path.name,
        "pre_restore_backup": pre_restore.name,
    }
