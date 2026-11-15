"""导出模块测试：报告结构、编码与公式注入防护。"""

from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook

from backend.app.exporting import build_csv, build_history_xlsx, build_xlsx

RECORD = {
    "id": 7,
    "calculator_id": "mtbf",
    "calculator_name": "MTBF 与失效率",
    "inputs": {"num_failures": 2, "total_test_time": 200000, "note": '=HYPERLINK("http://evil")'},
    "result": {
        "headline": [
            {"label": "MTBF", "value": 100000, "unit": "h", "note": "点估计"},
            {"label": "失效率 λ", "value": 10000, "unit": "FIT", "note": ""},
        ],
        "tables": [
            {
                "title": "点估计",
                "columns": ["指标", "数值", "单位"],
                "rows": [["MTBF", 100000, "h"]],
                "note": "单元测试数据",
            }
        ],
        "notes": ["这是说明文本"],
        "meta": {"model": "指数分布"},
    },
    "created_at": "2026-11-15T08:00:00+00:00",
}


def test_csv_has_bom_and_sections():
    data = build_csv(RECORD)
    assert data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    assert "半导体可靠性计算报告" in text
    assert "[核心指标]" in text
    assert "[点估计]" in text
    assert "这是说明文本" in text


def test_xlsx_structure_and_formula_guard():
    data = build_xlsx(RECORD)
    workbook = load_workbook(BytesIO(data))
    assert "报告概览" in workbook.sheetnames
    assert "点估计" in workbook.sheetnames

    formulas = []
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    formulas.append((cell.data_type, cell.value))
    # 以 "=" 开头的用户输入必须按文本保存，不能被当成公式
    assert formulas
    for data_type, value in formulas:
        assert data_type == "s", value


def test_history_xlsx_has_detail_sheet():
    data = build_history_xlsx([RECORD])
    workbook = load_workbook(BytesIO(data))
    assert workbook.sheetnames == ["历史记录", "明细"]
    detail_values = [cell.value for row in workbook["明细"].iter_rows() for cell in row]
    assert "MTBF" in detail_values
