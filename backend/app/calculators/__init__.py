"""计算器注册表：新增计算器时只需在此登记。"""

from __future__ import annotations

from .base import (
    BaseCalculator,
    CalculationError,
    CalculatorInfo,
    FieldOption,
    InputField,
    headline_item,
    series,
    sig,
    table,
)
from .duane import DuaneCalculator
from .mtbf import MTBFCalculator
from .sample_size import SampleSizeCalculator

CALCULATORS: dict[str, BaseCalculator] = {
    "mtbf": MTBFCalculator(),
    "duane": DuaneCalculator(),
    "sample_size": SampleSizeCalculator(),
}


def get_calculator(calculator_id: str) -> BaseCalculator:
    try:
        return CALCULATORS[calculator_id]
    except KeyError as exc:
        raise CalculationError(f"未知的计算器：{calculator_id}") from exc


def list_calculators() -> list[BaseCalculator]:
    return list(CALCULATORS.values())
