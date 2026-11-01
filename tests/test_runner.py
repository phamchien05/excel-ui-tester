"""Kiểm thử bộ chạy test (core/runner.py) với các kịch bản chạy trên trang thử nghiệm."""

from pathlib import Path

import pytest

from core.reader import TestCase, TestStep, TestSuite, read_suite
from core.runner import FAIL, PASS, SKIP, run_suite, slugify


def run_cases(cases: dict, tmp_path, **kwargs):
    suite = TestSuite(name="test", file_path="test.xlsx", cases=[
        TestCase(name, [TestStep(i, kw, sel, val, "") for i, (kw, sel, val) in enumerate(steps, 1)])
        for name, steps in cases.items()
    ])
    return run_suite(suite, tmp_path, timeout_ms=1500, **kwargs)


def test_dang_nhap_thanh_cong_va_that_bai(site_url, tmp_path):
    login = site_url + "login.html"
    result = run_cases({
        "Đúng": [("open", "", login), ("type", "#username", "admin"), ("type", "#password", "123456"),
                 ("click", "#login-btn", ""), ("assert_url", "", "home.html"), ("assert_text", "h1", "Xin chào")],
        "Sai": [("open", "", login), ("type", "#username", "admin"), ("type", "#password", "sai"),
                ("press_key", "#password", "Enter"), ("assert_text", "#error", "Sai tên đăng nhập")],
    }, tmp_path)
    assert [c.status for c in result.cases] == [PASS, PASS]
    assert (result.total, result.passed, result.failed, result.pass_rate) == (2, 2, 0, 100.0)


def test_buoc_loi_thi_dung_chup_anh_va_bo_qua_cac_buoc_sau(site_url, tmp_path):
    result = run_cases({
        "Cố ý sai": [("open", "", site_url + "login.html"), ("assert_text", "h1", "Chữ không có"),
                     ("click", "#login-btn", ""), ("type", "#username", "x")],
        "Case sau vẫn chạy": [("open", "", site_url + "home.html"), ("assert_text", "h1", "Xin chào")],
    }, tmp_path)
    failed, passed = result.cases
    assert failed.status == FAIL
    assert [s.status for s in failed.steps] == [PASS, FAIL, SKIP, SKIP]
    assert failed.error.startswith("Bước 2 (assert_text)")
    assert failed.screenshot and Path(failed.screenshot).exists()
    assert failed.steps[1].screenshot == failed.screenshot
    assert passed.status == PASS                        # Test case sau không bị ảnh hưởng
    assert result.pass_rate == 50.0


def test_tu_khoa_khong_hop_le(site_url, tmp_path):
    result = run_cases({"A": [("open", "", site_url + "home.html"), ("bam_vao", "#x", "")]}, tmp_path)
    assert "Từ khóa không hợp lệ: 'bam_vao'" in result.cases[0].error


def test_het_thoi_gian_cho_bao_loi_de_hieu(site_url, tmp_path):
    result = run_cases({"A": [("open", "", site_url + "home.html"), ("click", "#khong-co", "")]}, tmp_path)
    assert "Hết thời gian chờ (1.5s)" in result.cases[0].error
    assert "Call log" not in result.cases[0].error  # Đã cắt bỏ log dài của Playwright


def test_khong_mo_duoc_trang(tmp_path):
    result = run_cases({"A": [("open", "", "http://127.0.0.1:1/")]}, tmp_path)
    assert result.cases[0].status == FAIL
    assert "Không tải được trang" in result.cases[0].error


def test_moi_test_case_chay_tren_phien_trinh_duyet_doc_lap(site_url, tmp_path):
    # widgets.html đếm lượt xem bằng localStorage. Nếu dùng chung phiên thì lần 2 sẽ là "2"
    page = site_url + "widgets.html"
    result = run_cases({
        "Lần 1": [("open", "", page), ("assert_text", "#visits", "Lượt xem: 1")],
        "Lần 2": [("open", "", page), ("assert_text", "#visits", "Lượt xem: 1")],
    }, tmp_path)
    assert [c.status for c in result.cases] == [PASS, PASS]


def test_ghi_thoi_gian_va_goi_ham_tien_trinh(site_url, tmp_path):
    progress = []
    result = run_cases({"A": [("open", "", site_url + "home.html")], "B": [("wait", "", "0.2")]},
                       tmp_path, on_progress=lambda done, total, case: progress.append((done, total, case.name)))
    assert progress == [(1, 2, "A"), (2, 2, "B")]
    assert result.cases[1].steps[0].duration >= 0.2
    assert result.duration == pytest.approx(sum(c.duration for c in result.cases))
    assert result.end_time >= result.start_time


def test_chay_tu_file_excel_data_driven(site_url, tmp_path, make_excel):
    from openpyxl import load_workbook
    path = make_excel({"Đăng nhập": [
        ("open", "", site_url + "login.html", ""), ("type", "#username", "${u}", ""),
        ("type", "#password", "${p}", ""), ("click", "#login-btn", "", ""),
        ("assert_text", "${sel}", "${kq}", ""),
    ]})
    wb = load_workbook(path)
    ws = wb.create_sheet("DATA")
    for row in [["u", "p", "sel", "kq"], ["admin", "123456", "h1", "Xin chào"],
                ["", "123456", "#error", "Vui lòng nhập tên"], ["admin", "", "#error", "Vui lòng nhập mật khẩu"]]:
        ws.append(row)
    wb.save(path)
    result = run_suite(read_suite(path), tmp_path / "out", timeout_ms=1500)
    assert [c.status for c in result.cases] == [PASS, PASS, PASS]


def test_trinh_duyet_khong_ho_tro(tmp_path):
    with pytest.raises(ValueError, match="không hỗ trợ"):
        run_suite(TestSuite("x", "x.xlsx"), tmp_path, browser_name="ie")


@pytest.mark.parametrize("text, expected", [
    ("Đăng nhập thành công", "dang_nhap_thanh_cong"),
    ("TC01 / Giỏ hàng (3)", "tc01_gio_hang_3"),
    ("!!!", "test"),
])
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_runner_ghi_nhan_loi_javascript_cho_assert_no_js_error(site_url, tmp_path):
    # smoke.html cố ý ném lỗi chưa bắt; home.html không có lỗi
    result = run_cases({
        "Trang có lỗi JS": [("open", "", site_url + "smoke.html"), ("assert_no_js_error", "", "")],
        "Trang không lỗi": [("open", "", site_url + "home.html"), ("assert_no_js_error", "", "")],
    }, tmp_path)
    assert [c.status for c in result.cases] == [FAIL, PASS]
    assert "Lỗi chưa được bắt" in result.cases[0].error
