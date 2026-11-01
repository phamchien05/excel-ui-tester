"""
Định nghĩa các từ khóa (keyword) dùng trong kịch bản Excel.

Mỗi từ khóa là một hàm Python nhận vào:
    page     : trang trình duyệt Playwright đang chạy
    selector : cột "Selector" trong Excel (CSS như #id, .class hoặc text=...)
    value    : cột "Giá trị" trong Excel
    ctx      : KeywordContext - thông tin phụ (thư mục lưu ảnh, timeout, ...)

Hàm trả về đường dẫn ảnh chụp (nếu có) hoặc None.
Khi kiểm tra sai, hàm ném ra AssertionError -> runner sẽ đánh dấu bước FAIL.

Để thêm từ khóa mới chỉ cần viết hàm và gắn decorator @keyword("ten_tu_khoa").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from playwright.sync_api import Locator, Page, expect

# Bảng tra cứu: tên từ khóa -> hàm xử lý
KEYWORDS: dict[str, Callable] = {}

# Mô tả ngắn từng từ khóa (dùng cho tab Hướng dẫn và README)
KEYWORD_DOCS: dict[str, dict] = {}


@dataclass
class KeywordContext:
    """Thông tin dùng chung cho các từ khóa trong một test case."""
    screenshot_dir: Path        # Thư mục lưu ảnh chụp màn hình
    case_slug: str              # Tên test case đã chuẩn hóa (dùng đặt tên file ảnh)
    timeout_ms: int = 10_000    # Thời gian chờ tối đa cho mỗi thao tác
    step_no: int = 0            # Số thứ tự bước hiện tại
    js_errors: list = field(default_factory=list)  # Lỗi JavaScript chưa được bắt trên trang (runner ghi vào)


def keyword(name: str, selector: str = "", value: str = "", doc: str = ""):
    """Decorator đăng ký một hàm làm từ khóa."""
    def decorator(func):
        KEYWORDS[name] = func
        KEYWORD_DOCS[name] = {"selector": selector, "value": value, "doc": doc}
        return func
    return decorator


def _locate(page: Page, selector: str) -> Locator:
    """Tìm phần tử theo selector. Nếu có nhiều phần tử khớp thì lấy phần tử đầu tiên."""
    if not selector:
        raise ValueError("Từ khóa này bắt buộc phải có Selector")
    return page.locator(selector).first


# ---------------------------------------------------------------------------
# Nhóm thao tác (action)
# ---------------------------------------------------------------------------

@keyword("open", value="URL", doc="Mở một trang web")
def kw_open(page: Page, selector: str, value: str, ctx: KeywordContext):
    url = value or selector  # Cho phép ghi URL ở cột Giá trị hoặc cột Selector
    if not url:
        raise ValueError("Thiếu URL cần mở")
    # Chỉ chờ HTML tải xong (domcontentloaded), không chờ quảng cáo/script bên thứ ba
    # -> ổn định hơn; các bước sau đã tự chờ phần tử cần dùng.
    # Tải trang phụ thuộc mạng nên cho thời gian chờ tối thiểu 30 giây.
    page.goto(url, wait_until="domcontentloaded", timeout=max(ctx.timeout_ms, 30_000))


@keyword("click", selector="bắt buộc", doc="Nhấp chuột vào phần tử")
def kw_click(page, selector, value, ctx):
    _locate(page, selector).click()


@keyword("type", selector="bắt buộc", value="nội dung", doc="Nhập văn bản vào ô (xóa nội dung cũ trước)")
def kw_type(page, selector, value, ctx):
    _locate(page, selector).fill(value)


@keyword("clear", selector="bắt buộc", doc="Xóa nội dung ô nhập")
def kw_clear(page, selector, value, ctx):
    _locate(page, selector).fill("")


@keyword("select", selector="bắt buộc", value="value hoặc nhãn", doc="Chọn một lựa chọn trong ô <select>")
def kw_select(page, selector, value, ctx):
    loc = _locate(page, selector)
    try:
        loc.select_option(value=value, timeout=ctx.timeout_ms)
    except Exception:
        # Không khớp theo value thì thử khớp theo nhãn hiển thị
        loc.select_option(label=value, timeout=ctx.timeout_ms)


@keyword("hover", selector="bắt buộc", doc="Rê chuột lên phần tử")
def kw_hover(page, selector, value, ctx):
    _locate(page, selector).hover()


@keyword("press_key", selector="tùy chọn", value="tên phím, VD: Enter, Tab, Control+A",
         doc="Nhấn phím. Có selector thì nhấn trên phần tử đó")
def kw_press_key(page, selector, value, ctx):
    if not value:
        raise ValueError("Thiếu tên phím cần nhấn")
    if selector:
        _locate(page, selector).press(value)
    else:
        page.keyboard.press(value)


@keyword("wait", value="số giây", doc="Chờ cố định một khoảng thời gian")
def kw_wait(page, selector, value, ctx):
    seconds = float(value or 1)
    page.wait_for_timeout(seconds * 1000)


@keyword("wait_for", selector="bắt buộc", value="số giây tối đa (tùy chọn)",
         doc="Chờ đến khi phần tử xuất hiện")
def kw_wait_for(page, selector, value, ctx):
    timeout = float(value) * 1000 if value else ctx.timeout_ms
    _locate(page, selector).wait_for(state="visible", timeout=timeout)


@keyword("screenshot", value="tên file (tùy chọn)", doc="Chụp ảnh màn hình trang hiện tại")
def kw_screenshot(page, selector, value, ctx):
    name = value or f"{ctx.case_slug}_buoc{ctx.step_no}"
    path = ctx.screenshot_dir / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    if selector:  # Có selector thì chỉ chụp phần tử đó
        _locate(page, selector).screenshot(path=str(path))
    else:
        page.screenshot(path=str(path), full_page=True)
    return str(path)


# ---------------------------------------------------------------------------
# Nhóm kiểm tra (assertion)
# Dùng expect() của Playwright để tự động chờ đến khi điều kiện đúng
# (hoặc hết timeout) -> giảm lỗi chập chờn do trang tải chậm.
# ---------------------------------------------------------------------------

@keyword("assert_text", selector="tùy chọn", value="văn bản mong đợi",
         doc="Kiểm tra phần tử (hoặc cả trang nếu bỏ trống selector) có chứa văn bản")
def kw_assert_text(page, selector, value, ctx):
    loc = _locate(page, selector) if selector else page.locator("body")
    try:
        expect(loc).to_contain_text(value, timeout=ctx.timeout_ms)
    except AssertionError:
        # Lấy nội dung thực tế để thông báo lỗi dễ hiểu hơn
        try:
            actual = loc.inner_text(timeout=1000).strip()
            actual = actual if len(actual) <= 200 else actual[:200] + "..."
        except Exception:
            actual = "<không tìm thấy phần tử>"
        raise AssertionError(
            f"Mong đợi '{selector or 'trang'}' chứa văn bản \"{value}\" nhưng thực tế là \"{actual}\""
        ) from None


@keyword("assert_value", selector="bắt buộc", value="giá trị mong đợi",
         doc="Kiểm tra giá trị hiện tại của ô nhập / ô chọn bằng đúng giá trị")
def kw_assert_value(page, selector, value, ctx):
    loc = _locate(page, selector)
    try:
        expect(loc).to_have_value(value, timeout=ctx.timeout_ms)
    except AssertionError:
        try:
            actual = loc.input_value(timeout=1000)
        except Exception:
            actual = "<không tìm thấy phần tử>"
        raise AssertionError(f"Mong đợi ô '{selector}' có giá trị \"{value}\" nhưng thực tế là \"{actual}\"") from None


@keyword("assert_invalid", selector="bắt buộc",
         doc="Kiểm tra ô nhập bị trình duyệt đánh dấu không hợp lệ (HTML5 validation chặn gửi form)")
def kw_assert_invalid(page, selector, value, ctx):
    loc = _locate(page, selector)
    message = loc.evaluate("el => el.checkValidity() ? null : el.validationMessage")
    if message is None:
        raise AssertionError(f"Mong đợi ô '{selector}' không hợp lệ nhưng trình duyệt coi là hợp lệ")


@keyword("assert_no_js_error", doc="Kiểm tra trang không phát sinh lỗi JavaScript (kể từ khi bắt đầu test case)")
def kw_assert_no_js_error(page, selector, value, ctx):
    page.wait_for_timeout(300)  # Chờ các lỗi phát sinh muộn (VD: trong setTimeout) kịp được ghi nhận
    if ctx.js_errors:
        more = f" (và {len(ctx.js_errors) - 1} lỗi khác)" if len(ctx.js_errors) > 1 else ""
        raise AssertionError(f"Mong đợi không có lỗi JavaScript nhưng trang có lỗi: \"{ctx.js_errors[0]}\"{more}")


@keyword("assert_visible", selector="bắt buộc", doc="Kiểm tra phần tử đang hiển thị")
def kw_assert_visible(page, selector, value, ctx):
    try:
        expect(_locate(page, selector)).to_be_visible(timeout=ctx.timeout_ms)
    except AssertionError:
        raise AssertionError(f"Mong đợi phần tử '{selector}' hiển thị nhưng không thấy") from None


@keyword("assert_not_visible", selector="bắt buộc", doc="Kiểm tra phần tử KHÔNG hiển thị (hoặc không tồn tại)")
def kw_assert_not_visible(page, selector, value, ctx):
    try:
        expect(_locate(page, selector)).to_be_hidden(timeout=ctx.timeout_ms)
    except AssertionError:
        raise AssertionError(f"Mong đợi phần tử '{selector}' bị ẩn nhưng nó vẫn hiển thị") from None


@keyword("assert_url", value="URL hoặc một phần URL", doc="Kiểm tra URL hiện tại có chứa giá trị")
def kw_assert_url(page, selector, value, ctx):
    try:
        expect(page).to_have_url(re.compile(re.escape(value)), timeout=ctx.timeout_ms)
    except AssertionError:
        raise AssertionError(f"Mong đợi URL chứa \"{value}\" nhưng thực tế là \"{page.url}\"") from None


@keyword("assert_title", value="tiêu đề hoặc một phần", doc="Kiểm tra tiêu đề trang có chứa giá trị")
def kw_assert_title(page, selector, value, ctx):
    try:
        expect(page).to_have_title(re.compile(re.escape(value)), timeout=ctx.timeout_ms)
    except AssertionError:
        raise AssertionError(f"Mong đợi tiêu đề chứa \"{value}\" nhưng thực tế là \"{page.title()}\"") from None
