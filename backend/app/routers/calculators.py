"""计算器路由：元信息、示例输入、执行计算。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..calculators import get_calculator, list_calculators
from ..calculators.base import CalculationError
from ..database import get_db
from ..deps import enforce_quota, get_optional_user, quota_key, quota_snapshot, record_usage
from ..models import Calculation, User
from ..schemas import CalculateRequest, CalculateResponse

logger = logging.getLogger("semirel.calculators")
router = APIRouter()


@router.get("/calculators")
def list_all_calculators():
    return {"calculators": [calc.info.model_dump() for calc in list_calculators()]}


@router.get("/calculators/{calculator_id}")
def calculator_detail(calculator_id: str):
    try:
        calculator = get_calculator(calculator_id)
    except CalculationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return calculator.info.model_dump()


@router.get("/calculators/{calculator_id}/example")
def calculator_example(calculator_id: str):
    try:
        calculator = get_calculator(calculator_id)
    except CalculationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"inputs": calculator.example_inputs()}


@router.post("/calculators/{calculator_id}/calculate", response_model=CalculateResponse)
def calculate(
    calculator_id: str,
    payload: CalculateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    try:
        calculator = get_calculator(calculator_id)
    except CalculationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    key = quota_key(request, user)
    enforce_quota(db, key, user)

    try:
        result = calculator.calculate(payload.inputs)
    except CalculationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # 兜底：避免把堆栈直接抛给前端
        logger.exception("计算失败: %s", calculator_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"计算失败：{exc}") from exc

    created_at = datetime.now(timezone.utc)
    record_id: int | None = None
    summary = _summarize(result)

    if user is not None:
        record = Calculation(
            user_id=user.id,
            quota_key=key,
            calculator_id=calculator_id,
            calculator_name=calculator.info.name,
            summary=summary,
            inputs_json=json.dumps(payload.inputs, ensure_ascii=False),
            result_json=json.dumps(result, ensure_ascii=False),
            created_at=created_at,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        record_id = record.id

    record_usage(db, key)
    quota = quota_snapshot(db, key, user)

    return CalculateResponse(
        record_id=record_id,
        calculator_id=calculator_id,
        calculator_name=calculator.info.name,
        created_at=created_at,
        inputs=payload.inputs,
        result=result,
        quota=quota,
    )


def _summarize(result: dict) -> str:
    parts = []
    for item in result.get("headline", [])[:3]:
        label = item.get("label", "")
        value = item.get("value", "")
        unit = item.get("unit", "")
        parts.append(f"{label} {value}{unit}")
    return "；".join(parts)[:255]
