"""
Kiểm thử chạy trên cả 3 trình duyệt (chromium, firefox, webkit) và xử lý khi trình duyệt chưa được cài.
Trình duyệt nào chưa cài trên máy thì test tương ứng được bỏ qua (skip).
"""

import pytest
from playwright.sync_api import Error as PlaywrightError

from core.reader import TestCase, TestStep, TestSuite
from core.recorder import record
from core.runner import (PASS, SUPPORTED_BROWSERS, BrowserNotInstalledError, installed_browsers, launch_browser,
                         run_suite)
from core.smoke import smoke_check

INSTALLED = installed_browsers()
BROWSERS = [pytest.param(b, marks=pytest.mark.skipif(not INSTALLED[b], reason=f"{b} chưa được cài"))
            for b in SUPPORTED_BROWSERS]


@pytest.mark.parametrize("browser", BROWSERS)
def test_chay_kich_ban(browser, site_url, tmp_path):
    steps = [("open", "", site_url + "login.html"), ("type", "#username", "admin"), ("type", "#password", "123456"),
             ("click", "#login-btn", ""), ("assert_url", "", "home.html"), ("assert_text", "h1", "Xin chào")]
    suite = TestSuite("t", "t.xlsx", [TestCase("Đăng nhập", [TestStep(i, *s) for i, s in enumerate(steps, 1)])])
    result = run_suite(suite, tmp_path, browser_name=browser, timeout_ms=5000)
    assert result.browser == browser and result.cases[0].status == PASS, result.cases[0].error


@pytest.mark.parametrize("browser", BROWSERS)
def test_kiem_tra_nhanh(browser, site_url, tmp_path):
    r = smoke_check(site_url + "smoke.html", tmp_path, browser_name=browser)
    assert r.page_ok and len(r.broken_links) == 1 and len(r.broken_images) == 1
    assert len(r.screenshots) == 3 and all(r.screenshots.values())


@pytest.mark.parametrize("browser", BROWSERS)
def test_ghi_lai_thao_tac(browser, site_url):
    def nguoi_dung(page):
        page.click("#username")
        page.keyboard.type("admin")
        page.locator("button[data-a='stop']").click()

    steps = record(site_url + "login.html", browser_name=browser, headless=True, script=nguoi_dung)
    assert [(s.keyword, s.selector, s.value) for s in steps][1:] == [("type", "#username", "admin")]


class FakeBrowserType:
    """Giả lập trình duyệt chưa cài: launch() ném lỗi giống Playwright."""

    def launch(self, **kwargs):
        raise PlaywrightError("BrowserType.launch: Executable doesn't exist at C:\\...\\Playwright.exe")


class FakePlaywright:
    webkit = FakeBrowserType()


def test_bao_loi_de_hieu_khi_chua_cai_trinh_duyet():
    with pytest.raises(BrowserNotInstalledError) as err:
        launch_browser(FakePlaywright(), "webkit", headless=True)
    assert str(err.value) == "Chưa cài trình duyệt webkit. Hãy chạy lệnh: python -m playwright install webkit"


def test_trinh_duyet_khong_ho_tro():
    with pytest.raises(ValueError, match="không hỗ trợ"):
        launch_browser(FakePlaywright(), "ie")


def test_danh_sach_trinh_duyet_da_cai():
    assert set(INSTALLED) == set(SUPPORTED_BROWSERS)
    assert all(isinstance(v, bool) for v in INSTALLED.values())
