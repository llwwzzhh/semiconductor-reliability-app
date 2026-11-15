"""Duane 可靠性增长模型。

模型（MIL-HDBK-189 / Duane）：
    累计 MTBF   M_c(T) = α · T^β        （0 < β < 1，β 越小增长越快）
    瞬时 MTBF   M_i(T) = M_c(T) / (1-β)
    β 由 ln M_c 对 ln T 的最小二乘回归得到：β = slope，α = exp(intercept)
    增长率 = 1 - β

预测区间在 log 空间用回归预测区间（t 分布）近似，再取指数还原：
    ln M̂ ± t(1-α/2, n-2) · sqrt(MSE · (1 + 1/n + (x0 - x̄)²/Sxx))
"""

from __future__ import annotations

import math
import re
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

_SPLITTER = re.compile(r"[,;，；\s]+")


class DuaneCalculator(BaseCalculator):
    @property
    def info(self) -> CalculatorInfo:
        return CalculatorInfo(
            id="duane",
            name="Duane 可靠性增长模型",
            short_name="Duane",
            category="可靠性增长",
            description="按失效时刻拟合 Duane 增长模型，得到增长参数 β、瞬时 MTBF、回归显著性，并预测目标时刻 MTBF 或规划达到目标 MTBF 所需的试验时间。",
            formula_summary="M_c(T)=α·T^β；M_i(T)=M_c/(1-β)；增长率=1-β",
            standards=["MIL-HDBK-189", "MIL-HDBK-781A", "IEC 61014"],
            input_fields=[
                InputField(
                    name="failure_times",
                    label="失效时刻（升序）",
                    type="text",
                    required=True,
                    placeholder="120, 350, 720, 1300, 2100, 3200",
                    description="按时间先后排列的失效时刻，逗号或空格分隔，至少 3 个",
                ),
                InputField(
                    name="total_test_time",
                    label="当前累计试验时间 T",
                    type="number",
                    unit="h",
                    min=0,
                    required=False,
                    description="含未失效样本的总累计试验时间；留空则取最后一个失效时刻",
                ),
                InputField(
                    name="target_time",
                    label="预测时刻",
                    type="number",
                    unit="h",
                    min=0,
                    required=False,
                    description="需要预测累计/瞬时 MTBF 的未来时刻；留空则只给出当前时刻结果",
                ),
                InputField(
                    name="target_mtbf",
                    label="目标瞬时 MTBF",
                    type="number",
                    unit="h",
                    min=0,
                    required=False,
                    description="用于反算达到该 MTBF 所需的累计试验时间",
                ),
                InputField(
                    name="confidence_level",
                    label="置信水平",
                    type="select",
                    default="90",
                    options=[
                        FieldOption(value="80", label="80%"),
                        FieldOption(value="90", label="90%"),
                        FieldOption(value="95", label="95%"),
                        FieldOption(value="99", label="99%"),
                    ],
                ),
            ],
        )

    def example_inputs(self) -> dict[str, Any]:
        return {
            "failure_times": "120, 350, 720, 1300, 2100, 3200",
            "total_test_time": 4000,
            "target_time": 6000,
            "target_mtbf": 1200,
            "confidence_level": "90",
        }

    # ------------------------------------------------------------------ 计算
    def calculate(self, inputs: dict[str, Any]) -> dict[str, Any]:
        values = self.validate(inputs)
        failure_times = self._parse_times(values["failure_times"])
        conf = float(values["confidence_level"]) / 100.0
        alpha = 1.0 - conf

        n = len(failure_times)
        if n < 3:
            raise CalculationError("Duane 回归至少需要 3 个失效时刻，否则无法评估拟合显著性与置信区间")

        cumulative_mtbf = [failure_times[i] / (i + 1) for i in range(n)]
        xs = [math.log(t) for t in failure_times]
        ys = [math.log(m) for m in cumulative_mtbf]

        x_bar = sum(xs) / n
        y_bar = sum(ys) / n
        sxx = sum((x - x_bar) ** 2 for x in xs)
        sxy = sum((xs[i] - x_bar) * (ys[i] - y_bar) for i in range(n))
        if sxx == 0:
            raise CalculationError("失效时刻完全相同，无法拟合 Duane 模型")

        beta = sxy / sxx
        intercept = y_bar - beta * x_bar
        alpha_param = math.exp(intercept)

        fitted = [intercept + beta * x for x in xs]
        sse = sum((ys[i] - fitted[i]) ** 2 for i in range(n))
        sst = sum((y - y_bar) ** 2 for y in ys)
        r_squared = 1.0 - sse / sst if sst > 0 else 1.0
        df = n - 2
        mse = sse / df
        se_beta = math.sqrt(mse / sxx) if mse >= 0 else math.inf

        if se_beta and math.isfinite(se_beta) and se_beta > 0:
            t_value = beta / se_beta
            p_value = float(2 * (1 - stats.t.cdf(abs(t_value), df)))
        else:
            t_value = math.inf
            p_value = 0.0

        t_crit = float(stats.t.ppf(1 - alpha / 2, df))
        beta_ci = (beta - t_crit * se_beta, beta + t_crit * se_beta)

        test_duration = float(values.get("total_test_time") or failure_times[-1])
        if test_duration < failure_times[-1]:
            raise CalculationError("当前累计试验时间不得小于最后一个失效时刻")

        growth = 1.0 - beta
        max_observed = max(test_duration, failure_times[-1])

        def predict(t0: float) -> dict[str, Any]:
            x0 = math.log(t0)
            ln_cum = intercept + beta * x0
            cumulative = math.exp(ln_cum)
            residual_std = math.sqrt(max(mse, 0) * (1 + 1 / n + (x0 - x_bar) ** 2 / sxx))
            half = t_crit * residual_std
            interval = (math.exp(ln_cum - half), math.exp(ln_cum + half))
            if beta < 1:
                instantaneous = cumulative / (1 - beta)
                inst_interval = (interval[0] / (1 - beta), interval[1] / (1 - beta))
            else:
                instantaneous = None
                inst_interval = (None, None)
            return {
                "time": t0,
                "cumulative": cumulative,
                "instantaneous": instantaneous,
                "cumulative_ci": interval,
                "instantaneous_ci": inst_interval,
            }

        current = predict(max_observed)

        # ------------------------------------------------------------ 关键指标
        headline = [
            headline_item("增长参数 β", beta, "", "越接近 0 增长越快"),
            headline_item("增长率 1-β", growth, "", "累计 MTBF 的幂律增长指数"),
            headline_item("当前累计 MTBF", current["cumulative"], "h", f"T = {sig(max_observed)} h"),
        ]
        if current["instantaneous"] is not None:
            headline.append(headline_item("当前瞬时 MTBF", current["instantaneous"], "h", "工程当前水平"))

        # ------------------------------------------------------------ 回归参数
        param_rows = [
            ["尺度参数 α", alpha_param, "h^(1-β)"],
            ["增长参数 β", beta, "—"],
            ["增长率 1-β", growth, "—"],
            ["β 标准误", se_beta, "—"],
            ["β 的 t 值", t_value, "—"],
            ["显著性 p 值", p_value, "—"],
            [f"β 的 {conf * 100:g}% 置信区间", f"{beta_ci[0]:.4g} ~ {beta_ci[1]:.4g}", "—"],
            ["决定系数 R²", r_squared, "—"],
            ["回归自由度", df, "—"],
            ["失效样本数 n", n, "个"],
        ]
        tables = [
            table(
                "回归参数",
                ["参数", "数值", "单位/说明"],
                param_rows,
                note="β 的 p 值检验原假设 β=0（无增长）；p 越小说明增长趋势越显著。",
            )
        ]

        # -------------------------------------------------------- 累计 MTBF 明细
        cumulative_rows = [
            [i + 1, failure_times[i], cumulative_mtbf[i], fitted[i]]
            for i in range(n)
        ]
        tables.append(
            table(
                "累计 MTBF 观测数据",
                ["失效序号 i", "失效时刻 (h)", "实测累计 MTBF (h)", "拟合 ln M̂_c"],
                cumulative_rows,
                note="实测累计 MTBF = 失效时刻 / 失效序号；拟合值为 log 空间回归直线取值。",
            )
        )

        # ------------------------------------------------------------ 当前水平
        current_rows = [
            ["当前累计试验时间", max_observed, "h"],
            ["累计 MTBF", current["cumulative"], "h"],
            [
                "累计 MTBF 预测区间",
                f"{current['cumulative_ci'][0]:.4g} ~ {current['cumulative_ci'][1]:.4g}",
                f"{conf * 100:g}%",
            ],
        ]
        if current["instantaneous"] is not None:
            current_rows.append(["瞬时 MTBF", current["instantaneous"], "h"])
            current_rows.append(
                [
                    "瞬时 MTBF 预测区间",
                    f"{current['instantaneous_ci'][0]:.4g} ~ {current['instantaneous_ci'][1]:.4g}",
                    f"{conf * 100:g}%（近似）",
                ]
            )
        tables.append(table("当前可靠性水平", ["项目", "数值", "单位"], current_rows))

        # ------------------------------------------------------------ 目标时刻预测
        target_time = values.get("target_time")
        target_prediction = None
        if target_time:
            if target_time <= 0:
                raise CalculationError("预测时刻必须大于 0")
            target_prediction = predict(float(target_time))
            rows = [
                ["预测时刻", target_prediction["time"], "h"],
                ["累计 MTBF", target_prediction["cumulative"], "h"],
                [
                    "累计 MTBF 预测区间",
                    f"{target_prediction['cumulative_ci'][0]:.4g} ~ {target_prediction['cumulative_ci'][1]:.4g}",
                    f"{conf * 100:g}%",
                ],
            ]
            if target_prediction["instantaneous"] is not None:
                rows.append(["瞬时 MTBF", target_prediction["instantaneous"], "h"])
                rows.append(
                    [
                        "瞬时 MTBF 预测区间",
                        f"{target_prediction['instantaneous_ci'][0]:.4g} ~ {target_prediction['instantaneous_ci'][1]:.4g}",
                        f"{conf * 100:g}%（近似）",
                    ]
                )
            tables.append(table("目标时刻 MTBF 预测", ["项目", "数值", "单位"], rows))

        # ------------------------------------------------------------ 目标 MTBF 规划
        target_mtbf = values.get("target_mtbf")
        if target_mtbf:
            if beta >= 1:
                notes_target = "β ≥ 1 表示没有可靠性增长，无法通过延长试验达到更高的 MTBF。"
                tables.append(table("目标 MTBF 规划", ["项目", "数值", "单位"], [["结论", notes_target, "—"]]))
            else:
                target_mtbf = float(target_mtbf)
                required_instant_time = (target_mtbf * (1 - beta) / alpha_param) ** (1 / beta)
                required_cum_time = (target_mtbf / alpha_param) ** (1 / beta)
                rows = [
                    ["目标 MTBF（瞬时口径）", target_mtbf, "h"],
                    ["按瞬时 MTBF 反算所需累计时间", required_instant_time, "h"],
                    [
                        "还需累计试验时间",
                        max(required_instant_time - max_observed, 0),
                        "h",
                    ],
                    ["按累计 MTBF 反算所需累计时间", required_cum_time, "h"],
                    ["当前累计试验时间", max_observed, "h"],
                ]
                tables.append(
                    table(
                        "目标 MTBF 规划",
                        ["项目", "数值", "单位"],
                        rows,
                        note="所需时间按增长趋势外推，不含未来新失效；实际排产建议留 10%~20% 余量。",
                    )
                )

        # ------------------------------------------------------------ 增长评价
        notes = [self._growth_comment(beta)] + [
            "Duane 模型假设失效强度随累计试验时间按幂律下降，仅适用于纠正性改进持续进行的可靠性增长阶段。",
            "β ≥ 1 表示没有（或负向）增长；β 越接近 0，增长越快，但过小的 β 也常意味着早期数据主导，应结合后续数据复核。",
            "瞬时 MTBF 预测区间由累计区间按 1/(1-β) 近似缩放，属工程近似，严格推断需非线性回归的协方差矩阵。",
        ]

        # ------------------------------------------------------------ 图表
        chart_x_min = max(failure_times[0] * 0.9, 1e-6)
        chart_x_max = max(max_observed, failure_times[-1], float(target_time or 0)) * 1.15
        steps = 40
        fit_points = []
        inst_points = []
        for i in range(steps + 1):
            t = chart_x_min * ((chart_x_max / chart_x_min) ** (i / steps))
            cumulative = alpha_param * t ** beta
            fit_points.append([t, cumulative])
            if beta < 1:
                inst_points.append([t, cumulative / (1 - beta)])
        chart_series = [
            series("实测累计 MTBF", [[failure_times[i], cumulative_mtbf[i]] for i in range(n)]),
            series("拟合累计 MTBF", fit_points),
        ]
        if beta < 1:
            chart_series.append(series("瞬时 MTBF", inst_points))
        chart = {
            "type": "loglog",
            "title": "Duane 增长曲线（双对数坐标）",
            "x_label": "累计试验时间 (h)",
            "y_label": "MTBF (h)",
            "scale": "loglog",
            "series": chart_series,
        }

        return {
            "headline": headline,
            "tables": tables,
            "chart": chart,
            "notes": notes,
            "meta": {
                "model": "Duane 幂律增长模型",
                "confidence_level": conf * 100,
                "failures": n,
                "test_duration": sig(max_observed),
            },
        }

    # -------------------------------------------------------------- 辅助方法
    def _parse_times(self, raw: str) -> list[float]:
        tokens = [token for token in _SPLITTER.split(raw) if token]
        if not tokens:
            raise CalculationError("请输入失效时刻")
        try:
            times = [float(token) for token in tokens]
        except ValueError as exc:
            raise CalculationError("失效时刻必须是数字，用逗号或空格分隔") from exc
        if any(t <= 0 for t in times):
            raise CalculationError("失效时刻必须大于 0")
        if any(times[i] <= times[i - 1] for i in range(1, len(times))):
            raise CalculationError("失效时刻必须严格升序，请检查输入顺序或重复值")
        return times

    def _growth_comment(self, beta: float) -> str:
        if beta >= 1:
            return "β ≥ 1，当前数据未显示可靠性增长，需检查失效模式是否已纠正、改进是否真正生效。"
        if beta >= 0.8:
            return f"β = {beta:.3f}，增长缓慢；每翻倍累计试验时间，MTBF 提升约 {2 ** beta:.2f} 倍。"
        if beta >= 0.5:
            return f"β = {beta:.3f}，增长中等；每翻倍累计试验时间，MTBF 提升约 {2 ** beta:.2f} 倍。"
        if beta >= 0.2:
            return f"β = {beta:.3f}，增长良好；每翻倍累计试验时间，MTBF 提升约 {2 ** beta:.2f} 倍。"
        return f"β = {beta:.3f}，增长很快；每翻倍累计试验时间，MTBF 提升约 {2 ** beta:.2f} 倍，注意早期数据偏差。"
