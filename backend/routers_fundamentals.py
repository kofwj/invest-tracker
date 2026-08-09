"""基本面体检路由：K线页下方按代码查四块体检（估值/盈利/杠杆/现金）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

try:
    from .fundamentals import build_fundamental_check
except ImportError:
    from fundamentals import build_fundamental_check

router = APIRouter()


@router.get("/analysis/{code}")
def fundamental_check(code: str):
    try:
        data = build_fundamental_check(code)
    except Exception as exc:  # 数据源偶发失败不应 500
        raise HTTPException(status_code=502, detail=f"基本面数据获取失败：{exc}") from exc
    return data