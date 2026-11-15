"""计算器数学正确性测试。

断言值均按标准公式独立推算，用于防止回归：
- MTBF 卡方区间对照 χ² 临界值表（χ²(0.95,6)=12.5916，χ²(0.05,4)=0.7107，χ²(0.95,2)=5.9915）
- Duane 用已知 α、β 生成失效时刻，检查回归能否还原
- 样本量对照闭式解 n = ln(1-C)/ln(R) 与 χ² 分位数
"""

from __future__ import annotations

import json
import math

import pytest
from scipy import stats

from backend.app.calculators import CALCULATORS
from backend.app.calculators.base import CalculationError


def run(calculator: str, inputs: dict) -> dict:
    result = CALCULATORS[calculator].calculate(inputs)
    # 结果必须可以直接 JSON 序列化（前端与导出都依赖这一点）
    json.dumps(result, allow_nan=False, ensure_ascii=False)
    return result


def headline_value(result: dict, label: str):
    for item in result["headline"]:
        if item["label"] == label:
            return item["value"]
    raise AssertionError(f"未找到指标：{label}")


# --------------------------------------------------------------------- MTBF
def test_mtbf_point_estimate_and_fit():
    result = run(
        "mtbf",
        {
            "data_mode": "test_data",
            "num_failures": 2,
            "total_test_time": 200000,
            "termination": "time_terminated",
            "confidence_level": "90",
            "mission_time": 10000,
        },
    )
    assert headline_value(result, "MTBF") == pytest.approx(100000, rel=1e-9)
    assert headline_value(result, "失效率 λ") == pytest.approx(10000, rel=1e-6)  # 10000 FIT

    table = next(item for item in result["tables"] if item["title"] == "任务时间可靠度")
    reliability = table["rows"][1][1]
    assert reliability == pytest.approx(math.exp(-0.1), rel=1e-6)


def test_mtbf_chi_square_interval_matches_table():
    result = run(
        "mtbf",
        {
            "data_mode": "test_data",
            "num_failures": 2,
            "total_test_time": 200000,
            "termination": "time_terminated",
            "confidence_level": "90",
        },
    )
    interval = next(item for item in result["tables"] if item["title"] == "置信区间")
    lower, upper = interval["rows"][0][1], interval["rows"][0][2]
    # 2T/χ²(0.95, 2r+2) 与 2T/χ²(0.05, 2r)
    assert lower == pytest.approx(400000 / 12.5916, rel=2e-3)
    assert upper == pytest.approx(400000 / 0.7107, rel=2e-3)

    one_sided = interval["rows"][1][1]
    assert one_sided == pytest.approx(400000 / stats.chi2.ppf(0.9, 6), rel=1e-6)
    assert lower < one_sided < 100000


def test_mtbf_zero_failures_gives_infinite_point_and_finite_lower_bound():
    result = run("mtbf", {"data_mode": "test_data", "num_failures": 0, "total_test_time": 100000, "confidence_level": "90"})
    assert headline_value(result, "MTBF") == "∞"
    interval = next(item for item in result["tables"] if item["title"] == "置信区间")
    assert interval["rows"][0][2] == "∞"
    assert interval["rows"][0][1] == pytest.approx(200000 / 5.9915, rel=2e-3)


def test_mtbf_failure_termination_requires_failure():
    with pytest.raises(CalculationError):
        CALCULATORS["mtbf"].calculate(
            {"data_mode": "test_data", "num_failures": 0, "total_test_time": 100000, "termination": "failure_terminated"}
        )


def test_mtbf_rate_mode_uses_fit_conversion():
    result = run("mtbf", {"data_mode": "failure_rate", "failure_rate": 50, "failure_rate_unit": "fit"})
    assert headline_value(result, "MTBF") == pytest.approx(2e7, rel=1e-9)
    assert any("无法给出置信区间" in note for note in result["notes"])


def test_mtbf_bx_life():
    result = run("mtbf", {"data_mode": "test_data", "num_failures": 1, "total_test_time": 100000})
    table = next(item for item in result["tables"] if item["title"].startswith("寿命特征"))
    b10 = table["rows"][1][1]
    assert b10 == pytest.approx(100000 * math.log(1 / 0.9), rel=1e-4)


# -------------------------------------------------------------------- Duane
def _synthetic_times(alpha: float, beta: float, n: int) -> str:
    times = [(alpha * i) ** (1 / (1 - beta)) for i in range(1, n + 1)]
    return ", ".join(f"{t:.6f}" for t in times)


