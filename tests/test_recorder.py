"""Kiểm thử chức năng ghi lại thao tác (core/recorder.py)."""

import pytest

from core.reader import TestCase, TestSuite
from core.recorder import _to_step, record
from core.runner import PASS, run_suite


@pytest.mark.parametrize("payload, expected", [
    ({"action": "click", "selector": "#a", "label": "Gửi"}, ("click", "#a", "", "Bấm 'Gửi'")),
    ({"action": "type", "selector": "#u", "value": "an", "label": "Tên"}, ("type", "#u", "an", "Nhập vào ô Tên")),
    ({"action": "select", "selector": "#s", "value": "hn", "option": "Hà Nội", "label": "TP"},
     ("select", "#s", "hn", "Chọn 'Hà Nội' ở ô TP")),
    ({"action": "press_key", "selector": "#u", "value": "Enter", "label": "Tên"},
     ("press_key", "#u", "Enter", "Nhấn Enter tại ô Tên")),
    ({"action": "assert_text", "selector": "h1", "value": "Xin chào"},
     ("assert_text", "h1", "Xin chào", 'Kiểm tra hiển thị chữ "Xin chào"')),
    ({"action": "assert_visible", "selector": "#x", "label": ""}, ("assert_visible", "#x", "", "Kiểm tra '#x' đang hiển thị")),
    ({"action": "assert_url", "value": "http://h/home.html"}, ("assert_url", "", "/home.html", "Kiểm tra đang ở trang /home.html")),
])
def test_chuyen_thao_tac_thanh_buoc(payload, expected):
    s = _to_step(payload)
    assert (s.keyword, s.selector, s.value, s.description) == expected


def test_thao_tac_khong_ho_tro():
    with pytest.raises(ValueError):
        _to_step({"action": "drag"})


def test_ghi_luong_dang_nhap_roi_phat_lai(site_url, tmp_path):
    def nguoi_dung(page):
        # Playwright sinh sự kiện chuột/bàn phím thật (isTrusted) giống người dùng
        page.click("#username")
        page.keyboard.type("admin")             # Gõ từng ký tự -> phải gộp thành 1 bước
        page.click("#password")
        page.keyboard.type("123456")
        page.click("#login-btn")
        page.wait_for_url("**/home.html")
        page.locator("button[data-a='url']").click()       # Nút "Kiểm tra URL" trên thanh công cụ
        page.locator("button[data-a='text']").click()      # "Kiểm tra chữ" rồi bấm vào tiêu đề
        page.click("h1")
        page.locator("button[data-a='visible']").click()   # "Kiểm tra hiển thị" rồi bấm link
        page.click("#logout")
        page.wait_for_timeout(200)
        page.locator("button[data-a='stop']").click()

    added = []
    steps = record(site_url + "login.html", headless=True, script=nguoi_dung, on_step=added.append)
    assert [(s.keyword, s.selector, s.value) for s in steps] == [
        ("open", "", site_url + "login.html"),
        ("type", "#username", "admin"),
        ("type", "#password", "123456"),
        ("click", "#login-btn", ""),
        ("assert_url", "", "/home.html"),
        ("assert_text", "h1", "Xin chào admin"),
        ("assert_visible", "#logout", ""),
    ]
    assert len(added) == 6                     # Không tính bước open ban đầu
    assert [s.step_no for s in steps] == list(range(1, 8))

    # Chế độ chọn phần tử để kiểm tra không được làm trang chuyển đi (click vào link #logout bị chặn)
    result = run_suite(TestSuite("ghi", "ghi.xlsx", [TestCase("Ghi lại", steps)]), tmp_path, timeout_ms=2000)
    assert result.cases[0].status == PASS


def test_dong_trinh_duyet_thi_ket_thuc_ghi(site_url):
    steps = record(site_url + "widgets.html", headless=True, script=lambda page: (
        page.select_option("#city", "dn"), page.wait_for_timeout(200), page.close()))
    assert [(s.keyword, s.value) for s in steps][1:] == [("select", "dn")]
    assert steps[1].description == "Chọn 'Đà Nẵng' ở ô city"
