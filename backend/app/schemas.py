"""请求/响应模型。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=255, description="登录邮箱")
    username: str = Field("", max_length=64, description="显示名，留空则取邮箱前缀")
    password: str = Field(..., min_length=8, max_length=128, description="口令，至少 8 位")

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("邮箱格式不正确")
        return value

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("口令至少 8 位")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    is_premium: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class QuotaOut(BaseModel):
    daily_limit: int | None
    used: int
    remaining: int | None
    unlimited: bool
    tier: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut
    quota: QuotaOut


class MeResponse(BaseModel):
    authenticated: bool
    user: UserOut | None = None
    quota: QuotaOut


class CalculateRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class CalculationRecord(BaseModel):
    id: int | None = None
    calculator_id: str
    calculator_name: str
    inputs: dict[str, Any]
    result: dict[str, Any]
    created_at: datetime


class CalculateResponse(BaseModel):
    record_id: int | None
    calculator_id: str
    calculator_name: str
    created_at: datetime
    inputs: dict[str, Any]
    result: dict[str, Any]
    quota: QuotaOut


class ExportRequest(BaseModel):
    format: Literal["csv", "xlsx", "json"] = "csv"
    calculator_id: str = "custom"
    calculator_name: str = "可靠性计算结果"
    inputs: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)

    @field_validator("result")
    @classmethod
    def _check_result(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("result 不能为空")
        return value
