"""Kiểm thử sinh báo cáo HTML (core/reporter.py) và xuất kết quả Excel (core/excel_report.py)."""

import base64
from datetime import datetime

import pytest
from openpyxl import load_workbook

from core.excel_report import export_excel_report
from core.reporter import generate_report, generate_smoke_report, image_to_data_uri
from core.runner import CaseResult, StepResult, SuiteResult
from core.smoke import ImageResult, LinkResult, SmokeResult

# Ảnh PNG 1x1 điểm ảnh
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture
def suite_result(tmp_path):
    """Kết quả giả lập: 1 case đạt (data-driven), 1 case lỗi có ảnh chụp và nội dung lỗi chứa thẻ HTML."""
    shot = tmp_path / "screenshots" / "LOI_case_b_buoc2.png"
    shot.parent.mkdir()
    shot.write_bytes(PNG)
    ok = CaseResult("Case A", "PASS", 1.25, [
        StepResult(1, "open", "", "http://x", "Mở trang", "PASS", 0.5),
        StepResult(2, "assert_text", "h1", "Xin chào", "", "PASS", 0.75),
    ], data_row={"user": "admin", "pass": ""})
    bad = CaseResult("Case B", "FAIL", 2.0, [
        StepResult(1, "click", "#a", "", "Bấm nút", "PASS", 0.1),
        StepResult(2, "assert_text", ".msg", "<script>", "Kiểm tra thông báo", "FAIL", 1.9,
                   error="Mong đợi chứa \"<script>alert(1)</script>\"", screenshot=str(shot)),
        StepResult(3, "click", "#b", "", "Bước bị bỏ qua", "SKIP"),
    ], error="Bước 2 (assert_text): lỗi", screenshot=str(shot))
    return SuiteResult("bo_test", "bo_test.xlsx", "chromium", True,
                       datetime(2026, 1, 2, 3, 4, 5), datetime(2026, 1, 2, 3, 4, 9), [ok, bad])


def test_thong_ke(suite_result):
    r = suite_result
    assert (r.total, r.passed, r.failed, r.pass_rate, r.duration) == (2, 1, 1, 50.0, 3.25)


def test_bao_cao_html(suite_result, tmp_path):
    html = generate_report(suite_result, tmp_path).read_text(encoding="utf-8")
    assert "Báo cáo kiểm thử: bo_test" in html
    assert "Case A" in html and "Case B" in html
    assert "50.0%" in html
    assert "data:image/png;base64," in html                     # Ảnh lỗi được nhúng vào HTML
    assert "<script>alert(1)</script>" not in html               # Nội dung lỗi được escape, không chạy được
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "user = admin" in html and "pass = (trống)" in html   # Hiện dữ liệu data-driven
    assert "Bỏ qua" in html


def test_anh_khong_ton_tai_tra_ve_chuoi_rong(tmp_path):
    assert image_to_data_uri(None) == ""
    assert image_to_data_uri(str(tmp_path / "khong_co.png")) == ""


def test_bao_cao_kiem_tra_nhanh(tmp_path):
    shot = tmp_path / "a.jpg"
    shot.write_bytes(PNG)
    r = SmokeResult("http://x", "chromium", datetime.now(), page_ok=True, status=200, load_time=0.5,
                    title="Trang X", links=[LinkResult("http://x/a", 200), LinkResult("http://x/b", 404, "Không tìm thấy trang")],
                    images=[ImageResult("http://x/i.png", None, True, "HTTP 404")],
                    console_errors=["Lỗi <b>JS</b>"], screenshots={"Máy tính (1366px)": str(shot), "Tablet (768px)": None})
    html = generate_smoke_report(r, tmp_path).read_text(encoding="utf-8")
    assert "Kiểm tra nhanh: Trang X" in html
    assert "http://x/b" in html and "Không tìm thấy trang" in html
    assert "Thiếu alt" in html
    assert "Lỗi &lt;b&gt;JS&lt;/b&gt;" in html
    assert "Không chụp được ảnh" in html


def test_xuat_excel_dung_mau_test_case(suite_result, tmp_path):
    wb = load_workbook(export_excel_report(suite_result, tmp_path))
    assert wb.sheetnames == ["Tổng quan", "Test case", "Chi tiết bước"]

    overview = {row[0]: row[1] for row in wb["Tổng quan"].iter_rows(min_row=2, values_only=True)}
    assert overview["Tổng số test case"] == 2 and overview["Tỷ lệ đạt"] == "50.0%"
    assert overview["Bắt đầu"] == "02/01/2026 03:04:05"

    ws = wb["Test case"]
    headers = [c.value for c in ws[1]]
    assert headers[:7] == ["ID", "Tên test case", "Dữ liệu", "Các bước thực hiện", "Kết quả mong đợi",
                           "Kết quả thực tế", "Trạng thái"]
    a = [c.value for c in ws[2]]
    b = [c.value for c in ws[3]]
    assert a[0] == "TC01" and a[2] == "user = admin\npass = (trống)"
    assert a[3] == "1. Mở trang"                        # Các bước thao tác (không gồm bước kiểm tra)
    assert a[4] == '- assert_text h1 "Xin chào"'        # Kết quả mong đợi từ bước kiểm tra
    assert (a[5], a[6]) == ("Đúng như mong đợi", "Đạt")
    assert (b[5], b[6]) == ("Bước 2 (assert_text): lỗi", "Lỗi")
    assert b[8] == "screenshots/LOI_case_b_buoc2.png" and ws.cell(row=3, column=9).hyperlink
    assert ws.cell(row=3, column=7).fill.fgColor.rgb.endswith("FEE2E2")  # Ô "Lỗi" tô đỏ

    steps = list(wb["Chi tiết bước"].iter_rows(min_row=2, values_only=True))
    assert len(steps) == 5
    assert steps[4][6] == "Bỏ qua" and steps[4][7] in ("", None)
