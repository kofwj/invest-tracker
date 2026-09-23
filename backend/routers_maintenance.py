import csv
import io
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

try:
    from .csv_utils import _csv_sanitize_cell, create_safety_backup
    from .database import BACKUP_DIR, DB_PATH, LOCAL_TZ, db_session, open_db
except ImportError:
    from csv_utils import _csv_sanitize_cell, create_safety_backup
    from database import BACKUP_DIR, DB_PATH, LOCAL_TZ, db_session, open_db

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
        version_row = source.execute(
            "SELECT value FROM settings WHERE key='schema_version'"
        ).fetchone()
        if version_row is not None:
            raw_version = version_row["value"] if isinstance(version_row, sqlite3.Row) else version_row[0]
            try:
                candidate_version = int(str(raw_version).strip())
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="备份 schema_version 无效") from exc
            if candidate_version < 0:
                raise HTTPException(status_code=400, detail="备份 schema_version 不能为负数")
        else:
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

    try:
        check_sqlite(upload_path)
        pre_restore = Path(create_safety_backup("before_restore_upload"))
        restore_sqlite(upload_path, rollback_source=pre_restore)
    except Exception:
        upload_path.unlink(missing_ok=True)
        raise
    return {
        "status": "success",
        "uploaded_backup": upload_path.name,
        "pre_restore_backup": pre_restore.name,
    }


# ---------------------------------------------------------------------------
# 一键全量导出
#
# 只读：读 6 张表流式写成 CSV + 用 sqlite3 backup API 取一份数据库一致性副本，
# 再加一份 README，打包成一个 zip。全程不写任何业务数据。
# ---------------------------------------------------------------------------

EXPORT_CSV_SPECS = [
    ("transactions.csv", "transactions", "ORDER BY date DESC, id DESC"),
    ("holdings.csv", "holdings", "ORDER BY code"),
    ("deposits.csv", "deposits", "ORDER BY COALESCE(due_date, '9999-12-31'), id"),
    ("daily_snapshots.csv", "daily_snapshots", "ORDER BY date, id"),
    ("portfolio_cash_flows.csv", "portfolio_cash_flows", "ORDER BY date, id"),
    ("cash_flows.csv", "cash_flows", "ORDER BY date, id"),
]

# 每个字段一句中文说明，用于 README.txt；列名即数据库原始字段名。
EXPORT_COLUMN_NOTES = {
    "transactions": {
        "id": "交易记录自增编号（仅本库内部定位用）",
        "date": "交易日期（YYYY-MM-DD）",
        "code": "证券/基金代码，场外基金以 f 开头（如 f004388）",
        "name": "证券/基金名称",
        "category": "大类分类（A股权益/A股ETF/港股ETF/债基/黄金/REITs/其他）",
        "account": "证券账户名（默认华泰证券）",
        "direction": "交易方向（买入/卖出/分红/分红再投资/申购待确认/待确认申购）",
        "quantity": "数量（股数或基金份额，场外申购未确认时为 0）",
        "price": "成交单价（场外基金为申购/确认净值）",
        "amount": "成交金额（不含手续费）",
        "fee": "手续费/费用",
        "remark": "备注",
    },
    "holdings": {
        "id": "持仓记录自增编号（仅本库内部定位用）",
        "code": "证券/基金代码",
        "name": "证券/基金名称",
        "category": "大类分类，决定大类配置与再平衡口径",
        "quantity": "当前持有数量（股/份）",
        "avg_cost": "持仓均价（成本摊薄口径见程序内算法）",
        "diluted_cost": "摊薄成本价（均价扣减累计分红后的成本）",
        "total_dividend": "该持仓累计收到的分红金额",
        "last_price": "最近一次同步/手工填写的市价",
        "updated_at": "该持仓最近一次重算/更新时间",
        "expected_return": "预期年化收益率（小数，如 0.05 表示 5%）",
        "trailing_return_1y": "近一年实际收益率（小数），数据不足时为空",
        "trailing_return_1y_source": "近一年收益率的来源（如 kline/akshare）",
        "trailing_return_1y_updated_at": "近一年收益率最近更新时间",
    },
    "deposits": {
        "id": "存款记录自增编号",
        "bank_name": "银行名称",
        "amount": "存款本金",
        "interest_rate": "年利率（小数，如 0.025 表示 2.5%）",
        "start_date": "起存日（YYYY-MM-DD）",
        "due_date": "到期日（YYYY-MM-DD）",
        "remark": "备注",
    },
    "daily_snapshots": {
        "id": "快照自增编号",
        "date": "快照日期（YYYY-MM-DD，一天一条）",
        "total_assets": "当日总资产合计",
        "total_market_value": "当日持仓市值合计",
        "bank_balance": "当日银行存款余额",
        "securities_cash": "当日证券账户可用现金",
        "pending_purchase": "当日场外申购在途金额",
        "total_profit": "当日累计收益（按当日成本口径计算）",
        "lifetime_profit": "历史累计净收益（含已实现收益与分红）",
        "holdings_count": "当日持仓只数",
        "equity_mv": "当日权益类（A股权益/港股ETF 等）市值",
        "bond_mv": "当日债券类（债基）市值",
        "reit_mv": "当日 REITs 市值",
        "created_at": "快照写入时间",
        "unpriced_count": "当日缺市价（按 0 计市值）的持仓只数",
        "price_date": "所用市价的价格日期（用于判断价格新鲜度）",
        "price_stale": "市价是否过期（1=使用过期价，0=新鲜）",
        "manual_price_count": "当日含人工填写市价的持仓只数",
    },
    "portfolio_cash_flows": {
        "id": "记录自增编号",
        "date": "资金进出发生日期（YYYY-MM-DD）",
        "flow_type": "类型（投入=外部资金转入组合，取出=转出组合）",
        "amount": "金额（正数；方向由 flow_type 决定）",
        "source": "来源（手工录入/系统建议/导入等）",
        "remark": "备注",
        "created_at": "记录写入时间",
    },
    "cash_flows": {
        "id": "记录自增编号",
        "date": "资金变动日期（YYYY-MM-DD）",
        "account": "证券账户名",
        "flow_type": "类型（银证转入/银证转出）",
        "amount": "变动金额（正数）",
        "balance_before": "变动前账户现金余额",
        "balance_after": "变动后账户现金余额",
        "remark": "备注",
        "created_at": "记录写入时间",
    },
}


