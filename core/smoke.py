"""
Kiểm tra nhanh một trang web chỉ bằng URL (smoke test), không cần viết kịch bản.

Các bước kiểm tra:
  1. Trang có tải được không, mã HTTP, thời gian tải.
  2. Lỗi JavaScript trong console và lỗi chưa được bắt (uncaught exception).
  3. Các link <a href> trên trang có bị lỗi 4xx, 5xx, timeout không.
  4. Ảnh nào không tải được, ảnh nào thiếu thuộc tính alt.
  5. Chụp ảnh trang ở 3 kích thước: điện thoại, tablet, máy tính.
"""

from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urldefrag, urlparse

from playwright.sync_api import sync_playwright

from core.runner import launch_browser

# Ba kích thước màn hình dùng để chụp ảnh
VIEWPORTS = {
    "Điện thoại (375px)": {"width": 375, "height": 667},
    "Tablet (768px)": {"width": 768, "height": 1024},
    "Máy tính (1366px)": {"width": 1366, "height": 768},
}

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


@dataclass
class LinkResult:
    url: str
    status: int | None = None    # Mã HTTP, None nếu không kết nối được
    error: str = ""              # Mô tả lỗi (timeout, lỗi DNS, ...)
    duration: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status is not None and self.status < 400


@dataclass
class ImageResult:
    src: str
    alt: str | None              # None = thiếu hẳn thuộc tính alt
    broken: bool = False
    reason: str = ""


@dataclass
class SmokeResult:
    url: str
    browser: str
    start_time: datetime
    final_url: str = ""
    page_ok: bool = False
    status: int | None = None
    load_time: float = 0.0       # giây, thời gian đến khi sự kiện load xong
    dom_ready_time: float = 0.0  # giây, thời gian đến khi HTML phân tích xong
    title: str = ""
    error: str = ""              # Lỗi khi tải trang (nếu có)
    console_errors: list[str] = field(default_factory=list)
    links: list[LinkResult] = field(default_factory=list)
    links_total_found: int = 0   # Số link tìm thấy (có thể nhiều hơn số link đã kiểm tra)
    images: list[ImageResult] = field(default_factory=list)
    screenshots: dict[str, str] = field(default_factory=dict)  # tên kích thước -> đường dẫn ảnh
    duration: float = 0.0

    @property
    def broken_links(self) -> list[LinkResult]:
        return [l for l in self.links if not l.ok]

    @property
    def broken_images(self) -> list[ImageResult]:
        return [i for i in self.images if i.broken]

    @property
    def images_missing_alt(self) -> list[ImageResult]:
        return [i for i in self.images if i.alt is None]

    @property
    def checks(self) -> list[dict]:
        """Bảng tổng hợp các hạng mục kiểm tra và trạng thái đạt/lỗi/cảnh báo."""
        return [
            {"name": "Tải trang", "status": "PASS" if self.page_ok else "FAIL",
             "detail": f"HTTP {self.status} · {self.load_time:.2f}s" if self.page_ok else self.error},
            {"name": "Thời gian tải", "status": "PASS" if self.load_time <= 3 else "WARN",
             "detail": f"{self.load_time:.2f}s (khuyến nghị ≤ 3s)"},
            {"name": "Link hỏng", "status": "FAIL" if self.broken_links else "PASS",
             "detail": f"{len(self.broken_links)}/{len(self.links)} link lỗi"},
            {"name": "Ảnh không tải được", "status": "FAIL" if self.broken_images else "PASS",
             "detail": f"{len(self.broken_images)}/{len(self.images)} ảnh lỗi"},
            {"name": "Ảnh thiếu alt", "status": "WARN" if self.images_missing_alt else "PASS",
             "detail": f"{len(self.images_missing_alt)}/{len(self.images)} ảnh thiếu alt"},
            {"name": "Lỗi JavaScript", "status": "FAIL" if self.console_errors else "PASS",
             "detail": f"{len(self.console_errors)} lỗi trong console"},
        ]

    @property
    def overall(self) -> str:
        statuses = [c["status"] for c in self.checks]
        return "FAIL" if "FAIL" in statuses else ("WARN" if "WARN" in statuses else "PASS")


# ---------------------------------------------------------------------------
# Kiểm tra link bằng HTTP (chạy song song nhiều luồng cho nhanh)
# ---------------------------------------------------------------------------

