"""计算器基类与通用工具。

所有计算器都返回统一结构，前端、导出模块和测试因此可以复用同一套渲染逻辑：

{
    "headline": [{"label", "value", "unit", "note"}],          # 结果页顶部的关键指标卡片
    "tables":   [{"title", "columns", "rows", "note"}],        # 明细表格
    "chart":    {"type", "title", "x_label", "y_label", "scale", "series"},  # 可选图表
    "notes":    ["..."],                                       # 方法与假设说明
    "meta":     {"model", "assumptions", ...}
}
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class FieldOption(BaseModel):
    value: str
    label: str


class InputField(BaseModel):
    """前端据此动态生成表单控件。"""

    name: str
    label: str
    type: str = "number"  # number | integer | text | select
    unit: str = ""
    description: str = ""
    required: bool = True
    min: float | None = None
    max: float | None = None
    step: float | None = None
    default: Any = None
    options: list[FieldOption] = Field(default_factory=list)
    placeholder: str = ""
    visible_when: dict[str, Any] | None = None  # {"field": "x", "values": ["a", "b"]}


class CalculatorInfo(BaseModel):
    id: str
    name: str
    short_name: str
    category: str
    description: str
    formula_summary: str = ""
    standards: list[str] = Field(default_factory=list)
    input_fields: list[InputField] = Field(default_factory=list)


class CalculationError(ValueError):
    """输入不合法或计算条件不满足，路由层转换为 HTTP 400。"""


def sig(value: Any, digits: int = 6) -> Any:
    """保留有效数字，保证 JSON 可序列化（inf/nan 转成字符串）。"""
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isinf(v):
        return "∞" if v > 0 else "-∞"
    if math.isnan(v):
        return "—"
    if v == 0:
        return 0
    return float(f"{v:.{digits}g}")


class BaseCalculator(ABC):
    @property
    @abstractmethod
    def info(self) -> CalculatorInfo:
        """计算器元信息（含表单定义）。"""

    @abstractmethod
    def calculate(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """执行计算并返回统一结构的结果。"""

    def example_inputs(self) -> dict[str, Any]:
        return {field.name: field.default for field in self.info.input_fields if field.default is not None}

    # ---------------------------------------------------------------- 输入校验
    def validate(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(inputs, dict):
            raise CalculationError("inputs 必须是对象")

        cleaned: dict[str, Any] = {}
        errors: list[str] = []

        for field in self.info.input_fields:
            value = inputs.get(field.name)
            if isinstance(value, str):
                value = value.strip()

            # 条件字段：控件的可见性由 visible_when 决定，不可见时整项跳过（含必填校验）
            if field.visible_when:
                controller = field.visible_when.get("field")
                expected = field.visible_when.get("values")
                actual = cleaned.get(controller)
                if actual is None:
                    actual = inputs.get(controller)
                    if isinstance(actual, str):
                        actual = actual.strip()
                if expected is not None and str(actual) not in [str(item) for item in expected]:
                    continue

            if value is None or value == "":
                if field.default is not None and field.default != "":
                    value = field.default  # 未显式传参时采用表单默认值
                elif field.required:
                    errors.append(f"{field.label}为必填项")
                    continue
                else:
                    continue

            if field.type == "number":
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    errors.append(f"{field.label}必须是数字")
                    continue
                if not math.isfinite(value):
                    errors.append(f"{field.label}必须是有限数字")
                    continue
            elif field.type == "integer":
                try:
                    parsed = float(value)
                except (TypeError, ValueError):
                    errors.append(f"{field.label}必须是整数")
                    continue
                if not parsed.is_integer():
                    errors.append(f"{field.label}必须是整数")
                    continue
                value = int(parsed)
            elif field.type == "select":
                str_value = str(value)
                allowed = [option.value for option in field.options]
                if allowed and str_value not in allowed:
                    errors.append(f"{field.label}的取值必须是 {', '.join(allowed)} 之一")
                    continue
                value = str_value
            elif field.type == "text":
                value = str(value)

            if field.type in {"number", "integer"}:
                if field.min is not None and value < field.min:
                    errors.append(f"{field.label}不得小于 {field.min}")
                    continue
                if field.max is not None and value > field.max:
                    errors.append(f"{field.label}不得大于 {field.max}")
                    continue

            cleaned[field.name] = value

        if errors:
            raise CalculationError("；".join(errors))

        return cleaned


def table(title: str, columns: list[str], rows: list[list[Any]], note: str = "") -> dict[str, Any]:
    return {
        "title": title,
        "columns": columns,
        "rows": [[sig(cell) if isinstance(cell, (int, float)) else cell for cell in row] for row in rows],
        "note": note,
    }


def headline_item(label: str, value: Any, unit: str = "", note: str = "") -> dict[str, Any]:
    return {"label": label, "value": sig(value) if isinstance(value, (int, float)) else value, "unit": unit, "note": note}


def series(name: str, points: list[list[Any]]) -> dict[str, Any]:
    cleaned = []
    for x, y in points:
        if isinstance(y, str):
            continue
        if x is None or y is None:
            continue
        cleaned.append([sig(x), sig(y)])
    return {"name": name, "points": cleaned}
