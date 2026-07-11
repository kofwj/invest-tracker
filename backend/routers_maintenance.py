import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from .csv_utils import create_safety_backup
    from .database import BACKUP_DIR, DB_PATH, LOCAL_TZ
except ImportError:
    from csv_utils import create_safety_backup
    from database import BACKUP_DIR, DB_PATH, LOCAL_TZ

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


def check_sqlite(path: Path):
    try:
        with sqlite3.connect(str(path)) as conn:
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"备份文件无法读取：{e}")
    if str(ok).lower() != "ok":
        raise HTTPException(status_code=400, detail=f"备份完整性检查失败：{ok}")


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
    db = Path(DB_PATH)
    db.parent.mkdir(parents=True, exist_ok=True)
    tmp = db.with_suffix(db.suffix + ".restore_tmp")
    shutil.copy2(str(backup), str(tmp))
    tmp.replace(db)
    check_sqlite(db)
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
    db = Path(DB_PATH)
    db.parent.mkdir(parents=True, exist_ok=True)
    tmp = db.with_suffix(db.suffix + ".restore_tmp")
    shutil.copy2(str(upload_path), str(tmp))
    tmp.replace(db)
    check_sqlite(db)
    return {
        "status": "success",
        "uploaded_backup": upload_path.name,
        "pre_restore_backup": pre_restore.name,
    }
