"""
Kiểm thử từng từ khóa (core/keywords.py) trên trình duyệt thật với trang thử nghiệm.
Mỗi từ khóa có ít nhất một test trường hợp đúng và (với từ khóa kiểm tra) một test trường hợp sai.
"""

import pytest
from playwright.sync_api import sync_playwright

from core.keywords import KEYWORD_DOCS, KEYWORDS, KeywordContext

TIMEOUT_MS = 1500  # Thời gian chờ ngắn để các test "phải lỗi" chạy nhanh


@pytest.fixture(scope="module")
def browser():
    # Phạm vi module: đóng Playwright khi xong file này, tránh xung đột với run_suite ở file khác
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser, site_url):
    context = browser.new_context()
    pg = context.new_page()
    pg.set_default_timeout(TIMEOUT_MS)
    pg.goto(site_url + "widgets.html")
    yield pg
    context.close()


@pytest.fixture
def ctx(tmp_path):
    return KeywordContext(screenshot_dir=tmp_path, case_slug="test", timeout_ms=TIMEOUT_MS, step_no=3)


def run(keyword, page, ctx, selector="", value=""):
    """Gọi từ khóa giống như runner gọi."""
    return KEYWORDS[keyword](page, selector, value, ctx)


def test_du_18_tu_khoa_va_co_mo_ta():
    assert len(KEYWORDS) == 18
    assert set(KEYWORDS) == set(KEYWORD_DOCS)
    assert all(doc["doc"] for doc in KEYWORD_DOCS.values())


# ----- Thao tác -----

def test_open_dung_cot_gia_tri_hoac_selector(page, ctx, site_url):
    run("open", page, ctx, value=site_url + "home.html")
    assert page.url.endswith("home.html")
    run("open", page, ctx, selector=site_url + "login.html")
    assert page.url.endswith("login.html")


def test_open_thieu_url(page, ctx):
    with pytest.raises(ValueError, match="Thiếu URL"):
        run("open", page, ctx)


def test_click(page, ctx):
    run("click", page, ctx, "#to-home")
    page.wait_for_url("**/home.html")


def test_click_selector_dang_text(page, ctx):
    run("click", page, ctx, "text=Về trang chủ")
    page.wait_for_url("**/home.html")


def test_thieu_selector_bao_loi(page, ctx):
    with pytest.raises(ValueError, match="bắt buộc phải có Selector"):
        run("click", page, ctx, "")


def test_type_xoa_noi_dung_cu_roi_nhap(page, ctx):
    run("type", page, ctx, "#name", "Nguyễn Văn A")
    assert page.input_value("#name") == "Nguyễn Văn A"


def test_clear(page, ctx):
    run("clear", page, ctx, "#name")
    assert page.input_value("#name") == ""


@pytest.mark.parametrize("value", ["hcm", "TP Hồ Chí Minh"])
def test_select_theo_value_hoac_nhan(page, ctx, value):
    run("select", page, ctx, "#city", value)
    assert page.input_value("#city") == "hcm"
    assert page.inner_text("#city-result") == "Đã chọn: hcm"


def test_hover(page, ctx):
    run("hover", page, ctx, "#hover-box")
    assert page.inner_text("#hover-result") == "Đã rê chuột"


def test_press_key_tren_phan_tu(page, ctx):
    run("press_key", page, ctx, "#keys", "Enter")
    assert page.inner_text("#key-result") == "Phím: Enter"


def test_press_key_toan_trang(page, ctx):
    page.focus("#keys")
    run("press_key", page, ctx, "", "Tab")
    assert page.inner_text("#key-result") == "Phím: Tab"


def test_press_key_thieu_ten_phim(page, ctx):
    with pytest.raises(ValueError, match="Thiếu tên phím"):
        run("press_key", page, ctx, "#keys", "")


def test_wait(page, ctx):
    import time
    start = time.perf_counter()
    run("wait", page, ctx, value="0.3")
    assert time.perf_counter() - start >= 0.3


def test_wait_for_phan_tu_xuat_hien_sau(page, ctx):
    page.click("#show-later")
    run("wait_for", page, ctx, "#late", "3")
    assert page.is_visible("#late")


def test_wait_for_het_thoi_gian(page, ctx):
    with pytest.raises(Exception):
        run("wait_for", page, ctx, "#hidden-el", "0.3")


def test_screenshot_toan_trang_ten_mac_dinh(page, ctx, tmp_path):
    path = run("screenshot", page, ctx)
    assert path.endswith("test_buoc3.png")
    assert (tmp_path / "test_buoc3.png").stat().st_size > 0


def test_screenshot_mot_phan_tu_ten_tuy_chon(page, ctx, tmp_path):
    run("screenshot", page, ctx, "#hover-box", "hop_xam")
    assert (tmp_path / "hop_xam.png").exists()


# ----- Kiểm tra (assertion): trường hợp đúng -----

def test_assert_dung(page, ctx):
    run("assert_text", page, ctx, "h1", "thành phần")         # Chứa một phần văn bản
    run("assert_text", page, ctx, "", "Rê chuột vào đây")      # Không selector -> tìm cả trang
    run("assert_visible", page, ctx, "#hover-box")
    run("assert_not_visible", page, ctx, "#hidden-el")
    run("assert_not_visible", page, ctx, "#khong-ton-tai")     # Không tồn tại cũng coi là không hiển thị
    run("assert_url", page, ctx, value="widgets.html")
    run("assert_title", page, ctx, value="Thành phần")
    run("assert_value", page, ctx, "#name", "Giá trị ban đầu")


# ----- Kiểm tra (assertion): trường hợp sai phải báo lỗi rõ ràng -----

@pytest.mark.parametrize("keyword, selector, value, message", [
    ("assert_text", "h1", "Không có chữ này", 'thực tế là "Các thành phần"'),
    ("assert_text", "#khong-ton-tai", "abc", "<không tìm thấy phần tử>"),
    ("assert_visible", "#hidden-el", "", "hiển thị nhưng không thấy"),
    ("assert_not_visible", "#hover-box", "", "vẫn hiển thị"),
    ("assert_url", "", "trang-khac.html", "widgets.html"),
    ("assert_title", "", "Tiêu đề khác", "Thành phần - Trang thử nghiệm"),
    ("assert_value", "#name", "sai", 'thực tế là "Giá trị ban đầu"'),
])
def test_assert_sai_bao_loi_tieng_viet(page, ctx, keyword, selector, value, message):
    with pytest.raises(AssertionError, match="Mong đợi") as err:
        run(keyword, page, ctx, selector, value)
    assert message in str(err.value)


def test_assert_invalid(page, ctx, site_url):
    page.goto(site_url + "register.html")
    run("assert_invalid", page, ctx, "#fullname")  # Ô required đang trống -> không hợp lệ
    page.fill("#fullname", "An")
    with pytest.raises(AssertionError, match="coi là hợp lệ"):
        run("assert_invalid", page, ctx, "#fullname")


def test_assert_no_js_error(page, ctx):
    run("assert_no_js_error", page, ctx)                        # Chưa có lỗi -> đạt
    ctx.js_errors += ["ReferenceError: x is not defined", "TypeError: y"]
    with pytest.raises(AssertionError, match=r'trang có lỗi: "ReferenceError: x is not defined" \(và 1 lỗi khác\)'):
        run("assert_no_js_error", page, ctx)
