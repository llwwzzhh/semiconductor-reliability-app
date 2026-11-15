"""试验样本量计算器。

四种常用可靠性演示试验方案：

1. 成功运行试验（零失效，二项分布）
       n = ceil( ln(1-C) / ln(R) )
2. 二项试验（允许 c 个失效）
       n 为使 P(X ≤ c | q = 1-R) ≤ 1-C 的最小样本量，二分搜索 + 二项精确 CDF
3. 指数定时截尾（MTBF 演示，时间截止）
       T = θ0 · χ²(1-C, 2c+2) / 2
4. 指数定数截尾（MTBF 演示，失效截止）
       T = θ0 · χ²(1-C, 2c) / 2
   给出单台试验时长 d 时，所需样本量 n = ceil(T / d)。
"""

from __future__ import annotations

import math
from typing import Any

from scipy import stats

from .base import (
    BaseCalculator,
    CalculationError,
    CalculatorInfo,
    FieldOption,
    InputField,
    headline_item,
    sig,
    table,
)

_CONFIDENCE_OPTIONS = [
    FieldOption(value="60", label="60%"),
    FieldOption(value="70", label="70%"),
    FieldOption(value="80", label="80%"),
    FieldOption(value="90", label="90%"),
    FieldOption(value="95", label="95%"),
    FieldOption(value="99", label="99%"),
]

_TEST_TYPES = [
    FieldOption(value="success_run", label="成功运行试验（零失效，二项）"),
    FieldOption(value="binomial_failures", label="二项试验（允许失效）"),
    FieldOption(value="exponential_time", label="指数定时截尾（时间截止）"),
    FieldOption(value="exponential_failure", label="指数定数截尾（失效截止）"),
]

_BINOMIAL_TYPES = {"success_run", "binomial_failures"}
_EXPONENTIAL_TYPES = {"exponential_time", "exponential_failure"}
_MAX_UNITS = 2_000_000


