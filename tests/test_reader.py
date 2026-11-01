"""Kiểm thử module đọc Excel (core/reader.py)."""

import pytest
from openpyxl import Workbook

from core.reader import TestCase, TestStep, expand_data_driven, read_suite, substitute


def save_workbook(path, sheets: dict):
    """Tạo file Excel với các sheet cho trước: {tên_sheet: [dòng1, dòng2, ...]}"""
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    wb.save(path)
    return path


HEADER = ["Bước", "Từ khóa", "Selector", "Giá trị", "Mô tả"]


# ---------------------------------------------------------------------------
# Đọc sheet kịch bản
# ---------------------------------------------------------------------------

def test_moi_sheet_la_mot_test_case(tmp_path):
    path = save_workbook(tmp_path / "a.xlsx", {
        "Case A": [HEADER, [1, "open", "", "http://x", "Mở trang"]],
        "Case B": [HEADER, [1, "click", "#btn", "", ""], [2, "assert_url", "", "home", ""]],
    })
    suite = read_suite(path)
    assert suite.name == "a"
    assert [c.name for c in suite.cases] == ["Case A", "Case B"]
    assert len(suite.cases[1].steps) == 2
    step = suite.cases[0].steps[0]
    assert (step.step_no, step.keyword, step.value, step.description) == (1, "open", "http://x", "Mở trang")


def test_tu_khoa_viet_hoa_duoc_chuyen_ve_chu_thuong(tmp_path):
    path = save_workbook(tmp_path / "a.xlsx", {"C": [HEADER, [1, "  CLICK ", "#a", "", ""]]})
    assert read_suite(path).cases[0].steps[0].keyword == "click"


def test_bo_qua_dong_trong_va_dong_khong_co_tu_khoa(tmp_path):
    path = save_workbook(tmp_path / "a.xlsx", {"C": [
        HEADER, [1, "open", "", "http://x", ""], [None, None, None, None, None],
        [2, "", "#ghi-chu", "", "dòng ghi chú"], [3, "click", "#b", "", ""],
    ]})
    assert [s.keyword for s in read_suite(path).cases[0].steps] == ["open", "click"]


def test_so_nguyen_dang_float_duoc_doi_thanh_chuoi_so_nguyen(tmp_path):
    # Excel lưu số 3 thành 3.0 -> phải đọc ra "3" chứ không phải "3.0"
    path = save_workbook(tmp_path / "a.xlsx", {"C": [HEADER, [1.0, "assert_text", ".badge", 3.0, ""]]})
    step = read_suite(path).cases[0].steps[0]
    assert step.step_no == 1
    assert step.value == "3"


def test_cot_tieng_anh_va_thu_tu_cot_khac(tmp_path):
    path = save_workbook(tmp_path / "a.xlsx", {"C": [
        ["Keyword", "Value", "Selector", "Description"],
        ["type", "xin chào", "#name", "nhập tên"],
    ]})
    step = read_suite(path).cases[0].steps[0]
    assert (step.keyword, step.selector, step.value, step.description) == ("type", "#name", "xin chào", "nhập tên")
    assert step.step_no == 1  # Không có cột Bước -> tự đánh số


def test_sheet_khong_co_cot_tu_khoa_bi_bo_qua(tmp_path):
    path = save_workbook(tmp_path / "a.xlsx", {
        "Ghi chú": [["Nội dung"], ["Đây là ghi chú"]],
        "Trống": [],
        "Case": [HEADER, [1, "open", "", "http://x", ""]],
    })
    assert [c.name for c in read_suite(path).cases] == ["Case"]


def test_file_khong_ton_tai(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_suite(tmp_path / "khong_co.xlsx")


# ---------------------------------------------------------------------------
# Data-driven
# ---------------------------------------------------------------------------

def test_thay_bien():
    assert substitute("Xin chào ${ten}!", {"ten": "An"}) == "Xin chào An!"
    assert substitute("${ a }-${b}", {"a": "1", "b": "2"}) == "1-2"  # Cho phép khoảng trắng trong ${ }


def test_bien_khong_co_trong_du_lieu_duoc_giu_nguyen():
    assert substitute("${khong_co}", {"ten": "An"}) == "${khong_co}"


def test_moi_dong_data_sinh_mot_test_case(tmp_path):
    path = save_workbook(tmp_path / "a.xlsx", {
        "Đăng nhập": [HEADER, [1, "type", "#user", "${user}", "Nhập ${user}"]],
        "Không dùng biến": [HEADER, [1, "open", "", "http://x", ""]],
        "DATA": [["truong_hop", "user"], ["Đúng", "admin"], [None, None], ["Sai", "guest"]],
    })
    suite = read_suite(path)
    assert len(suite.data) == 2  # Dòng trống trong DATA bị bỏ qua
    names = [c.name for c in suite.cases]
    assert names == ["Đăng nhập [#1: Đúng]", "Đăng nhập [#2: Sai]", "Không dùng biến"]
    assert suite.cases[0].steps[0].value == "admin"
    assert suite.cases[1].steps[0].description == "Nhập guest"
    assert suite.cases[1].data_row == {"truong_hop": "Sai", "user": "guest"}
    assert suite.cases[2].data_row is None


def test_khong_co_data_thi_giu_nguyen():
    cases = [TestCase("A", [TestStep(1, "type", "#a", "${x}")])]
    assert expand_data_driven(cases, []) is cases


def test_gia_tri_dau_tien_rong_thi_nhan_la_trong():
    cases = [TestCase("A", [TestStep(1, "type", "#a", "${u}")])]
    result = expand_data_driven(cases, [{"u": ""}])
    assert result[0].name == "A [#1: (trống)]"