HTTP_STATUS_TEXT = {
    400: "Yêu cầu không hợp lệ", 401: "Cần đăng nhập/xác thực", 403: "Bị từ chối truy cập",
    404: "Không tìm thấy trang", 405: "Phương thức không được hỗ trợ", 408: "Server hết thời gian chờ",
    410: "Trang đã bị xóa", 429: "Gửi quá nhiều yêu cầu", 500: "Lỗi máy chủ nội bộ",
    502: "Bad Gateway", 503: "Dịch vụ tạm thời không khả dụng", 504: "Gateway hết thời gian chờ",
}


def describe_http_status(code: int) -> str:
    """Diễn giải mã HTTP lỗi bằng tiếng Việt."""
    if code in HTTP_STATUS_TEXT:
        return HTTP_STATUS_TEXT[code]
    return "Lỗi phía máy khách (4xx)" if code < 500 else "Lỗi phía máy chủ (5xx)"


def check_link(url: str, timeout: float = 10) -> LinkResult:
    """Gửi request HEAD (nhẹ, không tải nội dung); nếu server không hỗ trợ HEAD thì thử GET."""
    result = LinkResult(url=url)
    start = time.perf_counter()
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout,
                                        context=ssl.create_default_context()) as resp:
                result.status, result.error = resp.status, ""
        except urllib.error.HTTPError as e:
            result.status, result.error = e.code, describe_http_status(e.code)
        except TimeoutError:
            result.status, result.error = None, f"Hết thời gian chờ ({timeout:g}s)"
        except urllib.error.URLError as e:
            reason = e.reason
            result.status = None
            result.error = f"Hết thời gian chờ ({timeout:g}s)" if isinstance(reason, TimeoutError) \
                else f"Không kết nối được: {reason}"
        except Exception as e:
            result.status, result.error = None, f"Lỗi: {e}"
        # HEAD bị từ chối (405, 403, 404...) thì thử lại bằng GET; còn lại dừng
        if result.ok or method == "GET" or result.status is None:
            break
    result.duration = round(time.perf_counter() - start, 3)
    return result


def check_links(urls: list[str], workers: int = 10, timeout: float = 10) -> list[LinkResult]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda u: check_link(u, timeout), urls))


# ---------------------------------------------------------------------------
# Thu thập thông tin trên trang bằng JavaScript
# ---------------------------------------------------------------------------

JS_COLLECT_LINKS = "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"

JS_COLLECT_IMAGES = """() => Array.from(document.images).map(img => ({
    src: img.currentSrc || img.src,
    alt: img.getAttribute('alt'),
    complete: img.complete,
    naturalWidth: img.naturalWidth
}))"""

# Cuộn từ từ xuống cuối trang để kích hoạt các ảnh tải chậm (lazy loading)
JS_SCROLL_TO_BOTTOM = """async () => {
    for (let y = 0; y < document.body.scrollHeight && y < 30000; y += 600) {
        window.scrollTo(0, y);
        await new Promise(r => setTimeout(r, 80));
    }
    window.scrollTo(0, 0);
}"""


def _filter_links(hrefs: list[str], page_url: str = "") -> list[str]:
    """Chỉ giữ link http/https, bỏ phần #neo, bỏ link trỏ về chính trang đang kiểm tra
    và loại trùng lặp (giữ thứ tự)."""
    seen, result = {urldefrag(page_url)[0]}, []
    for href in hrefs:
        url = urldefrag(href)[0]
        if urlparse(url).scheme in ("http", "https") and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def _analyze_images(raw_images: list[dict]) -> list[ImageResult]:
    """Xác định ảnh hỏng: trình duyệt đã tải xong mà chiều rộng thực = 0."""
    images = []
    for img in raw_images:
        src = img["src"] or ""
        result = ImageResult(src=src or "(không có src)", alt=img["alt"])
        if not src:
            result.broken, result.reason = True, "Thiếu thuộc tính src"
        elif img["naturalWidth"] == 0:
            if img["complete"]:
                result.broken, result.reason = True, "Trình duyệt không hiển thị được ảnh"
                if src.startswith("http"):
                    # Hỏi lại máy chủ để phân biệt: ảnh hỏng thật hay trình duyệt không hỗ trợ định dạng ảnh
                    # (VD: bản WebKit trên Windows không hiển thị được ảnh .avif)
                    link = check_link(src)
                    if link.ok:
                        ext = Path(urlparse(src).path).suffix.lower() or "này"
                        result.reason = (f"Máy chủ trả ảnh bình thường (HTTP {link.status}) nhưng trình duyệt này "
                                         f"không hiển thị được — có thể không hỗ trợ định dạng {ext}")
                    elif link.status:
                        result.reason = f"HTTP {link.status} - {link.error}"
            elif src.startswith("http"):
                # Ảnh chưa tải xong (lazy) -> kiểm tra trực tiếp bằng HTTP
                link = check_link(src)
                if not link.ok:
                    result.broken = True
                    result.reason = f"HTTP {link.status}" if link.status else link.error
        images.append(result)
    return images