def export_table_csv(conn, table, order_by):
    """把一张表流式写成 utf-8-sig 的 CSV（Excel 打开中文不乱码），返回 (列名, 字节)。"""
    columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if not columns:
        raise HTTPException(status_code=500, detail=f"导出失败：账本缺少数据表 {table}")
    # 公式注入防护与 /transactions/export 等既有导出保持同一处理。
    quoted = ", ".join(f'"{col}"' for col in columns)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    # 逐行写，不把整表 fetchall 进内存。
    for row in conn.execute(f"SELECT {quoted} FROM {table} {order_by}"):
        writer.writerow([_csv_sanitize_cell(row[col]) for col in columns])
    return columns, ("\ufeff" + out.getvalue()).encode("utf-8")


def export_db_snapshot_bytes(conn):
    """用 sqlite3 backup API 取一份一致性副本（WAL 下直接复制文件会拿到半成品）。"""
    payload = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmpdir:
        snapshot = Path(tmpdir) / "invest.db"
        # 显式 close：python 的 `with sqlite3.connect()` 只提交不关闭，
        # WAL 没 checkpoint 完就按文件读会漏掉最后几次写入。
        dst = sqlite3.connect(str(snapshot))
        try:
            conn.backup(dst)
            dst.commit()
        finally:
            dst.close()
        with snapshot.open("rb") as fh:
            payload.write(fh.read())
    payload.seek(0)
    return payload.getvalue()


def build_export_readme(export_ts, exported):
    """exported: [(文件名, 表名, 列名列表)]，按各表实际列生成逐列说明。"""
    tz_name = getattr(export_ts.tzinfo, "key", None) or str(export_ts.tzinfo or "")
    lines = [
        "投资账本全量导出（底稿）",
        "=" * 60,
        f"导出时间：{export_ts.strftime('%Y-%m-%d %H:%M:%S')}（时区 {tz_name}）",
        "导出方式：只读导出，未修改任何账本数据。",
        "",
        "文件清单：",
    ]
    for filename, table, _columns in exported:
        lines.append(f"  {filename:<24} 对应数据表 {table}")
    lines += [
        f"  {'invest.db':<24} 主库的一致性副本（sqlite3 在线 backup API，WAL 下也一致）",
        f"  {'README.txt':<24} 本说明",
        "",
        "重要提示：",
        "  这份 zip 只是底稿（备份/留档/给 Excel 看），恢复请用设置页的备份/恢复功能",
        "  （POST /maintenance/restore 或 /maintenance/restore-upload），不要把 invest.db",
        "  直接覆盖到 data/invest.db —— 那样会绕过版本迁移与完整性校验，容易把库弄坏。",
        "  CSV 也不保证能被程序完整还原（缺 id 关联，且部分表没有导入入口）。",
        "",
        "CSV 编码：UTF-8 带 BOM（utf-8-sig），Excel/WPS 双击打开中文不乱码。",
        "列名说明：CSV 第一行是表头，用数据库原始字段名；逐列含义见下面各节。",
        "",
        "各文件列含义：",
        "",
    ]
    for filename, table, columns in exported:
        notes = EXPORT_COLUMN_NOTES.get(table, {})
        lines.append(f"[{filename}]（表 {table}）")
        for col in columns:
            lines.append(f"  {col:<32} {notes.get(col, '数据库原样字段')}")
        lines.append("")
    return "\r\n".join(lines) + "\r\n"


@router.get("/maintenance/export-all")
def export_all():
    """一键全量导出：6 张表 CSV + 主库一致性副本 + README，打包成 zip 下载。"""
    export_ts = datetime.now(LOCAL_TZ)
    exported = []
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as bundle:
        with db_session(row_factory=sqlite3.Row) as conn:
            for filename, table, order_by in EXPORT_CSV_SPECS:
                columns, data = export_table_csv(conn, table, order_by)
                bundle.writestr(filename, data)
                exported.append((filename, table, columns))
            bundle.writestr("invest.db", export_db_snapshot_bytes(conn))
        bundle.writestr("README.txt", build_export_readme(export_ts, exported))
    filename = f"invest-tracker-export-{export_ts.strftime('%Y%m%d')}.zip"
    return Response(
        content=payload.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
