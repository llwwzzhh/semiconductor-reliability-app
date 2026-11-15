"""导出路由：把当前计算结果导出为 CSV / XLSX / JSON。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Response

from ..exporting import render_single
from ..schemas import ExportRequest

router = APIRouter()


@router.post("/calculation")
def export_calculation(payload: ExportRequest):
    record = {
        "id": "当前结果",
        "calculator_id": payload.calculator_id,
        "calculator_name": payload.calculator_name,
        "inputs": payload.inputs,
        "result": payload.result,
        "created_at": datetime.now(timezone.utc),
    }
    content, media_type, filename = render_single(record, payload.format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
