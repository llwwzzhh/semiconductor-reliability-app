"""MTBF / 失效率计算器。

数学模型（指数分布，恒定失效率）：
    λ = r / T                     r 为失效数，T 为总器件小时（Σ 样本数×时长）
    MTBF = 1 / λ = T / r
    FIT = λ × 10^9               失效数 / 十亿器件小时（JEDEC JEP150 口径）
    R(t) = exp(-t / MTBF)
置信区间（卡方精确法）：
    定时截尾：MTBF 双侧下限 = 2T/χ²(1-α/2, 2r+2)，上限 = 2T/χ²(α/2, 2r)
    定数截尾：上下限自由度均为 2r
    单侧下限：2T/χ²(1-α, 2r+2)（定时截尾）/ 2T/χ²(1-α, 2r)（定数截尾）
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
    series,
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

_HOURS_PER_YEAR = 365.25 * 24


class MTBFCalculator(BaseCalculator):
    @property
    def info(self) -> CalculatorInfo:
        return CalculatorInfo(
            id="mtbf",
            name="MTBF 与失效率",
            short_name="MTBF",
            category="基础指标",
            description="由试验数据（失效数与总器件小时）或已知失效率计算 MTBF、FIT，给出卡方精确置信区间、任务时间可靠度与 Bx 寿命。",
            formula_summary="MTBF = T/r；λ = r/T；FIT = λ×10⁹；R(t) = e^(-t/MTBF)",
            standards=["MIL-HDBK-781A", "JEDEC JEP150", "IEC 61709"],
            input_fields=[
                InputField(
                    name="data_mode",
                    label="数据来源",
                    type="select",
                    default="test_data",
                    description="用试验数据反推，或直接输入已知失效率",
                    options=[
                        FieldOption(value="test_data", label="试验数据（失效数 + 总器件小时）"),
                        FieldOption(value="failure_rate", label="已知失效率"),
                    ],
                ),
                InputField(
                    name="num_failures",
                    label="失效数 r",
                    type="integer",
                    min=0,
                    max=100000,
                    default=2,
                    description="试验期间观察到的失效数量，0 表示零失效",
                    visible_when={"field": "data_mode", "values": ["test_data"]},
                ),
                InputField(
                    name="total_test_time",
                    label="总器件小时 T",
                    type="number",
                    unit="h",
                    min=0.000001,
                    default=200000,
                    description="Σ(样本数 × 各自试验时长)，即器件·小时总和",
                    visible_when={"field": "data_mode", "values": ["test_data"]},
                ),
                InputField(
                    name="termination",
                    label="截尾方式",
                    type="select",
                    default="time_terminated",
                    description="定时截尾：到达设定时间停止；定数截尾：失效数达到 r 时停止",
                    options=[
                        FieldOption(value="time_terminated", label="定时截尾（时间截止）"),
                        FieldOption(value="failure_terminated", label="定数截尾（失效截止）"),
                    ],
                    visible_when={"field": "data_mode", "values": ["test_data"]},
                ),
                InputField(
                    name="failure_rate",
                    label="失效率 λ",
                    type="number",
                    min=0.000000001,
                    default=50,
                    description="已知失效率数值，单位由下一项指定",
                    visible_when={"field": "data_mode", "values": ["failure_rate"]},
                ),
                InputField(
                    name="failure_rate_unit",
                    label="失效率单位",
                    type="select",
                    default="fit",
                    options=[
                        FieldOption(value="fit", label="FIT（失效数/10⁹ 器件小时）"),
                        FieldOption(value="per_1e6_hours", label="失效数/10⁶ 器件小时"),
                        FieldOption(value="per_hour", label="失效数/器件小时"),
                    ],
                    visible_when={"field": "data_mode", "values": ["failure_rate"]},
                ),
                InputField(
                    name="confidence_level",
                    label="置信水平",
                    type="select",
                    default="90",
                    options=_CONFIDENCE_OPTIONS,
                ),
                InputField(
                    name="mission_time",
                    label="任务时间 t",
                    type="number",
                    unit="h",
                    min=0,
                    default=10000,
                    required=False,
                    description="用于计算 R(t)；留空则只输出 MTBF 与区间",
                ),
            ],
        )

    # ------------------------------------------------------------------ 计算
    def calculate(self, inputs: dict[str, Any]) -> dict[str, Any]:
        values = self.validate(inputs)
        conf_pct = float(values["confidence_level"])
        conf = conf_pct / 100.0
        alpha = 1.0 - conf
        mission = values.get("mission_time")

        failures: int | None
        total_time: float | None
        termination: str | None
        intervals: dict[str, Any] | None = None
        notes: list[str] = []

        if values["data_mode"] == "test_data":
            failures = int(values["num_failures"])
            total_time = float(values["total_test_time"])
            termination = values.get("termination", "time_terminated")
            if total_time <= 0:
                raise CalculationError("总器件小时必须大于 0")
            if termination == "failure_terminated" and failures == 0:
                raise CalculationError("定数截尾至少需要 1 个失效；零失效数据请选择定时截尾")

            failure_rate = failures / total_time
            mtbf = math.inf if failures == 0 else total_time / failures
            intervals = self._confidence_intervals(failures, total_time, termination, alpha, conf_pct)
            notes.append("置信区间采用卡方精确法，适用于恒定失效率（指数分布）假设下的定时/定数截尾试验。")
        else:
            raw_rate = float(values["failure_rate"])
            unit = values.get("failure_rate_unit", "fit")
            failure_rate = {
                "fit": raw_rate * 1e-9,
                "per_1e6_hours": raw_rate * 1e-6,
                "per_hour": raw_rate,
            }[unit]
            if failure_rate <= 0:
                raise CalculationError("失效率必须大于 0")
            mtbf = 1.0 / failure_rate
            failures = None
            total_time = None
            termination = None
            notes.append("直接指定失效率时无法给出置信区间：区间估计需要失效数与总器件小时（或截尾方式）作为样本信息。")

        fit = failure_rate * 1e9

        # ------------------------------------------------------------ 关键指标
        headline = [
            headline_item("MTBF", mtbf, "h", "点估计"),
            headline_item("MTBF", mtbf / _HOURS_PER_YEAR if math.isfinite(mtbf) else "∞", "年"),
            headline_item("失效率 λ", fit, "FIT"),
            headline_item("平均每 10⁶ 小时失效数", failure_rate * 1e6, "次"),
        ]
        if intervals:
            headline.insert(1, headline_item(f"MTBF 双侧下限（{conf_pct:g}%）", intervals["mtbf_lower_two"], "h"))
            headline.insert(2, headline_item(f"MTBF 单侧下限（{conf_pct:g}%）", intervals["mtbf_lower_one"], "h"))

        # ------------------------------------------------------------ 点估计表
        point_rows = [
            ["失效数 r", failures if failures is not None else "—", "次"],
            ["总器件小时 T", total_time if total_time is not None else "—", "h"],
            ["失效率 λ", failure_rate, "1/h"],
            ["失效率 λ", failure_rate * 1e6, "次/10⁶ h"],
            ["失效率 λ", fit, "FIT"],
            ["MTBF", mtbf, "h"],
            ["MTBF", mtbf / _HOURS_PER_YEAR if math.isfinite(mtbf) else "∞", "年"],
        ]
        tables = [table("点估计", ["指标", "数值", "单位"], point_rows)]

        if intervals:
            rows = [
                [
                    "双侧区间",
                    intervals["mtbf_lower_two"],
                    intervals["mtbf_upper_two"],
                    intervals["fit_upper_two"],
                    f"{conf_pct:g}% 置信，卡方精确法（{termination_label(termination)}）",
                ],
                [
                    "单侧下限",
                    intervals["mtbf_lower_one"],
                    "—",
                    intervals["fit_upper_one"],
                    f"以 {conf_pct:g}% 置信度断言 MTBF 不低于该值",
                ],
            ]
            tables.append(
                table(
                    "置信区间",
                    ["类型", "MTBF 下限 (h)", "MTBF 上限 (h)", "λ 上限 (FIT)", "说明"],
                    rows,
                    note="FIT 上限由 MTBF 下限换算，代表失效率的保守上界。",
                )
            )

        # ------------------------------------------------------ 可靠度与寿命
        if mission is not None:
            reliability = math.exp(-mission / mtbf) if math.isfinite(mtbf) else 1.0
            unreliability = 1.0 - reliability
            tables.append(
                table(
                    "任务时间可靠度",
                    ["项目", "数值", "单位"],
                    [
                        ["任务时间 t", mission, "h"],
                        ["可靠度 R(t)", reliability, "—"],
                        ["失效概率 F(t)", unreliability, "—"],
                        [f"每千台预期失效数（t={mission:g} h）", unreliability * 1000, "台"],
                    ],
                    note="R(t)=exp(-t/MTBF)；批量场景按二项期望近似。",
                )
            )

        if math.isfinite(mtbf):
            tables.append(
                table(
                    "寿命特征（Bx 寿命）",
                    ["特征寿命", "时间 (h)", "对应失效比例"],
                    [
                        ["B1 寿命", bx_life(mtbf, 1), "1%"],
                        ["B10 寿命", bx_life(mtbf, 10), "10%"],
                        ["B50 寿命（中位寿命）", bx_life(mtbf, 50), "50%"],
                    ],
                    note="Bx 寿命 = MTBF × ln(1/(1-x%))，即累计失效达到 x% 的时间。",
                )
            )

        # ------------------------------------------------------------ 可靠度曲线
        chart = None
        if math.isfinite(mtbf):
            t_max = mission * 1.5 if mission else 0
            t_max = max(t_max, mtbf * 3)
            steps = 30
            points_r = []
            points_f = []
            for i in range(steps + 1):
                t = t_max * i / steps
                reliability = math.exp(-t / mtbf)
                points_r.append([t, reliability])
                points_f.append([t, 1 - reliability])
            chart = {
                "type": "line",
                "title": "可靠度衰减曲线",
                "x_label": "时间 (h)",
                "y_label": "概率",
                "scale": "linear",
                "series": [series("可靠度 R(t)", points_r), series("失效概率 F(t)", points_f)],
            }

        notes.append("MTBF 是统计平均值，不代表任一台器件的实际寿命；工程上应与任务时间、置信区间一并使用。")
        if failures == 0:
            notes.append("零失效时 MTBF 点估计为 ∞，工程上应引用单侧置信下限作为保守 MTBF。")

        return {
            "headline": headline,
            "tables": tables,
            "chart": chart,
            "notes": notes,
            "meta": {
                "model": "指数分布（恒定失效率）",
                "confidence_level": conf_pct,
                "termination": termination,
                "data_mode": values["data_mode"],
            },
        }

    # -------------------------------------------------------------- 区间计算
    def _confidence_intervals(
        self, failures: int, total_time: float, termination: str, alpha: float, conf_pct: float
    ) -> dict[str, Any]:
        if termination == "time_terminated":
            df_lower = 2 * failures + 2  # 下限自由度（含失效后继续试验信息）
            df_upper = 2 * failures  # 上限自由度
            df_one = 2 * failures + 2
        else:
            df_lower = 2 * failures
            df_upper = 2 * failures
            df_one = 2 * failures

        chi2_upper_crit = float(stats.chi2.ppf(1 - alpha / 2, df_lower))
        mtbf_lower_two = 2 * total_time / chi2_upper_crit
        if failures == 0:
            mtbf_upper_two = math.inf
        else:
            chi2_lower_crit = float(stats.chi2.ppf(alpha / 2, df_upper))
            mtbf_upper_two = 2 * total_time / chi2_lower_crit

        chi2_one = float(stats.chi2.ppf(1 - alpha, df_one))
        mtbf_lower_one = 2 * total_time / chi2_one

        fit_upper_two = (1.0 / mtbf_lower_two) * 1e9
        fit_upper_one = (1.0 / mtbf_lower_one) * 1e9

        return {
            "mtbf_lower_two": sig(mtbf_lower_two),
            "mtbf_upper_two": sig(mtbf_upper_two),
            "mtbf_lower_one": sig(mtbf_lower_one),
            "fit_upper_two": sig(fit_upper_two),
            "fit_upper_one": sig(fit_upper_one),
        }


def termination_label(termination: str | None) -> str:
    if termination == "failure_terminated":
        return "定数截尾"
    if termination == "time_terminated":
        return "定时截尾"
    return "未指定"


def bx_life(mtbf: float, percent: float) -> float:
    """Bx 寿命：累计失效达到 percent% 的时间。"""
    return mtbf * math.log(1.0 / (1.0 - percent / 100.0))
