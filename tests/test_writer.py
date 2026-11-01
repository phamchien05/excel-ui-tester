"""Kiểm thử module ghi Excel (core/writer.py)."""

from openpyxl import load_workbook

from core.reader import TestCase, TestStep, read_suite
from core.writer import NOTES_SHEET_NAME, safe_sheet_name, write_cases


def test_ghi_roi_doc_lai_giu_nguyen_noi_dung(tmp_path):
    cases = [
        TestCase("Đăng nhập", [TestStep(1, "open", "", "http://x", "Mở trang"),
                               TestStep(2, "type", "#u", "admin", "Nhập tên")]),
        TestCase("Đăng xuất", [TestStep(1, "click", "#logout", "", "")]),
    ]
    path = write_cases(tmp_path / "out.xlsx", cases, notes=["Ghi chú 1"])
    suite = read_suite(path)
    assert [c.name for c in suite.cases] == ["Đăng nhập", "Đăng xuất"]  # Sheet ghi chú bị bỏ qua
    assert [(s.keyword, s.selector, s.value) for s in suite.cases[0].steps] == [
        ("open", "", "http://x"), ("type", "#u", "admin")]


def test_sheet_ghi_chu_duoc_tao(tmp_path):
    path = write_cases(tmp_path / "out.xlsx", [TestCase("A", [TestStep(1, "open", "", "x")])],
                       notes=["Dòng 1", "Dòng 2"])
    wb = load_workbook(path)
    assert wb.sheetnames == ["A", NOTES_SHEET_NAME]
    assert wb[NOTES_SHEET_NAME]["A3"].value == "Dòng 2"


def test_dong_tu_ghi_nhan_va_can_xem_lai_duoc_to_mau(tmp_path):
    steps = [TestStep(1, "open", "", "x"), TestStep(2, "assert_url", "", "a", note="auto"),
             TestStep(3, "assert_text", "", "b", note="review")]
    wb = load_workbook(write_cases(tmp_path / "out.xlsx", [TestCase("A", steps)]))
    ws = wb["A"]
    colors = [ws.cell(row=r, column=1).fill.fgColor.rgb for r in (2, 3, 4)]
    assert colors[0] in (None, "00000000")  # Dòng thường: không tô
    assert colors[1].endswith("FFF2CC")     # Vàng
    assert colors[2].endswith("F8CBAD")     # Cam


def test_ten_sheet_bo_ky_tu_cam_va_cat_31_ky_tu():
    used = set()
    assert safe_sheet_name("A/B:C*D?[E]", used) == "A-B-C-D--E-"
    long_name = safe_sheet_name("x" * 50, used)
    assert len(long_name) == 31


def test_ten_sheet_trung_duoc_danh_so():
    used = set()
    assert safe_sheet_name("Test", used) == "Test"
    assert safe_sheet_name("test", used) == "test (2)"  # Excel không phân biệt hoa thường
    assert safe_sheet_name("Test", used) == "Test (3)"


def test_ten_sheet_dac_biet_khong_bi_dung():
    used = set()
    assert safe_sheet_name("DATA", used) == "DATA (2)"     # Tránh bị hiểu là sheet dữ liệu
    assert safe_sheet_name(NOTES_SHEET_NAME, used) != NOTES_SHEET_NAME
    assert safe_sheet_name("", used) == "Test"
