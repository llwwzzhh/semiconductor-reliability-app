"""导出构建：CSV / XLSX / JSON。

两种导出形态：
- 单条记录：报告式排版（概览 + 每个表格独立页签 + 说明）
- 多条记录：历史台账（汇总表 + 明细平铺表）
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_SHEET_TITLE_BAD = re.compile(r"[\[\]:*?/\\]")
_HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
_SECTION_FILL = PatternFill("solid", fgColor="E8EEF4")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_THIN = Side(style="thin", color="D0D7E2")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:  # NaN
            return "—"
        return f"{value:.10g}"
    return str(value)


def _safe_sheet_title(raw: str, used: set[str]) -> str:
    title = _SHEET_TITLE_BAD.sub("", raw).strip() or "Sheet"
    title = title[:31]
    base = title
    index = 2
    while title in used:
        suffix = f"_{index}"
        title = base[: 31 - len(suffix)] + suffix
        index += 1
    used.add(title)
    return title


def _write_sheet(ws, title: str, columns: list[str], rows: list[list[Any]], note: str = "") -> None:
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=12)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(columns), 2))
    ws.append(columns)
    header_row = ws.max_row
    for col_index in range(1, len(columns) + 1):
        cell = ws.cell(row=header_row, column=col_index)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _BORDER
    for row in rows:
        ws.append([_cell_value(cell) for cell in row])
        for col_index in range(1, len(columns) + 1):
            ws.cell(row=ws.max_row, column=col_index).border = _BORDER
    if note:
        ws.append([])
        ws.append([f"说明：{note}"])
        ws.cell(row=ws.max_row, column=1).font = Font(italic=True, color="6B7280")
    for col_index, column in enumerate(columns, start=1):
        width = max(len(str(column)) + 4, 12)
        ws.column_dimensions[get_column_letter(col_index)].width = min(width, 42)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)


def _cell_value(value: Any) -> Any:
    if isinstance(value, float) and value != value:
        return "—"
    return value


def _sanitize_sheet(worksheet) -> None:
    """把以 "=" 开头的文本强制按字符串写入，避免被 Excel 当成公式执行。"""
    for row in worksheet.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                cell.data_type = "s"


def _record_meta(record: dict[str, Any]) -> dict[str, str]:
    created = record.get("created_at")
    if isinstance(created, datetime):
        created_text = created.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        created_text = _str(created)
    return {
        "计算器": _str(record.get("calculator_name") or record.get("calculator_id")),
        "记录编号": _str(record.get("id") or "未保存"),
        "生成时间": created_text,
    }


def _flatten_inputs(inputs: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for key, value in inputs.items():
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        rows.append([key, value])
    return rows


# --------------------------------------------------------------------- CSV
def build_csv(record: dict[str, Any]) -> bytes:
    result = record.get("result", {})
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")

    writer.writerow(["半导体可靠性计算报告"])
    for key, value in _record_meta(record).items():
        writer.writerow([key, value])
    writer.writerow([])

    writer.writerow(["[核心指标]"])
    writer.writerow(["指标", "数值", "单位", "说明"])
    for item in result.get("headline", []):
        writer.writerow([item.get("label", ""), _str(item.get("value")), item.get("unit", ""), item.get("note", "")])

    for section in result.get("tables", []):
        writer.writerow([])
        writer.writerow([f"[{section.get('title', '')}]"])
        writer.writerow(section.get("columns", []))
        for row in section.get("rows", []):
            writer.writerow([_str(cell) for cell in row])
        if section.get("note"):
            writer.writerow(["说明", section["note"]])

    if record.get("inputs"):
        writer.writerow([])
        writer.writerow(["[输入参数]"])
        writer.writerow(["参数", "取值"])
        for row in _flatten_inputs(record["inputs"]):
            writer.writerow([row[0], _str(row[1])])

    notes = result.get("notes") or []
    if notes:
        writer.writerow([])
        writer.writerow(["[说明与假设]"])
        for note in notes:
            writer.writerow([note])

    return buffer.getvalue().encode("utf-8-sig")


def build_history_csv(records: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["记录编号", "计算时间", "计算器", "主要结果", "输入参数"])
    for record in records:
        result = record.get("result", {})
        summary = "；".join(
            f"{item.get('label')}={_str(item.get('value'))}{item.get('unit', '')}" for item in result.get("headline", [])[:3]
        )
        inputs = json.dumps(record.get("inputs", {}), ensure_ascii=False)
        writer.writerow([
            _str(record.get("id")),
            _record_meta(record)["生成时间"],
            _str(record.get("calculator_name") or record.get("calculator_id")),
            summary,
            inputs,
        ])
    return buffer.getvalue().encode("utf-8-sig")


# -------------------------------------------------------------------- XLSX
def build_xlsx(record: dict[str, Any]) -> bytes:
    result = record.get("result", {})
    workbook = Workbook()
    summary = workbook.active
    summary.title = "报告概览"
    used_titles = {"报告概览"}

    summary.append(["半导体可靠性计算报告"])
    summary["A1"].font = Font(bold=True, size=14)
    summary.append([])
    for key, value in _record_meta(record).items():
        summary.append([key, value])
        summary.cell(row=summary.max_row, column=1).font = Font(bold=True)
    meta = result.get("meta") or {}
    if meta:
        summary.append([])
        summary.append(["模型与设置"])
        summary.cell(row=summary.max_row, column=1).font = Font(bold=True)
        for key, value in meta.items():
            summary.append([key, _str(value)])

    summary.append([])
    summary.append(["核心指标"])
    summary.cell(row=summary.max_row, column=1).font = Font(bold=True)
    summary.append(["指标", "数值", "单位", "说明"])
    header_row = summary.max_row
    for col in range(1, 5):
        cell = summary.cell(row=header_row, column=col)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
    for item in result.get("headline", []):
        summary.append([item.get("label", ""), _cell_value(item.get("value")), item.get("unit", ""), item.get("note", "")])
        for col in range(1, 5):
            summary.cell(row=summary.max_row, column=col).border = _BORDER

    if record.get("inputs"):
        summary.append([])
        summary.append(["输入参数"])
        summary.cell(row=summary.max_row, column=1).font = Font(bold=True)
        summary.append(["参数", "取值"])
        header = summary.max_row
        for col in range(1, 3):
            summary.cell(row=header, column=col).font = Font(bold=True)
            summary.cell(row=header, column=col).fill = _SECTION_FILL
            summary.cell(row=header, column=col).border = _BORDER
        for row in _flatten_inputs(record["inputs"]):
            summary.append([row[0], _str(row[1])])
            summary.cell(row=summary.max_row, column=1).border = _BORDER
            summary.cell(row=summary.max_row, column=2).border = _BORDER

    summary.column_dimensions["A"].width = 26
    summary.column_dimensions["B"].width = 34
    summary.column_dimensions["C"].width = 12
    summary.column_dimensions["D"].width = 46

    for section in result.get("tables", []):
        title = _safe_sheet_title(section.get("title", "明细"), used_titles)
        sheet = workbook.create_sheet(title)
        _write_sheet(
            sheet,
            section.get("title", title),
            section.get("columns", []),
            section.get("rows", []),
            section.get("note", ""),
        )

    notes = result.get("notes") or []
    if notes:
        sheet = workbook.create_sheet(_safe_sheet_title("说明与假设", used_titles))
        sheet.append(["说明与假设"])
        sheet["A1"].font = Font(bold=True, size=12)
        for note in notes:
            sheet.append([note])
        sheet.column_dimensions["A"].width = 120

    for worksheet in workbook.worksheets:
        _sanitize_sheet(worksheet)

    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def build_history_xlsx(records: list[dict[str, Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "历史记录"
    columns = ["记录编号", "计算时间", "计算器", "主要结果", "输入参数"]
    _write_sheet(sheet, "可靠性计算历史记录", columns, [
        [
            _str(record.get("id")),
            _record_meta(record)["生成时间"],
            _str(record.get("calculator_name") or record.get("calculator_id")),
            "；".join(
                f"{item.get('label')}={_str(item.get('value'))}{item.get('unit', '')}"
                for item in record.get("result", {}).get("headline", [])[:3]
            ),
            json.dumps(record.get("inputs", {}), ensure_ascii=False),
        ]
        for record in records
    ])

    detail = workbook.create_sheet("明细")
    _write_sheet(
        detail,
        "逐条指标明细",
        ["记录编号", "计算器", "分组", "指标", "数值", "单位"],
        _detail_rows(records),
    )
    for worksheet in workbook.worksheets:
        _sanitize_sheet(worksheet)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _detail_rows(records: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for record in records:
        result = record.get("result", {})
        for item in result.get("headline", []):
            rows.append([
                _str(record.get("id")),
                _str(record.get("calculator_name") or record.get("calculator_id")),
                "核心指标",
                item.get("label", ""),
                _cell_value(item.get("value")),
                item.get("unit", ""),
            ])
        for section in result.get("tables", []):
            for row in section.get("rows", []):
                rows.append([
                    _str(record.get("id")),
                    _str(record.get("calculator_name") or record.get("calculator_id")),
                    section.get("title", ""),
                    _str(row[0]) if row else "",
                    " | ".join(_str(cell) for cell in row[1:]),
                    "",
                ])
    return rows


# -------------------------------------------------------------------- JSON
def build_json(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


# ----------------------------------------------------------------- 输出封装
def render_single(record: dict[str, Any], fmt: str) -> tuple[bytes, str, str]:
    calculator_id = _str(record.get("calculator_id") or "result")
    stamp = _timestamp()
    if fmt == "csv":
        return build_csv(record), "text/csv; charset=utf-8", f"reliability_{calculator_id}_{stamp}.csv"
    if fmt == "xlsx":
        return (
            build_xlsx(record),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"reliability_{calculator_id}_{stamp}.xlsx",
        )
    return build_json(record), "application/json; charset=utf-8", f"reliability_{calculator_id}_{stamp}.json"


def render_history(records: list[dict[str, Any]], fmt: str) -> tuple[bytes, str, str]:
    stamp = _timestamp()
    if fmt == "csv":
        return build_history_csv(records), "text/csv; charset=utf-8", f"reliability_history_{stamp}.csv"
    if fmt == "xlsx":
        return (
            build_history_xlsx(records),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"reliability_history_{stamp}.xlsx",
        )
    return build_json(records), "application/json; charset=utf-8", f"reliability_history_{stamp}.json"
