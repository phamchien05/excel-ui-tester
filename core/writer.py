"""
Ghi danh sách test case ra file Excel đúng định dạng mà reader.py đọc được.

Dùng cho chức năng tự sinh kịch bản (quét trang) và ghi lại thao tác.
Các bước có note = "auto" (kết quả do công cụ tự ghi nhận) được tô vàng nhạt,
note = "review" (cần người xem lại) được tô cam để người kiểm thử dễ nhận ra.
"""

from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from core.reader import TestCase

HEADERS = ["Bước", "Từ khóa", "Selector", "Giá trị", "Mô tả"]
COLUMN_WIDTHS = {"A": 7, "B": 18, "C": 40, "D": 34, "E": 60}

HEADER_FILL = PatternFill("solid", fgColor="2F5597")
HEADER_FONT = Font(bold=True, color="FFFFFF")
NOTE_FILLS = {
    "auto": PatternFill("solid", fgColor="FFF2CC"),    # vàng nhạt: tự ghi nhận
    "review": PatternFill("solid", fgColor="F8CBAD"),  # cam: cần xem lại
}

NOTES_SHEET_NAME = "Ghi chú"


def safe_sheet_name(name: str, used: set[str]) -> str:
    """Tên sheet Excel: tối đa 31 ký tự, không chứa []:*?/\\ và không trùng nhau."""
    base = re.sub(r"[\[\]:*?/\\]", "-", name).strip() or "Test"
    candidate, index = base[:31], 2
    while candidate.lower() in used or candidate.upper() == "DATA" or candidate == NOTES_SHEET_NAME:
        suffix = f" ({index})"
        candidate = base[:31 - len(suffix)] + suffix
        index += 1
    used.add(candidate.lower())
    return candidate


def _style_header(ws):
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"


def write_cases(path: str | Path, cases: list[TestCase], notes: list[str] | None = None) -> Path:
    """
    Ghi các test case ra file Excel, mỗi test case một sheet.
    notes: các dòng ghi chú, ghi vào sheet "Ghi chú" ở cuối (reader sẽ bỏ qua sheet này).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()

    for case in cases:
        ws = wb.create_sheet(title=safe_sheet_name(case.name, used))
        ws.append(HEADERS)
        for i, step in enumerate(case.steps, start=1):
            ws.append([i, step.keyword, step.selector, step.value, step.description])
            if step.note in NOTE_FILLS:
                for cell in ws[ws.max_row]:
                    cell.fill = NOTE_FILLS[step.note]
        _style_header(ws)
        for col, width in COLUMN_WIDTHS.items():
            ws.column_dimensions[col].width = width

    if notes:
        ws = wb.create_sheet(title=NOTES_SHEET_NAME)
        ws.append(["Ghi chú"])
        for line in notes:
            ws.append([line])
        _style_header(ws)
        ws.column_dimensions["A"].width = 120

    wb.save(path)
    return path
