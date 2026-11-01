"""
Bộ chạy test (test runner).

Luồng xử lý:
  1. Mở trình duyệt (chromium / firefox / webkit), headless hoặc có giao diện.
  2. Với mỗi test case: tạo một context + trang mới (độc lập cookie, localStorage).
  3. Chạy lần lượt từng bước bằng cách tra từ khóa trong bảng KEYWORDS.
  4. Bước nào lỗi: ghi lỗi, tự chụp màn hình, các bước sau đánh dấu "Bỏ qua",
     rồi chuyển sang test case tiếp theo.
  5. Ghi lại thời gian của từng bước và từng test case.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from core.keywords import KEYWORDS, KeywordContext
from core.reader import TestCase, TestSuite

SUPPORTED_BROWSERS = ("chromium", "firefox", "webkit")

# Trạng thái của bước / test case
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


# ---------------------------------------------------------------------------
# Cấu trúc lưu kết quả
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    step_no: int
    keyword: str
    selector: str
    value: str
    description: str
    status: str = SKIP
    duration: float = 0.0          # giây
    error: str = ""
    screenshot: str | None = None  # Đường dẫn ảnh (ảnh lỗi hoặc ảnh do từ khóa screenshot)


@dataclass
class CaseResult:
    name: str
    status: str = PASS
    duration: float = 0.0
    steps: list[StepResult] = field(default_factory=list)
    error: str = ""
    screenshot: str | None = None  # Ảnh chụp lúc lỗi
    data_row: dict | None = None


@dataclass
class SuiteResult:
    name: str
    file_path: str
    browser: str
    headless: bool
    start_time: datetime
    end_time: datetime | None = None
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.status == PASS)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return round(self.passed * 100 / self.total, 1) if self.total else 0.0

    @property
    def duration(self) -> float:
        return sum(c.duration for c in self.cases)


# ---------------------------------------------------------------------------
# Hàm tiện ích
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Chuyển chuỗi tiếng Việt thành tên file an toàn: 'Đăng nhập' -> 'dang_nhap'."""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:60] or "test"


def _friendly_error(exc: Exception, step, timeout_ms: int) -> str:
    """Rút gọn thông báo lỗi của Playwright thành câu dễ đọc bằng tiếng Việt."""
    if isinstance(exc, PlaywrightTimeoutError):
        if step.keyword == "open":
            return f"Hết thời gian chờ khi mở trang '{step.value or step.selector}' - trang tải quá chậm hoặc không phản hồi"
        return (f"Hết thời gian chờ ({timeout_ms / 1000:g}s) khi thực hiện '{step.keyword}' "
                f"với selector '{step.selector}' - phần tử không tồn tại hoặc không thao tác được")
    message = str(exc).strip()
    # Lỗi Playwright thường kèm "Call log" rất dài -> chỉ giữ phần đầu
    message = message.split("Call log:")[0].strip()
    if isinstance(exc, PlaywrightError) and "net::" in message:
        return f"Không tải được trang: {message.splitlines()[0]}"
    return message.splitlines()[0] if message else exc.__class__.__name__


# ---------------------------------------------------------------------------
# Mở trình duyệt (dùng chung cho runner, smoke, generator, recorder)
# ---------------------------------------------------------------------------

class BrowserNotInstalledError(RuntimeError):
    """Trình duyệt chưa được Playwright tải về máy."""


def install_command(browser_name: str) -> str:
    return f"python -m playwright install {browser_name}"


def launch_browser(playwright, browser_name: str, **kwargs):
    """Mở trình duyệt. Nếu chưa cài thì báo lỗi tiếng Việt kèm lệnh cài thay cho thông báo dài của Playwright."""
    if browser_name not in SUPPORTED_BROWSERS:
        raise ValueError(f"Trình duyệt không hỗ trợ: {browser_name}. Chọn một trong {SUPPORTED_BROWSERS}")
    try:
        return getattr(playwright, browser_name).launch(**kwargs)
    except PlaywrightError as exc:
        if "Executable doesn't exist" in str(exc):
            raise BrowserNotInstalledError(
                f"Chưa cài trình duyệt {browser_name}. Hãy chạy lệnh: {install_command(browser_name)}") from None
        raise