# ---------------------------------------------------------------------------
# Hàm chính
# ---------------------------------------------------------------------------

def smoke_check(
    url: str,
    output_dir: str | Path,
    browser_name: str = "chromium",
    headless: bool = True,
    max_links: int = 100,
    on_progress: Callable[[str], None] | None = None,
) -> SmokeResult:
    """Kiểm tra nhanh một URL. on_progress(thông_điệp) dùng để báo tiến trình lên giao diện."""
    if not urlparse(url).scheme:
        url = "https://" + url  # Người dùng gõ "example.com" thì tự thêm https://
    notify = on_progress or (lambda msg: None)
    output_dir = Path(output_dir)
    shot_dir = output_dir / "screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)

    result = SmokeResult(url=url, browser=browser_name, start_time=datetime.now())
    started = time.perf_counter()

    with sync_playwright() as p:
        browser = launch_browser(p, browser_name, headless=headless)
        try:
            # ----- 1 & 2. Tải trang, đo thời gian, bắt lỗi console -----
            notify("Đang tải trang...")
            context = browser.new_context(viewport=VIEWPORTS["Máy tính (1366px)"], user_agent=USER_AGENT)
            page = context.new_page()
            page.on("console", lambda msg: result.console_errors.append(msg.text)
                    if msg.type == "error" else None)
            page.on("pageerror", lambda exc: result.console_errors.append(f"Uncaught: {exc}"))

            t0 = time.perf_counter()
            try:
                response = page.goto(url, wait_until="load", timeout=30_000)
                result.load_time = round(time.perf_counter() - t0, 3)
                result.status = response.status if response else None
                result.page_ok = response is not None and response.status < 400
                if not result.page_ok:
                    result.error = f"Trang trả về mã lỗi HTTP {result.status}"
            except Exception as exc:
                result.load_time = round(time.perf_counter() - t0, 3)
                result.error = f"Không tải được trang: {str(exc).splitlines()[0]}"

            if result.status is not None:
                result.final_url = page.url
                result.title = page.title()
                # Thời gian DOM sẵn sàng lấy từ Navigation Timing API của trình duyệt
                result.dom_ready_time = round(page.evaluate(
                    "() => { const n = performance.getEntriesByType('navigation')[0];"
                    " return n ? n.domContentLoadedEventEnd / 1000 : 0; }"), 3)

                # ----- 3. Ảnh -----
                notify("Đang kiểm tra ảnh...")
                page.evaluate(JS_SCROLL_TO_BOTTOM)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass  # Trang có kết nối liên tục (quảng cáo, chat...) thì bỏ qua
                result.images = _analyze_images(page.evaluate(JS_COLLECT_IMAGES))

                # ----- 4. Link -----
                links = _filter_links(page.evaluate(JS_COLLECT_LINKS), page.url)
                result.links_total_found = len(links)
                notify(f"Đang kiểm tra {min(len(links), max_links)} link...")
                result.links = check_links(links[:max_links])
            context.close()

            # ----- 5. Chụp ảnh ở 3 kích thước -----
            if result.status is not None:
                for name, viewport in VIEWPORTS.items():
                    notify(f"Đang chụp ảnh {name}...")
                    result.screenshots[name] = _take_screenshot(browser, url, viewport, shot_dir)
        finally:
            browser.close()

    result.duration = round(time.perf_counter() - started, 3)
    notify("Hoàn tất")
    return result


def _take_screenshot(browser, url: str, viewport: dict, shot_dir: Path) -> str | None:
    """Mở trang với kích thước màn hình cho trước và chụp toàn trang (định dạng JPEG cho nhẹ)."""
    is_mobile = viewport["width"] < 768
    context = browser.new_context(viewport=viewport, user_agent=None if not is_mobile else
                                  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
    page = context.new_page()
    path = shot_dir / f"trang_{viewport['width']}px.jpg"
    try:
        page.goto(url, wait_until="load", timeout=30_000)
        page.wait_for_timeout(800)  # Chờ hiệu ứng / font hiển thị ổn định
        page.screenshot(path=str(path), full_page=True, type="jpeg", quality=70, timeout=15_000)
        return str(path)
    except Exception:
        return None
    finally:
        context.close()