def test_duane_recovers_synthetic_parameters():
    alpha, beta = 100.0, 0.4
    result = run("duane", {"failure_times": _synthetic_times(alpha, beta, 10), "confidence_level": "90"})
    assert headline_value(result, "增长参数 β") == pytest.approx(beta, rel=1e-4)
    params = next(item for item in result["tables"] if item["title"] == "回归参数")
    alpha_row = params["rows"][0]
    assert alpha_row[1] == pytest.approx(alpha, rel=1e-3)
    # 合成数据完全落在直线上
    assert params["rows"][7][1] == pytest.approx(1.0, rel=1e-6)


def test_duane_instantaneous_mtbf_uses_one_minus_beta():
    result = run(
        "duane",
        {"failure_times": _synthetic_times(100, 0.4, 10), "total_test_time": 100000, "confidence_level": "90"},
    )
    beta = headline_value(result, "增长参数 β")
    cumulative = headline_value(result, "当前累计 MTBF")
    instantaneous = headline_value(result, "当前瞬时 MTBF")
    assert instantaneous == pytest.approx(cumulative / (1 - beta), rel=1e-4)


def test_duane_target_mtbf_planning():
    alpha, beta = 100.0, 0.4
    target = 20000
    test_duration = 100000
    result = run(
        "duane",
        {
            "failure_times": _synthetic_times(alpha, beta, 10),
            "total_test_time": test_duration,
            "target_mtbf": target,
            "confidence_level": "90",
        },
    )
    plan = next(item for item in result["tables"] if item["title"] == "目标 MTBF 规划")
    required = plan["rows"][1][1]
    # 瞬时口径：T = (M(1-β)/α)^(1/β)
    assert required == pytest.approx((target * (1 - beta) / alpha) ** (1 / beta), rel=1e-4)
    assert required > test_duration
    assert plan["rows"][2][1] == pytest.approx(required - test_duration, rel=1e-4)


def test_duane_rejects_non_increasing_times():
    with pytest.raises(CalculationError):
        CALCULATORS["duane"].calculate({"failure_times": "100, 200, 150"})
    with pytest.raises(CalculationError):
        CALCULATORS["duane"].calculate({"failure_times": "100, 200"})


def test_duane_chart_has_log_points():
    result = run("duane", {"failure_times": _synthetic_times(100, 0.4, 8)})
    chart = result["chart"]
    assert chart["scale"] == "loglog"
    labels = [item["name"] for item in chart["series"]]
    assert "实测累计 MTBF" in labels and "拟合累计 MTBF" in labels
    for item in chart["series"]:
        for point in item["points"]:
            assert point[0] > 0 and point[1] > 0


# --------------------------------------------------------------- 样本量
def test_success_run_matches_closed_form():
    result = run("sample_size", {"test_type": "success_run", "target_reliability": 0.9, "confidence_level": "90"})
    assert headline_value(result, "所需样本量 n") == 22


def test_success_run_higher_reliability_needs_more_units():
    result = run("sample_size", {"test_type": "success_run", "target_reliability": 0.95, "confidence_level": "90"})
    assert headline_value(result, "所需样本量 n") == 45


def test_binomial_allowed_failure_is_minimal():
    result = run(
        "sample_size",
        {"test_type": "binomial_failures", "target_reliability": 0.9, "allowed_failures": 1, "confidence_level": "90"},
    )
    units = headline_value(result, "所需样本量 n")
    # 恰好满足判定阈值，且少一台就不满足
    assert float(stats.binom.cdf(1, units, 0.1)) <= 0.1
    assert float(stats.binom.cdf(1, units - 1, 0.1)) > 0.1


def test_exponential_time_terminated_total_time():
    result = run(
        "sample_size",
        {"test_type": "exponential_time", "target_mtbf": 1e6, "allowed_failures": 0, "confidence_level": "90"},
    )
    expected = 0.5 * 1e6 * float(stats.chi2.ppf(0.9, 2))
    assert headline_value(result, "所需总试验时间") == pytest.approx(expected, rel=1e-4)


def test_exponential_units_from_duration():
    result = run(
        "sample_size",
        {
            "test_type": "exponential_time",
            "target_mtbf": 100000,
            "allowed_failures": 0,
            "test_duration": 5000,
            "confidence_level": "90",
        },
    )
    total = headline_value(result, "所需总试验时间")
    assert headline_value(result, "所需样本量 n") == math.ceil(total / 5000)


def test_exponential_failure_terminated_requires_failure():
    with pytest.raises(CalculationError):
        CALCULATORS["sample_size"].calculate(
            {"test_type": "exponential_failure", "target_mtbf": 1e5, "allowed_failures": 0}
        )
