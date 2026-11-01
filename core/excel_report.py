"""
Xuất kết quả chạy test ra file Excel theo mẫu test case thường dùng trong tài liệu kiểm thử.

File ket_qua.xlsx gồm 3 sheet:
  1. Tổng quan    : thông tin lần chạy và thống kê pass/fail.
  2. Test case    : mỗi dòng một test case với các cột
                    ID | Tên test case | Dữ liệu | Các bước thực hiện | Kết quả mong đợi |
                    Kết quả thực tế | Trạng thái | Thời gian | Ảnh lỗi
  3. Chi tiết bước: mỗi dòng một bước, kèm kết quả và thời gian của bước đó.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

EXCEL_REPORT_NAME = "ket_qua.xlsx"

HEADER_FILL = PatternFill("solid", fgColor="2F5597")
HEADER_FONT = Font(bold=True, color="FFFFFF")
STATUS_STYLE = {
    "PASS": (PatternFill("solid", fgColor="DCFCE7"), Font(bold=True, color="16A34A")),
    "FAIL": (PatternFill("solid", fgColor="FEE2E2"), Font(bold=True, color="DC2626")),
    "SKIP": (PatternFill("solid", fgColor="F3F4F6"), Font(color="9CA3AF")),
}
STATUS_TEXT = {"PASS": "Đạt", "FAIL": "Lỗi", "SKIP": "Bỏ qua"}
THIN = Side(style="thin", color="D1D5DB")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")


def _step_text(step) -> str:
    """Mô tả một bước bằng chữ: ưu tiên cột Mô tả, nếu trống thì ghép từ khóa + selector + giá trị."""
    if step.description:
        return step.description
    return " ".join(part for part in (step.keyword, step.selector, f"\"{step.value}\"" if step.value else "") if part)


def _expected_text(case) -> str:
    """Kết quả mong đợi = các bước kiểm tra (assert_...) và chụp ảnh của test case."""
    checks = [s for s in case.steps if s.keyword.startswith("assert_")]
    return "\n".join(f"- {_step_text(s)}" for s in checks) or "(Không có bước kiểm tra)"


def _actual_text(case) -> str:
    if case.status == "PASS":
        return "Đúng như mong đợi"
    return case.error


def _write_table(ws, headers: list[str], rows: list[list], widths: list[int], status_col: int | None = None):
    """Ghi bảng có tiêu đề, kẻ viền, xuống dòng tự động, tô màu cột trạng thái."""
    ws.append(headers)
    for cell in ws[1]:
        cell.fill, cell.font, cell.border = HEADER_FILL, HEADER_FONT, BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in rows:
        ws.append(row)
        for cell in ws[ws.max_row]:
            cell.alignment, cell.border = WRAP, BORDER
        if status_col is not None:
            status_cell = ws.cell(row=ws.max_row, column=status_col + 1)
            raw = next((k for k, v in STATUS_TEXT.items() if v == status_cell.value), None)
            if raw:
                status_cell.fill, status_cell.font = STATUS_STYLE[raw]
                status_cell.alignment = Alignment(horizontal="center", vertical="top")
    for i, width in enumerate(widths):
        ws.column_dimensions[chr(ord("A") + i)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions  # Bật bộ lọc ở dòng tiêu đề


def export_excel_report(result, output_dir: str | Path) -> Path:
    """Ghi kết quả chạy bộ test (SuiteResult) ra file Excel. Trả về đường dẫn file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    wb = Workbook()

    # ----- Sheet 1: Tổng quan -----
    ws = wb.active
    ws.title = "Tổng quan"
    ws.append(["BÁO CÁO KẾT QUẢ KIỂM THỬ"])
    ws["A1"].font = Font(bold=True, size=14, color="2F5597")
    summary = [
        ("Bộ test", result.name), ("File kịch bản", result.file_path),
        ("Trình duyệt", f"{result.browser} ({'headless' if result.headless else 'có giao diện'})"),
        ("Bắt đầu", result.start_time.strftime("%d/%m/%Y %H:%M:%S")),
        ("Kết thúc", result.end_time.strftime("%d/%m/%Y %H:%M:%S") if result.end_time else ""),
        ("Tổng số test case", result.total), ("Đạt (Pass)", result.passed), ("Lỗi (Fail)", result.failed),
        ("Tỷ lệ đạt", f"{result.pass_rate}%"), ("Tổng thời gian chạy", f"{result.duration:.2f} giây"),
    ]
    for label, value in summary:
        ws.append([label, value])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 60

    # ----- Sheet 2: Test case -----
    rows = []
    for index, case in enumerate(result.cases, start=1):
        data = "\n".join(f"{k} = {v or '(trống)'}" for k, v in case.data_row.items()) if case.data_row else ""
        # Các bước thao tác (bước kiểm tra đã nằm ở cột Kết quả mong đợi), đánh số lại liên tục
        actions = [s for s in case.steps if not s.keyword.startswith("assert_")]
        steps = "\n".join(f"{i}. {_step_text(s)}" for i, s in enumerate(actions, start=1))
        screenshot = f"screenshots/{Path(case.screenshot).name}" if case.screenshot else ""
        rows.append([f"TC{index:02d}", case.name, data, steps, _expected_text(case), _actual_text(case),
                     STATUS_TEXT[case.status], round(case.duration, 2), screenshot])
    ws = wb.create_sheet("Test case")
    _write_table(ws, ["ID", "Tên test case", "Dữ liệu", "Các bước thực hiện", "Kết quả mong đợi",
                      "Kết quả thực tế", "Trạng thái", "Thời gian (s)", "Ảnh lỗi"],
                 rows, [7, 30, 22, 50, 45, 40, 11, 10, 30], status_col=6)
    # Ô ảnh lỗi là liên kết, bấm vào mở ảnh (file ảnh nằm cùng thư mục báo cáo)
    for row in ws.iter_rows(min_row=2, min_col=9, max_col=9):
        if row[0].value:
            row[0].hyperlink = row[0].value
            row[0].font = Font(color="2563EB", underline="single")

    # ----- Sheet 3: Chi tiết bước -----
    rows = [[f"TC{index:02d}", s.step_no, s.keyword, s.selector, s.value, s.description,
             STATUS_TEXT[s.status], round(s.duration, 3) if s.status != "SKIP" else "", s.error]
            for index, case in enumerate(result.cases, start=1) for s in case.steps]
    _write_table(wb.create_sheet("Chi tiết bước"),
                 ["ID", "Bước", "Từ khóa", "Selector", "Giá trị", "Mô tả", "Kết quả", "Thời gian (s)", "Lỗi"],
                 rows, [7, 6, 16, 30, 25, 40, 10, 11, 50], status_col=6)

    path = output_dir / EXCEL_REPORT_NAME
    wb.save(path)
    return path