def installed_browsers() -> dict[str, bool]:
    """Kiểm tra trình duyệt nào đã được cài: {'chromium': True, 'firefox': False, ...}"""
    with sync_playwright() as p:
        return {name: Path(getattr(p, name).executable_path).exists() for name in SUPPORTED_BROWSERS}


# ---------------------------------------------------------------------------
# Chạy test
# ---------------------------------------------------------------------------

def run_case(browser, case: TestCase, screenshot_dir: Path, timeout_ms: int) -> CaseResult:
    """Chạy một test case trên một context trình duyệt mới."""
    result = CaseResult(name=case.name, data_row=case.data_row)
    result.steps = [StepResult(s.step_no, s.keyword, s.selector, s.value, s.description)
                    for s in case.steps]

    # Context mới = phiên trình duyệt độc lập (giống cửa sổ ẩn danh mới)
    context = browser.new_context(viewport={"width": 1366, "height": 768})
    page = context.new_page()
    page.set_default_timeout(timeout_ms)
    ctx = KeywordContext(screenshot_dir=screenshot_dir, case_slug=slugify(case.name),
                         timeout_ms=timeout_ms)
    # Ghi lại lỗi JavaScript chưa được bắt (dùng cho từ khóa assert_no_js_error)
    page.on("pageerror", lambda exc: ctx.js_errors.append(str(exc).splitlines()[0]))

    case_start = time.perf_counter()
    try:
        for step, step_result in zip(case.steps, result.steps):
            ctx.step_no = step.step_no
            func = KEYWORDS.get(step.keyword)
            step_start = time.perf_counter()
            try:
                if func is None:
                    raise ValueError(f"Từ khóa không hợp lệ: '{step.keyword}'. "
                                     f"Các từ khóa hỗ trợ: {', '.join(KEYWORDS)}")
                step_result.screenshot = func(page, step.selector, step.value, ctx)
                step_result.status = PASS
            except Exception as exc:  # Bất kỳ lỗi nào cũng làm bước này FAIL
                step_result.status = FAIL
                step_result.error = _friendly_error(exc, step, timeout_ms)
                step_result.screenshot = _capture_failure(page, screenshot_dir, ctx)
                result.status = FAIL
                result.error = f"Bước {step.step_no} ({step.keyword}): {step_result.error}"
                result.screenshot = step_result.screenshot
            finally:
                step_result.duration = round(time.perf_counter() - step_start, 3)

            if step_result.status == FAIL:
                break  # Dừng test case, các bước còn lại giữ trạng thái SKIP
    finally:
        result.duration = round(time.perf_counter() - case_start, 3)
        context.close()
    return result


def _capture_failure(page, screenshot_dir: Path, ctx: KeywordContext) -> str | None:
    """Chụp màn hình khi bước bị lỗi. Nếu chụp không được thì bỏ qua."""
    path = screenshot_dir / f"LOI_{ctx.case_slug}_buoc{ctx.step_no}.png"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=False, timeout=5000)
        return str(path)
    except Exception:
        return None


def run_suite(
    suite: TestSuite,
    output_dir: str | Path,
    browser_name: str = "chromium",
    headless: bool = True,
    timeout_ms: int = 10_000,
    on_progress: Callable[[int, int, CaseResult], None] | None = None,
) -> SuiteResult:
    """
    Chạy toàn bộ test case trong bộ test.

    on_progress(số_case_đã_chạy, tổng_số_case, kết_quả_case_vừa_chạy) được gọi sau
    mỗi test case -> dùng để cập nhật thanh tiến trình trên giao diện.
    """
    if browser_name not in SUPPORTED_BROWSERS:
        raise ValueError(f"Trình duyệt không hỗ trợ: {browser_name}. Chọn một trong {SUPPORTED_BROWSERS}")

    output_dir = Path(output_dir)
    screenshot_dir = output_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    cases = suite.cases
    result = SuiteResult(name=suite.name, file_path=suite.file_path, browser=browser_name,
                         headless=headless, start_time=datetime.now())

    with sync_playwright() as p:
        browser = launch_browser(p, browser_name, headless=headless)
        try:
            for index, case in enumerate(cases, start=1):
                case_result = run_case(browser, case, screenshot_dir, timeout_ms)
                result.cases.append(case_result)
                if on_progress:
                    on_progress(index, len(cases), case_result)
        finally:
            browser.close()

    result.end_time = datetime.now()
    return result
