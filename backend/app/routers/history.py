"""历史记录路由：查询、查看、删除与批量导出。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_user
from ..exporting import render_history
from ..models import Calculation, User

router = APIRouter()


def _to_dict(record: Calculation) -> dict:
    return {
        "id": record.id,
        "calculator_id": record.calculator_id,
        "calculator_name": record.calculator_name,
        "summary": record.summary,
        "inputs": json.loads(record.inputs_json or "{}"),
        "result": json.loads(record.result_json or "{}"),
        "created_at": record.created_at or datetime.now(timezone.utc),
    }


def _user_records(db: Session, user: User, limit: int = 200) -> list[Calculation]:
    return list(
        db.execute(
            select(Calculation)
            .where(Calculation.user_id == user.id)
            .order_by(Calculation.created_at.desc(), Calculation.id.desc())
            .limit(limit)
        ).scalars()
    )


@router.get("/export")
def export_history(
    format: Literal["csv", "xlsx", "json"] = Query("xlsx", description="导出格式"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    records = [_to_dict(item) for item in _user_records(db, user, limit=500)]
    if not records:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="暂无可导出的历史记录")
    content, media_type, filename = render_history(records, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("")
def list_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    calculator_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    statement = select(Calculation).where(Calculation.user_id == user.id)
    if calculator_id:
        statement = statement.where(Calculation.calculator_id == calculator_id)
    statement = statement.order_by(Calculation.created_at.desc(), Calculation.id.desc()).offset(offset).limit(limit)
    records = [_to_dict(item) for item in db.execute(statement).scalars()]
    return {"records": records, "count": len(records)}


@router.get("/{record_id}")
def get_record(record_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    record = db.get(Calculation, record_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    return _to_dict(record)


@router.delete("/{record_id}")
def delete_record(record_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    record = db.get(Calculation, record_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")
    db.delete(record)
    db.commit()
    return {"ok": True, "deleted": record_id}