class SampleSizeCalculator(BaseCalculator):
    @property
    def info(self) -> CalculatorInfo:
        return CalculatorInfo(
            id="sample_size",
            name="试验样本量计算",
            short_name="样本量",
            category="试验设计",
            description="按目标可靠度或目标 MTBF、置信水平与允许失效数，计算可靠性演示试验所需的样本量与试验时间。",
            formula_summary="零失效 n=ln(1-C)/ln(R)；定时截尾 T=θ0·χ²(1-C,2c+2)/2；定数截尾 T=θ0·χ²(1-C,2c)/2",
            standards=["MIL-HDBK-781A", "IEC 61124", "GJB 899A"],
            input_fields=[
                InputField(
                    name="test_type",
                    label="试验类型",
                    type="select",
                    default="success_run",
                    options=_TEST_TYPES,
                    description="二项类按可靠度目标，指数类按 MTBF 目标",
                ),
                InputField(
                    name="target_reliability",
                    label="目标可靠度 R",
                    type="number",
                    min=0.0001,
                    max=0.9999,
                    step=0.001,
                    default=0.9,
                    description="0~1 之间，例如 0.9 表示 90% 可靠度",
                    visible_when={"field": "test_type", "values": ["success_run", "binomial_failures"]},
                ),
                InputField(
                    name="target_mtbf",
                    label="目标 MTBF θ0",
                    type="number",
                    unit="h",
                    min=0.0001,
                    default=100000,
                    description="需要在给定置信度下演示的最低 MTBF",
                    visible_when={"field": "test_type", "values": ["exponential_time", "exponential_failure"]},
                ),
                InputField(
                    name="allowed_failures",
                    label="允许失效数 c",
                    type="integer",
                    min=0,
                    max=100,
                    default=0,
                    description="试验中允许出现的失效数量，0 表示零失效方案",
                    visible_when={
                        "field": "test_type",
                        "values": ["binomial_failures", "exponential_time", "exponential_failure"],
                    },
                ),
                InputField(
                    name="test_duration",
                    label="单台试验时长 d",
                    type="number",
                    unit="h",
                    min=0,
                    required=False,
                    description="指数类方案用于把总试验时间换算成样本数；留空则只输出总时间",
                    visible_when={"field": "test_type", "values": ["exponential_time", "exponential_failure"]},
                ),
                InputField(
                    name="confidence_level",
                    label="置信水平",
                    type="select",
                    default="90",
                    options=_CONFIDENCE_OPTIONS,
                ),
            ],
        )

    def example_inputs(self) -> dict[str, Any]:
        return {
            "test_type": "success_run",
            "target_reliability": 0.9,
            "allowed_failures": 0,
            "confidence_level": "90",
        }

    # ------------------------------------------------------------------ 计算
    def calculate(self, inputs: dict[str, Any]) -> dict[str, Any]:
        values = self.validate(inputs)
        test_type = values["test_type"]
        conf_pct = float(values["confidence_level"])
        conf = conf_pct / 100.0
        allowed = int(values.get("allowed_failures") or 0)

        if test_type == "success_run":
            allowed = 0
        if test_type in _BINOMIAL_TYPES:
            reliability = float(values["target_reliability"])
            if not 0 < reliability < 1:
                raise CalculationError("目标可靠度必须介于 0 与 1 之间（不含端点）")
            units, extra_note = self._binomial_units(reliability, conf, allowed)
            total_time = None
            per_unit_time = None
            method_label = "成功运行 / 二项试验"
            headline = [
                headline_item("所需样本量 n", units, "台", f"零失效" if allowed == 0 else f"允许 {allowed} 个失效"),
                headline_item("目标可靠度 R", reliability, "", f"{reliability * 100:.4g}%"),
                headline_item("置信水平", conf_pct, "%"),
                headline_item("判定准则", f"n={units} 台试验中失效数 ≤ {allowed}", ""),
            ]
            detail_rows = [
                ["试验类型", "成功运行 / 二项试验", "—"],
                ["所需样本量 n", units, "台"],
                ["允许失效数 c", allowed, "个"],
                ["目标可靠度 R", reliability, "—"],
                ["置信水平", conf_pct, "%"],
                ["判定准则", f"全部 {units} 台（或失效数 ≤ {allowed}）通过则接受", "—"],
            ]
            notes = [
                "二项方案要求试验结束时每台样品均未失效（零失效方案），或失效数不超过允许值。",
                "样本量按二项精确分布求解，P(X ≤ c | q=1-R) ≤ 1-C 时即达到要求的置信度。",
                extra_note,
            ]
        else:
            target_mtbf = float(values["target_mtbf"])
            if target_mtbf <= 0:
                raise CalculationError("目标 MTBF 必须大于 0")
            if test_type == "exponential_failure" and allowed == 0:
                raise CalculationError("定数截尾方案至少需要允许 1 个失效；零失效请使用定时截尾方案")

            if test_type == "exponential_time":
                df = 2 * allowed + 2
                total_time = 0.5 * target_mtbf * float(stats.chi2.ppf(conf, df))
                method_label = "指数定时截尾（时间截止）"
                method_note = "定时截尾在累计试验时间 T 处停止，零失效方案对应自由度 2c+2。"
            else:
                df = 2 * allowed
                total_time = 0.5 * target_mtbf * float(stats.chi2.ppf(conf, df))
                method_label = "指数定数截尾（失效截止）"
                method_note = "定数截尾在出现第 c 个失效时停止，自由度为 2c。"

            duration = values.get("test_duration")
            if duration:
                per_unit_time = float(duration)
                units = math.ceil(total_time / per_unit_time)
            else:
                per_unit_time = None
                units = None

            headline = [
                headline_item("所需总试验时间", total_time, "器件·h", f"{conf_pct:g}% 置信"),
                headline_item("所需样本量 n", units if units is not None else "—", "台", "按单台时长换算" if units else "未填单台时长"),
                headline_item("目标 MTBF θ0", target_mtbf, "h"),
                headline_item("允许失效数 c", allowed, "个"),
            ]
            detail_rows = [
                ["试验类型", method_label, "—"],
                ["目标 MTBF θ0", target_mtbf, "h"],
                ["允许失效数 c", allowed, "个"],
                ["置信水平", conf_pct, "%"],
                ["所需总试验时间 T", total_time, "器件·h"],
                ["单台试验时长 d", per_unit_time if per_unit_time else "—", "h"],
                ["所需样本量 n", units if units is not None else "—", "台"],
                ["演示 MTBF 倍数 T/θ0", total_time / target_mtbf, "倍"],
            ]
            notes = [
                method_note,
                f"若单台时长确定为 {per_unit_time:g} h，需要 ceil(T/d) = {units} 台同时或累计投入。" if per_unit_time and units else "填写单台试验时长可把总试验时间换算为样本数量。",
                "上述方案假定失效率恒定（指数分布）；若存在多个失效模式，建议按失效模式分列并预留额外样本。",
            ]

        # ------------------------------------------------------------ 权衡表
        tradeoff_rows = []
        for c in range(0, 6):
            if test_type in _BINOMIAL_TYPES:
                reliability = float(values["target_reliability"])
                units_c, _ = self._binomial_units(reliability, conf, c)
                tradeoff_rows.append([c, units_c, "—", "—"])
            else:
                if test_type == "exponential_failure" and c == 0:
                    tradeoff_rows.append([c, "不适用", "不适用", "—"])
                    continue
                df_c = 2 * c + 2 if test_type == "exponential_time" else 2 * c
                total_c = 0.5 * float(values["target_mtbf"]) * float(stats.chi2.ppf(conf, df_c))
                units_c = math.ceil(total_c / float(values["test_duration"])) if values.get("test_duration") else None
                tradeoff_rows.append(
                    [c, units_c if units_c is not None else "—", total_c, total_c / float(values["target_mtbf"])]
                )

        if test_type in _BINOMIAL_TYPES:
            columns = ["允许失效数 c", "所需样本量 n（台）", "总试验时间", "备注"]
            note = f"置信水平 {conf_pct:g}%、目标可靠度 {float(values['target_reliability']):.4g} 下的对照表。"
        else:
            columns = ["允许失效数 c", "所需样本量 n（台）", "所需总试验时间 T（器件·h）", "T/θ0 倍数"]
            note = f"置信水平 {conf_pct:g}%、目标 MTBF {float(values['target_mtbf']):.4g} h 下的对照表；样本量按所填单台时长换算。"

        tables = [
            table("推荐试验方案", ["项目", "数值", "单位"], detail_rows),
            table("不同允许失效数的方案对比", columns, tradeoff_rows, note=note),
        ]

        return {
            "headline": headline,
            "tables": tables,
            "chart": None,
            "notes": notes,
            "meta": {"model": method_label, "confidence_level": conf_pct},
        }

    # -------------------------------------------------------------- 二分求解
    def _binomial_units(self, reliability: float, conf: float, allowed: int) -> tuple[int, str]:
        rejection_target = 1.0 - conf
        q = 1.0 - reliability

        if allowed == 0:
            # 闭式解：R^n ≤ 1-C
            units = math.ceil(math.log(rejection_target) / math.log(reliability))
            return max(units, 1), "零失效方案采用闭式解 n = ln(1-C)/ln(R)。"

        def satisfied(n: int) -> bool:
            return float(stats.binom.cdf(allowed, n, q)) <= rejection_target

        if not satisfied(_MAX_UNITS):
            raise CalculationError(
                f"允许 {allowed} 个失效时所需样本量超过 {_MAX_UNITS:,}，请放宽目标可靠度或提高允许失效数"
            )

        low = max(allowed + 1, 1)
        high = low
        while not satisfied(high):
            low = high
            high *= 2
            if high > _MAX_UNITS:
                high = _MAX_UNITS
                break
        # high 已满足，binary search 最小 n
        while low + 1 < high:
            mid = (low + high) // 2
            if satisfied(mid):
                high = mid
            else:
                low = mid
        return high, f"允许 {allowed} 个失效时由二项精确 CDF 二分求解，判定阈值 1-C = {rejection_target:.4g}。"
