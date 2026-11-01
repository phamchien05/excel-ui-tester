"""
Tự sinh kịch bản kiểm thử từ một URL (không cần viết Excel bằng tay).

Quy trình 3 bước:
  1. QUÉT TRANG (scan_page): mở trang, tìm các thành phần có thể kiểm thử:
       - Form (các ô nhập + nút gửi)    - Link điều hướng    - Dropdown đứng riêng
  2. NGƯỜI DÙNG CHỌN phần muốn kiểm thử, kỹ thuật thiết kế test và sửa dữ liệu hợp lệ.
  3. SINH TEST CASE (generate_cases) theo các kỹ thuật thiết kế test hộp đen:
       - Phân vùng tương đương : dữ liệu hợp lệ / không hợp lệ
       - Bỏ trống trường       : lần lượt để trống từng ô
       - Sai định dạng         : email thiếu @, số điện thoại có chữ, URL sai...
       - Giá trị biên          : độ dài / giá trị tại min-1, min, max, max+1
       - Ký tự đặc biệt        : chuỗi XSS, SQL injection
     Với form, công cụ CHẠY THỬ từng test case để GHI NHẬN KẾT QUẢ THỰC TẾ
     (chuyển trang? hiện thông báo gì? trình duyệt chặn gửi?) rồi dùng làm kết quả mong đợi.
     Các dòng tự ghi nhận được tô màu trong Excel để người kiểm thử xem lại.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from core.dom import QA_HELPERS_JS, mark_fragile
from core.keywords import KEYWORDS, KeywordContext
from core.reader import TestCase, TestStep, read_suite
from core.runner import launch_browser

# Các kỹ thuật thiết kế test được hỗ trợ: mã -> tên hiển thị
TECHNIQUES = {
    "hop_le": "Dữ liệu hợp lệ",
    "bo_trong": "Bỏ trống trường",
    "dinh_dang": "Sai định dạng",
    "gia_tri_bien": "Giá trị biên",
    "ky_tu_dac_biet": "Ký tự đặc biệt (XSS, SQL injection)",
}

TEXT_INPUT_TYPES = {"text", "email", "password", "search", "tel", "url", "number"}
NEED_REVIEW_TEXT = "<ĐIỀN KẾT QUẢ MONG ĐỢI>"


# ---------------------------------------------------------------------------
# Cấu trúc dữ liệu kết quả quét trang
# ---------------------------------------------------------------------------

@dataclass
class FormField:
    selector: str
    label: str
    tag: str                    # input / textarea / select
    type: str                   # text, email, password, number, checkbox, select...
    required: bool = False
    maxlength: int | None = None
    minlength: int | None = None
    min: str = ""
    max: str = ""
    options: list[dict] = field(default_factory=list)  # Các lựa chọn nếu là <select>
    valid_value: str = ""       # Giá trị hợp lệ (người dùng sửa được trên giao diện)
    name: str = ""              # Thuộc tính name (dùng gộp nhóm radio)

    @property
    def is_choice(self) -> bool:
        """Ô tích chọn (checkbox / radio)."""
        return self.type in ("checkbox", "radio")

    @property
    def is_text(self) -> bool:
        """Ô nhập chữ tự do (áp dụng được bỏ trống, giá trị biên, ký tự đặc biệt)."""
        return self.tag == "textarea" or (self.tag == "input" and self.type in TEXT_INPUT_TYPES)

    @property
    def key(self) -> str:
        """Chuỗi dùng để đoán ý nghĩa của ô: type + nhãn + giá trị trong selector.
        Bỏ phần cú pháp như [name=, [data-test= để chữ "name" trong cú pháp không gây nhầm lẫn."""
        selector = re.sub(r"\[[\w-]+=", " ", self.selector)
        return f"{self.type} {self.label} {selector}".lower()

    @property
    def kind(self) -> str:
        """Loại dữ liệu theo ngữ nghĩa, dựa vào type và tên ô. Chỉ xét ô nhập chữ (radio có nhãn
        'Liên hệ qua email' không phải ô email)."""
        if not self.is_text:
            return "other"
        key = self.key
        if self.type == "email" or "email" in key or "e-mail" in key:
            return "email"
        if self.type == "tel" or any(k in key for k in ("phone", "điện thoại", "sđt", "mobile")):
            return "tel"
        if self.type == "url":
            return "url"
        if self.type == "number":
            return "number"
        return "text"


@dataclass
class FormInfo:
    title: str
    selector: str
    submit: str                 # Selector nút gửi, rỗng nếu không có (khi đó nhấn Enter)
    submit_label: str
    fields: list[FormField]


@dataclass
class LinkInfo:
    selector: str
    text: str
    href: str
    new_tab: bool = False


@dataclass
class SelectInfo:
    selector: str
    label: str
    options: list[dict]


@dataclass
class ControlInfo:
    """Nút bấm / checkbox / radio đứng riêng (ngoài form)."""
    selector: str
    label: str
    kind: str                   # button / checkbox / radio

    @property
    def kind_text(self) -> str:
        return {"button": "Nút", "checkbox": "Checkbox", "radio": "Radio", "link": "Link"}.get(self.kind, self.kind)


@dataclass
class PageScan:
    url: str                    # URL dùng cho bước "open" của các test case sinh ra
    title: str
    headings: list[dict]        # [{selector, text}]
    forms: list[FormInfo]
    links: list[LinkInfo]
    selects: list[SelectInfo]
    controls: list[ControlInfo] = field(default_factory=list)  # Nút bấm, checkbox, radio ngoài form
    final_url: str = ""         # URL thực tế sau khi mở (khác url nếu trang tự chuyển hướng, VD: về trang đăng nhập)
    setup: list[TestStep] = field(default_factory=list)  # Bước chuẩn bị (VD: đăng nhập), chèn vào đầu mọi test case

    @property
    def redirected(self) -> bool:
        """Trang bị chuyển hướng sang đường dẫn khác (thường do chưa đăng nhập)."""
        return bool(self.final_url) and \
            urlparse(self.final_url).path.rstrip("/") != urlparse(self.url).path.rstrip("/")


# ---------------------------------------------------------------------------
# 1. QUÉT TRANG
# ---------------------------------------------------------------------------

JS_SCAN = r"""
() => {
  const qa = window.__qa;
  const SKIP = ['hidden', 'submit', 'button', 'image', 'reset', 'file'];
  const isField = el => !(el.tagName === 'INPUT' && SKIP.includes((el.type || '').toLowerCase()))
                        && qa.visible(el) && !el.disabled && !el.readOnly;
  const fieldInfo = el => ({
    selector: qa.selector(el), label: qa.label(el), tag: el.tagName.toLowerCase(), name: el.getAttribute('name') || '',
    type: el.tagName === 'INPUT' ? (el.type || 'text').toLowerCase() : el.tagName.toLowerCase(),
    required: el.required || el.getAttribute('aria-required') === 'true',
    maxlength: el.maxLength > 0 ? el.maxLength : null,
    minlength: el.minLength > 0 ? el.minLength : null,
    min: el.getAttribute('min') || '', max: el.getAttribute('max') || '',
    options: el.tagName === 'SELECT'
      ? Array.from(el.options).map(o => ({ value: o.value, label: o.text.trim() })) : []
  });
  // Tìm nút gửi: ưu tiên nút submit thật, bỏ qua nút Hủy / Quay lại / Đóng (VD: form thanh toán có Cancel đứng trước Continue)
  const NOT_SUBMIT = /^(cancel|hủy|huỷ|back|quay lại|trở lại|close|đóng|reset|làm lại|xóa|clear)\b/i;
  const usable = el => qa.visible(el) && !NOT_SUBMIT.test((qa.label(el) || '').trim());
  const findSubmit = c => {
    for (const sel of ['button[type=submit], input[type=submit], input[type=image]', 'button:not([type])',
                       'button, input[type=button], [role=button]']) {
      const found = Array.from(c.querySelectorAll(sel)).find(usable);
      if (found) return found;
    }
    return null;
  };
  const clean = t => (t || '').replace(/\s+/g, ' ').trim().slice(0, 40);
  const titleOf = (c, submit) => clean(c.getAttribute && (c.getAttribute('aria-label') || c.getAttribute('name')))
      || clean((c.querySelector('legend, h1, h2, h3, h4') || {}).innerText)
      || (submit ? clean(qa.label(submit)) : '') || clean(c.id);

  // Nhóm 1: thẻ <form> thật
  const groups = [];
  document.querySelectorAll('form').forEach(f => {
    const fields = Array.from(f.querySelectorAll('input, textarea, select')).filter(isField);
    if (fields.length) groups.push({ container: f, fields });
  });
  // Nhóm 2: ô nhập nằm ngoài <form> -> gom theo khối cha gần nhất có chứa nút bấm
  const orphanGroups = new Map();
  Array.from(document.querySelectorAll('input, textarea, select'))
    .filter(el => isField(el) && !el.closest('form'))
    .forEach(el => {
      let c = el.parentElement, depth = 0;
      while (c && c !== document.body && depth < 6 && !c.querySelector('button, input[type=submit], [role=button]')) {
        c = c.parentElement; depth++;
      }
      if (!c || depth >= 6) c = document.body;
      if (!orphanGroups.has(c)) orphanGroups.set(c, []);
      orphanGroups.get(c).push(el);
    });

  const selects = [], controls = [];
  const isTextLike = f => f.tagName === 'TEXTAREA'
      || (f.tagName === 'INPUT' && !['checkbox', 'radio', 'range', 'color'].includes((f.type || '').toLowerCase()));
  orphanGroups.forEach((fields, c) => {
    // Nhóm có ô nhập chữ -> là form (VD: ô tìm kiếm + nút Tìm). Ngược lại các ô đứng riêng được tách ra:
    // dropdown (VD: sắp xếp sản phẩm) và checkbox/radio (VD: bộ lọc) -> kiểm thử riêng, không phải form
    if (fields.some(isTextLike)) {
      groups.push({ container: c, fields });
      return;
    }
    fields.forEach(f => {
      if (f.tagName === 'SELECT') selects.push({ selector: qa.selector(f), label: qa.label(f), options: fieldInfo(f).options });
      else controls.push({ selector: qa.selector(f), label: qa.label(f), kind: f.type.toLowerCase() });
    });
  });

  const forms = groups.map(g => {
    const submit = findSubmit(g.container);
    return {
      title: titleOf(g.container, submit),
      selector: g.container === document.body ? 'body' : qa.selector(g.container),
      submit: submit ? qa.target(submit) : '',
      submit_label: submit ? qa.label(submit) : '',
      fields: g.fields.slice(0, 12).map(fieldInfo)
    };
  });

  // Link: chỉ lấy link http(s) đang hiển thị, bỏ link neo (#) và trùng lặp
  const seen = new Set(), links = [];
  document.querySelectorAll('a[href]').forEach(a => {
    if (!qa.visible(a) || !/^https?:/.test(a.href)) return;
    const href = a.href.split('#')[0];
    if (href === location.href.split('#')[0] || seen.has(href)) return;
    seen.add(href);
    links.push({ selector: qa.target(a), text: qa.label(a), href, new_tab: a.target === '_blank' });
  });

  const headings = Array.from(document.querySelectorAll('h1, h2')).filter(qa.visible).slice(0, 5)
    .map(h => ({ selector: qa.selector(h), text: clean(h.innerText) })).filter(h => h.text);

  // Nút bấm nằm ngoài các form đã tìm thấy (VD: Thêm vào giỏ, Xem chi tiết).
  // Bỏ qua nút nguy hiểm (đăng xuất, xóa tài khoản) và nút trùng tên (6 nút "Add to cart" chỉ lấy 1).
  const DANGEROUS = /log\s*-?out|sign\s*-?out|đăng xuất|thoát|xóa tài khoản|xoá tài khoản|delete account|hủy tài khoản|huỷ tài khoản/i;
  const formContainers = groups.map(g => g.container).filter(c => c !== document.body);
  const seenLabels = new Set(controls.map(c => c.label));
  const buttons = Array.from(document.querySelectorAll(
      'button, [role=button], input[type=button], input[type=submit], a[href="#"], a:not([href])[onclick]'));
  for (const b of buttons) {
    if (controls.length >= 20) break;
    if (!qa.visible(b) || b.disabled || b.closest('form') || formContainers.some(c => c.contains(b))) continue;
    const label = clean(qa.label(b));
    if (!label || DANGEROUS.test(label) || seenLabels.has(label)) continue;
    seenLabels.add(label);
    controls.push({ selector: qa.target(b), label, kind: 'button' });
  }

  return { title: document.title, headings, forms, links: links.slice(0, 80), selects, controls };
}
"""


def _new_page(browser):
    """Tạo context + trang mới đã nạp sẵn bộ hàm window.__qa."""
    context = browser.new_context(viewport={"width": 1366, "height": 768})
    context.add_init_script(QA_HELPERS_JS)
    page = context.new_page()
    page.set_default_timeout(10_000)
    return context, page


def _goto(page, url: str):
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    try:
        page.wait_for_load_state("networkidle", timeout=5_000)  # Chờ trang dựng xong (SPA)
    except Exception:
        pass


def _normalize_url(url: str) -> str:
    url = url.strip()
    return url if not url or urlparse(url).scheme else "https://" + url


# ---------------------------------------------------------------------------
# BƯỚC CHUẨN BỊ (VD: ĐĂNG NHẬP) TRƯỚC KHI QUÉT
# Các bước này được chạy trước khi quét trang, và được chèn vào đầu MỌI test case sinh ra
# (mỗi test case chạy trên một phiên trình duyệt mới nên phải đăng nhập lại).
# ---------------------------------------------------------------------------

SETUP_PREFIX = "[Chuẩn bị] "


class SetupError(RuntimeError):
    """Bước chuẩn bị (đăng nhập...) không chạy được."""


def _short_error(exc: Exception) -> str:
    return str(exc).split("Call log:")[0].strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__


def _as_setup(steps: list[TestStep]) -> list[TestStep]:
    """Sao chép các bước và gắn tiền tố [Chuẩn bị] vào mô tả để phân biệt trong Excel."""
    result = []
    for s in steps:
        desc = s.description if s.description.startswith(SETUP_PREFIX) else SETUP_PREFIX + (s.description or s.keyword)
        result.append(TestStep(0, s.keyword, s.selector, s.value, desc))
    return result


def _run_steps(page, steps: list[TestStep], timeout_ms: int):
    """Chạy các bước chuẩn bị; lỗi thì báo rõ bước nào."""
    ctx = KeywordContext(screenshot_dir=Path("."), case_slug="chuan_bi", timeout_ms=timeout_ms)
    for i, step in enumerate(steps, start=1):
        try:
            KEYWORDS[step.keyword](page, step.selector, step.value, ctx)
        except Exception as exc:
            raise SetupError(f"Bước chuẩn bị {i} ({step.keyword} {step.selector}) bị lỗi: {_short_error(exc)}") from None
    try:
        page.wait_for_load_state("networkidle", timeout=3_000)
    except Exception:
        pass


# Tìm form đăng nhập: ô mật khẩu đang hiển thị, ô tên đăng nhập đứng ngay trước nó, nút gửi cùng form
JS_FIND_LOGIN = r"""
() => {
  const qa = window.__qa;
  const pwd = Array.from(document.querySelectorAll('input[type=password]')).find(qa.visible);
  if (!pwd) return null;
  const TEXT_TYPES = ['text', 'email', 'tel', ''];
  const before = Array.from(document.querySelectorAll('input')).filter(e => qa.visible(e)
      && TEXT_TYPES.includes((e.getAttribute('type') || '').toLowerCase())
      && (e.compareDocumentPosition(pwd) & Node.DOCUMENT_POSITION_FOLLOWING));
  const user = before[before.length - 1] || null;
  const scope = pwd.closest('form') || pwd.parentElement;
  let submit = Array.from((pwd.closest('form') || document).querySelectorAll(
      'button[type=submit], input[type=submit], button:not([type])')).find(qa.visible) || null;
  if (!submit && scope) submit = Array.from(scope.querySelectorAll('button, [role=button]')).find(qa.visible) || null;
  return {
    user: user ? qa.selector(user) : '', user_label: user ? qa.label(user) : '',
    password: qa.selector(pwd), submit: submit ? qa.target(submit) : '', submit_label: submit ? qa.label(submit) : ''
  };
}
"""


def build_login_steps(login_url: str, username: str, password: str, browser_name: str = "chromium",
                      timeout_ms: int = 10_000) -> list[TestStep]:
    """
    Tự tìm form đăng nhập trên trang login_url và tạo các bước đăng nhập.
    Thử đăng nhập luôn: nếu sau khi gửi vẫn ở trang đăng nhập (ô mật khẩu còn hiển thị) thì báo lỗi.
    """
    login_url = _normalize_url(login_url)
    with sync_playwright() as p:
        browser = launch_browser(p, browser_name, headless=True)
        try:
            context, page = _new_page(browser)
            page.set_default_timeout(timeout_ms)
            _goto(page, login_url)
            info = page.evaluate(JS_FIND_LOGIN)
            if not info:
                raise SetupError("Không tìm thấy ô mật khẩu trên trang đăng nhập. Kiểm tra lại URL trang đăng nhập.")
            steps = [TestStep(0, "open", "", login_url, "Mở trang đăng nhập")]
            if info["user"]:
                steps.append(TestStep(0, "type", info["user"], username, f"Nhập {info['user_label'] or 'tên đăng nhập'}"))
            steps.append(TestStep(0, "type", info["password"], password, "Nhập mật khẩu"))
            steps.append(TestStep(0, "click", info["submit"], "", f"Bấm nút {info['submit_label']}") if info["submit"]
                         else TestStep(0, "press_key", info["password"], "Enter", "Nhấn Enter để đăng nhập"))

            # Thử đăng nhập để chắc chắn tài khoản đúng
            _run_steps(page, steps, timeout_ms)
            page.wait_for_timeout(800)
            same_page = urlparse(page.url).path.rstrip("/") == urlparse(login_url).path.rstrip("/")
            still_on_login = same_page and page.locator(info["password"]).first.is_visible()
            if still_on_login:
                messages = _safe_messages(page)
                detail = f': "{messages[0]["text"]}"' if messages else ". Kiểm tra lại tên đăng nhập / mật khẩu."
                raise SetupError("Đăng nhập không thành công" + detail)
        finally:
            browser.close()
    return _as_setup(steps)


def setup_from_suite(excel_path: str | Path, case_name: str) -> list[TestStep]:
    """Lấy các bước của một test case trong file Excel (VD: kịch bản đã ghi lại) làm bước chuẩn bị."""
    suite = read_suite(excel_path)
    case = next((c for c in suite.cases if c.name == case_name), None)
    if case is None:
        raise SetupError(f"Không tìm thấy test case '{case_name}' trong file {Path(excel_path).name}")
    return _as_setup(case.steps)


def scan_page(url: str, browser_name: str = "chromium", setup: list[TestStep] | None = None,
              timeout_ms: int = 10_000) -> PageScan:
    """
    Mở trang và tìm các thành phần có thể kiểm thử.
    setup: các bước chuẩn bị (VD: đăng nhập) chạy trước khi mở url. url rỗng = quét trang đang mở sau bước chuẩn bị.
    """
    url = _normalize_url(url)
    setup = setup or []
    with sync_playwright() as p:
        browser = launch_browser(p, browser_name, headless=True)
        try:
            context, page = _new_page(browser)
            page.set_default_timeout(timeout_ms)
            if setup:
                _run_steps(page, setup, timeout_ms)
            if url:
                _goto(page, url)
            raw = page.evaluate(JS_SCAN)
            final_url = page.url
        finally:
            browser.close()
    return _to_page_scan(raw, url or final_url, final_url, setup)


# ---------------------------------------------------------------------------
# QUÉT NHIỀU TRANG (đi theo link cùng website)
# ---------------------------------------------------------------------------

# Link không được đi vào khi quét: đăng xuất (mất phiên đăng nhập), xóa (thay đổi dữ liệu)
UNSAFE_LINK = re.compile(r"log\s*-?out|sign\s*-?out|logoff|đăng xuất|thoát|delete|remove|xóa|xoá", re.I)
# Link tải file, không phải trang web
FILE_EXTENSIONS = (".pdf", ".zip", ".rar", ".7z", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
                   ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".avif", ".mp3", ".mp4", ".avi", ".exe",
                   ".msi", ".dmg", ".apk", ".css", ".js", ".json", ".xml", ".txt")


def _page_key(url: str) -> str:
    """Khóa so sánh trùng trang: bỏ #neo và dấu / cuối."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}" + (f"?{parsed.query}" if parsed.query else "")


ID_SEGMENT = re.compile(r"^(\d+|[0-9a-f-]{16,}|[0-9A-Za-z]{20,})$")


def page_template(url: str) -> str:
    """
    Khuôn mẫu trang: thay các đoạn đường dẫn giống mã ID (số, chuỗi dài) bằng ':id' và bỏ giá trị query.
    VD: /product/01M64D4165EW1MFKCSP4R7CQTK và /product/01M64D416KM2... -> cùng khuôn /product/:id
    -> chỉ cần quét một trang đại diện thay vì hàng chục trang sản phẩm giống hệt nhau.
    """
    parsed = urlparse(url)
    segments = [":id" if ID_SEGMENT.match(s) else s for s in parsed.path.rstrip("/").split("/")]
    query_keys = sorted(k.split("=")[0] for k in parsed.query.split("&") if k)
    return f"{parsed.netloc}{'/'.join(segments)}?{'&'.join(query_keys)}"


def should_follow(link_href: str, link_text: str, site_netloc: str) -> bool:
    """Link có nên đi theo khi quét nhiều trang không: cùng website, là trang web, không nguy hiểm."""
    parsed = urlparse(link_href)
    if parsed.scheme not in ("http", "https") or parsed.netloc != site_netloc:
        return False
    if parsed.path.lower().endswith(FILE_EXTENSIONS):
        return False
    return not UNSAFE_LINK.search(f"{link_href} {link_text}")


def crawl_site(
    start_url: str,
    browser_name: str = "chromium",
    setup: list[TestStep] | None = None,
    max_pages: int = 8,
    extra_urls: list[str] = (),
    timeout_ms: int = 10_000,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[PageScan]:
    """
    Quét nhiều trang: bắt đầu từ start_url (và các extra_urls), đi theo link cùng website kiểu
    lan rộng theo từng lớp (BFS) cho đến khi đủ max_pages trang. Dùng chung một phiên trình duyệt
    nên chỉ cần đăng nhập (setup) một lần.
    """
    start_url = _normalize_url(start_url)
    setup = setup or []
    site = urlparse(start_url).netloc
    queue = [start_url] + [_normalize_url(u) for u in extra_urls if u.strip()]
    queued = {_page_key(u) for u in queue}
    templates = {page_template(u) for u in queue}  # Mỗi khuôn mẫu trang chỉ quét một trang đại diện
    visited_final: set[str] = set()
    scans: list[PageScan] = []

    with sync_playwright() as p:
        browser = launch_browser(p, browser_name, headless=True)
        try:
            context, page = _new_page(browser)
            page.set_default_timeout(timeout_ms)
            if setup:
                _run_steps(page, setup, timeout_ms)
            while queue and len(scans) < max_pages:
                url = queue.pop(0)
                if on_progress:
                    on_progress(len(scans), max_pages, url)
                try:
                    _goto(page, url)
                    raw = page.evaluate(JS_SCAN)
                except Exception:
                    continue  # Trang lỗi / không mở được -> bỏ qua, quét trang khác
                final_key = _page_key(page.url)
                if final_key in visited_final:
                    continue  # VD: nhiều trang cùng chuyển hướng về trang đăng nhập -> chỉ giữ một
                visited_final.add(final_key)
                scans.append(_to_page_scan(raw, url, page.url, setup))
                for link in raw["links"]:
                    key, template = _page_key(link["href"]), page_template(link["href"])
                    if key in queued or template in templates or not should_follow(link["href"], link["text"], site):
                        continue
                    queued.add(key)
                    templates.add(template)
                    queue.append(link["href"].split("#")[0])
        finally:
            browser.close()
    if on_progress:
        on_progress(len(scans), len(scans), "Hoàn tất")
    return scans


def form_signature(form: FormInfo) -> tuple:
    """Dấu hiệu nhận biết form trùng nhau giữa các trang (VD: ô tìm kiếm ở đầu mọi trang)."""
    return (form.selector, form.submit, tuple(f.selector for f in form.fields))


def _group_radios(fields: list[FormField]) -> list[FormField]:
    """Nhóm radio cùng name chỉ giữ lại nút đầu tiên làm đại diện (chọn nút này = đã chọn nhóm)."""
    seen, result = set(), []
    for f in fields:
        if f.type == "radio" and f.name:
            if f.name in seen:
                continue
            seen.add(f.name)
        result.append(f)
    return result


def _to_page_scan(raw: dict, url: str, final_url: str, setup: list[TestStep]) -> PageScan:
    """Chuyển kết quả JavaScript (dict) thành PageScan."""
    forms = []
    for f in raw["forms"]:
        fields = _group_radios([FormField(**fd) for fd in f.pop("fields")])
        for fd in fields:
            fd.valid_value = guess_valid_value(fd)
        forms.append(FormInfo(fields=fields, **f))
    for i, form in enumerate(forms, start=1):
        form.title = form.title or f"Form {i}"
    for link in raw["links"]:
        if link["text"] in ("", "a"):  # Link không có chữ (VD: chỉ chứa ảnh) -> dùng tên miền + đường dẫn
            parsed = urlparse(link["href"])
            link["text"] = (parsed.netloc + parsed.path).rstrip("/")[:40]
    return PageScan(url=url, title=raw["title"], headings=raw["headings"], forms=forms,
                    links=[LinkInfo(**l) for l in raw["links"]],
                    selects=[SelectInfo(**s) for s in raw["selects"]],
                    controls=[ControlInfo(**c) for c in raw["controls"]],
                    final_url=final_url, setup=list(setup))


def guess_valid_value(f: FormField) -> str:
    """Đoán một giá trị hợp lệ dựa vào loại ô và tên ô. Người dùng có thể sửa lại trên giao diện."""
    key = f.key
    if f.tag == "select":
        # Lựa chọn đầu tiên thường là dòng hướng dẫn ("-- Chọn --") nên ưu tiên lựa chọn thứ hai
        values = [o["value"] for o in f.options]
        return values[1] if len(values) > 1 else (values[0] if values else "")
    if f.type in ("checkbox", "radio"):
        return "check" if f.required else ""
    if f.type in ("number", "range"):
        lo = _to_number(f.min, 0 if f.type == "range" else 1)
        hi = _to_number(f.max, 100 if f.type == "range" else lo + 100)
        return _fmt_number((lo + hi) // 2 if hi >= lo else lo)
    # Các ô có định dạng cố định của trình duyệt
    fixed_formats = {"color": "#3366ff", "date": "2000-01-15", "datetime-local": "2000-01-15T10:30",
                     "month": "2000-01", "week": "2000-W03", "time": "10:30"}
    if f.type in fixed_formats:
        return fixed_formats[f.type]

    rules = [  # (điều kiện, giá trị) xét theo thứ tự
        (f.kind == "email", "test.user@example.com"),
        (f.type == "password" or "pass" in key or "mật khẩu" in key, "Abc@12345"),
        (f.kind == "tel", "0912345678"),
        (f.kind == "url", "https://example.com"),
        (any(k in key for k in ("zip", "postal", "mã bưu")), "100000"),
        (any(k in key for k in ("user", "login", "tài khoản", "account")), "testuser"),
        (any(k in key for k in ("first", "tên")), "An"),
        (any(k in key for k in ("last", "họ")), "Nguyen"),
        ("name" in key, "Nguyen Van An"),
        (any(k in key for k in ("address", "địa chỉ")), "1 Dai Co Viet, Ha Noi"),
        (f.type == "search" or "search" in key or "tìm" in key or '[name="q"]' in key, "kiem thu"),
        (f.tag == "textarea", "Noi dung kiem thu tu dong"),
    ]
    value = next((v for cond, v in rules if cond), "Kiem thu")
    if f.minlength and len(value) < f.minlength:
        value += "a" * (f.minlength - len(value))
    if f.maxlength and len(value) > f.maxlength:
        value = value[:f.maxlength]
    return value


def _to_number(text: str, default: int) -> int:
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default


def _fmt_number(n: int) -> str:
    return str(int(n))


# ---------------------------------------------------------------------------
# 2. SINH CÁC "BẢN NHÁP" TEST CASE CHO FORM THEO TỪNG KỸ THUẬT
# Mỗi bản nháp = tên + các giá trị ghi đè (selector -> giá trị) + các bước kiểm tra thêm.
# Các ô không bị ghi đè sẽ dùng giá trị hợp lệ.
# ---------------------------------------------------------------------------

@dataclass
class FormDraft:
    name: str
    overrides: dict[str, str] = field(default_factory=dict)
    pre_submit_checks: list[TestStep] = field(default_factory=list)  # Kiểm tra ngay trước khi gửi
    purpose: str = ""


XSS_VALUE = "<script>alert('xss')</script>"
SQLI_VALUE = "' OR '1'='1' --"


def _drafts_for_form(form: FormInfo, techniques: set[str]) -> list[FormDraft]:
    drafts: list[FormDraft] = []
    text_fields = [f for f in form.fields if f.is_text]

    if "hop_le" in techniques:
        drafts.append(FormDraft("Hợp lệ", purpose="Tất cả các trường nhập dữ liệu hợp lệ"))

    if "bo_trong" in techniques:
        # Nếu form có đánh dấu bắt buộc thì chỉ thử các ô bắt buộc, ngược lại thử mọi ô nhập chữ
        targets = [f for f in form.fields if f.required] or text_fields
        for f in targets:
            if f.is_choice:
                drafts.append(FormDraft(f"Không chọn {f.label}", {f.selector: ""},
                                        purpose=f"Không tích chọn '{f.label}', các ô khác hợp lệ"))
            else:
                drafts.append(FormDraft(f"Bỏ trống {f.label}", {f.selector: ""},
                                        purpose=f"Để trống ô '{f.label}', các ô khác hợp lệ"))
        if len(targets) > 1:
            drafts.append(FormDraft("Bỏ trống tất cả", {f.selector: "" for f in targets},
                                    purpose="Để trống tất cả các ô"))

    if "dinh_dang" in techniques:
        invalid_by_kind = {
            "email": [("abc", "email thiếu @"), ("abc@", "email thiếu tên miền")],
            "tel": [("abcxyz", "số điện thoại chứa chữ"), ("123", "số điện thoại quá ngắn")],
            "url": [("khong-phai-url", "URL sai định dạng")],
            "number": [("-1", "số âm"), ("1.5", "số thập phân")],
        }
        for f in form.fields:
            for value, why in invalid_by_kind.get(f.kind, []):
                drafts.append(FormDraft(f"Sai định dạng {f.label} ({why})", {f.selector: value},
                                        purpose=f"Ô '{f.label}' nhập {why}: \"{value}\""))

    if "gia_tri_bien" in techniques:
        drafts += _boundary_drafts(form)

    if "ky_tu_dac_biet" in techniques and text_fields:
        # Chỉ chèn vào các ô chữ thường (không phải email/số) để không bị chặn bởi định dạng
        targets = [f for f in text_fields if f.kind == "text"] or text_fields
        drafts.append(FormDraft("XSS", {f.selector: XSS_VALUE for f in targets},
                                purpose="Chèn mã script để kiểm tra lỗ hổng XSS"))
        drafts.append(FormDraft("SQL injection", {f.selector: SQLI_VALUE for f in targets},
                                purpose="Chèn chuỗi SQL injection"))
    return drafts


def count_form_cases(form: FormInfo, techniques: set[str]) -> int:
    """Số test case sẽ sinh ra cho một form (để hiển thị trước cho người dùng)."""
    return len(_drafts_for_form(form, techniques))


def _boundary_drafts(form: FormInfo) -> list[FormDraft]:
    """Phân tích giá trị biên dựa vào maxlength, minlength, min, max của từng ô."""
    drafts = []
    for f in form.fields:
        if f.type == "number" and (f.min or f.max):
            points = []
            if f.min:
                lo = _to_number(f.min, 0)
                points += [(lo - 1, "min-1"), (lo, "min")]
            if f.max:
                hi = _to_number(f.max, 0)
                points += [(hi, "max"), (hi + 1, "max+1")]
            for n, name in points:
                drafts.append(FormDraft(f"Biên {f.label} = {name}", {f.selector: _fmt_number(n)},
                                        purpose=f"Ô '{f.label}' nhận giá trị biên {name} = {n}"))
        elif f.is_text and f.kind == "text" and f.type != "number":
            if f.maxlength:
                m = f.maxlength
                drafts.append(FormDraft(f"Biên {f.label} = max", {f.selector: "a" * m},
                                        purpose=f"Ô '{f.label}' nhập đúng {m} ký tự (maxlength)"))
                # Nhập max+1 ký tự: trình duyệt phải tự cắt còn max ký tự
                drafts.append(FormDraft(
                    f"Biên {f.label} = max+1", {f.selector: "a" * (m + 1)},
                    [TestStep(0, "assert_value", f.selector, "a" * m,
                              f"Ô chỉ nhận tối đa {m} ký tự")],
                    purpose=f"Ô '{f.label}' nhập {m + 1} ký tự (vượt maxlength)"))
            if f.minlength:
                n = f.minlength
                drafts.append(FormDraft(f"Biên {f.label} = min-1", {f.selector: "a" * (n - 1)},
                                        purpose=f"Ô '{f.label}' nhập {n - 1} ký tự (dưới minlength)"))
                drafts.append(FormDraft(f"Biên {f.label} = min", {f.selector: "a" * n},
                                        purpose=f"Ô '{f.label}' nhập đúng {n} ký tự (minlength)"))
            if not f.maxlength and not f.minlength and f.type != "password":
                drafts.append(FormDraft(f"Biên {f.label} = 1 ký tự", {f.selector: "a"},
                                        purpose=f"Ô '{f.label}' nhập 1 ký tự"))
                drafts.append(FormDraft(f"Biên {f.label} = 256 ký tự", {f.selector: "a" * 256},
                                        purpose=f"Ô '{f.label}' nhập chuỗi rất dài (256 ký tự)"))
    return drafts


def _fill_steps(form: FormInfo, overrides: dict[str, str]) -> list[TestStep]:
    """Các bước điền form: ô bị ghi đè dùng giá trị ghi đè, còn lại dùng giá trị hợp lệ."""
    steps = []
    for f in form.fields:
        value = overrides.get(f.selector, f.valid_value)
        if f.tag == "select":
            if value:
                steps.append(TestStep(0, "select", f.selector, value, f"Chọn '{value}' ở ô {f.label}"))
        elif f.type in ("checkbox", "radio"):
            if value:
                steps.append(TestStep(0, "click", f.selector, "", f"Tích chọn ô {f.label}"))
        elif value == "":
            steps.append(TestStep(0, "clear", f.selector, "", f"Để trống ô {f.label}"))
        else:
            shown = value if len(value) <= 40 else f"{value[:20]}... ({len(value)} ký tự)"
            steps.append(TestStep(0, "type", f.selector, value, f"Nhập '{shown}' vào ô {f.label}"))
    return steps


def _submit_step(form: FormInfo) -> TestStep:
    if form.submit:
        return TestStep(0, "click", form.submit, "", f"Bấm nút {form.submit_label or 'gửi'}")
    last_text = next((f for f in reversed(form.fields) if f.is_text), form.fields[-1])
    return TestStep(0, "press_key", last_text.selector, "Enter", "Nhấn Enter để gửi form")


# ---------------------------------------------------------------------------
# 3. CHẠY THỬ ĐỂ GHI NHẬN KẾT QUẢ THỰC TẾ
# ---------------------------------------------------------------------------

# Tìm các thông báo đang hiển thị (lỗi, thành công, cảnh báo...) theo các mẫu class/thuộc tính phổ biến
JS_FIND_MESSAGES = r"""
() => {
  const qa = window.__qa;
  const SELS = ['[role="alert"]', '[aria-live="assertive"]', '[aria-live="polite"]',
    '[data-test*="error" i]', '[data-testid*="error" i]', '.invalid-feedback', '.error-message', '.error',
    '.errors', '.alert', '.flash', '#flash', '.toast', '.notification', '.message', '.help-block',
    '.text-danger', '[class*="error" i]', '[class*="invalid" i]', '[class*="success" i]', '[class*="warning" i]'];
  const out = [], seen = new Set();
  for (const s of SELS) {
    for (const el of document.querySelectorAll(s)) {
      if (seen.has(el) || ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'FORM', 'BODY', 'HTML', 'svg'].includes(el.tagName)) continue;
      if (!qa.visible(el) || el.querySelector('input, textarea, select')) continue;
      const text = (el.innerText || '').trim();
      if (!text || text.length > 300) continue;
      seen.add(el);
      out.push({ selector: qa.selector(el), text: text.split('\n')[0].trim().slice(0, 100) });
    }
  }
  return out;
}
"""

# Tìm ô đầu tiên bị trình duyệt đánh dấu không hợp lệ (HTML5 validation)
JS_FIND_INVALID = r"""
(containerSel) => {
  const c = containerSel === 'body' ? document.body : document.querySelector(containerSel);
  if (!c) return null;
  const bad = Array.from(c.querySelectorAll('input, textarea, select'))
    .find(e => e.willValidate && !e.checkValidity());
  return bad ? { selector: window.__qa.selector(bad), message: bad.validationMessage } : null;
}
"""


def _url_part(url: str, before_url: str = "") -> str:
    """
    Phần đặc trưng của URL để dùng với assert_url (assert_url kiểm tra 'có chứa').
    Đổi đường dẫn -> chỉ lấy đường dẫn; cùng đường dẫn mà khác query -> lấy cả query.
    """
    parsed = urlparse(url)
    if before_url and urlparse(before_url).path != parsed.path and parsed.path not in ("", "/"):
        return parsed.path
    part = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return part if part not in ("", "/") else url


def _safe_messages(page) -> list[dict]:
    try:
        return page.evaluate(JS_FIND_MESSAGES)
    except Exception:
        return []


def _observe_form_case(browser, url: str, form: FormInfo, steps_before_submit: list[TestStep],
                       submit: TestStep, timeout_ms: int) -> list[TestStep]:
    """
    Chạy thử các bước trên trình duyệt thật rồi quan sát điều gì xảy ra sau khi gửi form.
    Trả về các bước kiểm tra (assert) mô tả kết quả thực tế, đánh dấu note="auto" hoặc "review".
    """
    context, page = _new_page(browser)
    page.set_default_timeout(timeout_ms)
    dialogs: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    ctx = KeywordContext(screenshot_dir=Path("."), case_slug="sinh_tu_dong", timeout_ms=timeout_ms)
    try:
        try:
            for step in steps_before_submit:
                KEYWORDS[step.keyword](page, step.selector, step.value, ctx)
            before_url = page.url
            before_messages = {m["text"] for m in _safe_messages(page)}
            KEYWORDS[submit.keyword](page, submit.selector, submit.value, ctx)
        except Exception as exc:
            reason = str(exc).split("Call log:")[0].strip().splitlines()[0]
            return [TestStep(0, "assert_text", "", NEED_REVIEW_TEXT,
                             f"Không chạy thử được ({reason}) - cần tự điền kết quả", note="review")]

        # Chờ trang phản hồi (chuyển trang, gọi API, hiện thông báo...)
        page.wait_for_timeout(800)
        try:
            page.wait_for_load_state("networkidle", timeout=3_000)
        except Exception:
            pass

        result: list[TestStep] = []
        if dialogs:
            result.append(TestStep(0, "assert_visible", "body", "",
                                   f"CẢNH BÁO: trang hiện hộp thoại \"{dialogs[0]}\" - nghi ngờ lỗ hổng XSS",
                                   note="review"))

        # Trường hợp 1: chuyển sang trang khác
        if page.url.split("#")[0] != before_url.split("#")[0]:
            expected_url = _url_part(page.url, before_url)
            result.append(TestStep(0, "assert_url", "", expected_url,
                                   f"Chuyển sang trang {expected_url} (tự ghi nhận)", note="auto"))
            return result

        # Trường hợp 2: hiện thông báo mới
        new_messages = [m for m in _safe_messages(page) if m["text"] not in before_messages]
        if new_messages:
            msg = new_messages[0]
            result.append(TestStep(0, "assert_text", msg["selector"], msg["text"],
                                   f"Hiện thông báo \"{msg['text']}\" (tự ghi nhận)", note="auto"))
            return result

        # Trường hợp 3: trình duyệt chặn gửi form do HTML5 validation
        invalid = page.evaluate(JS_FIND_INVALID, form.selector)
        if invalid:
            result.append(TestStep(0, "assert_invalid", invalid["selector"], "",
                                   f"Trình duyệt chặn gửi form: \"{invalid['message']}\" (tự ghi nhận)",
                                   note="auto"))
            return result

        # Trường hợp 4: không thấy thay đổi rõ ràng -> cần người xem lại
        target = form.submit or form.fields[0].selector
        result.append(TestStep(0, "assert_visible", target, "",
                               "Không thấy thay đổi rõ ràng sau khi gửi (form vẫn hiển thị) - cần xem lại",
                               note="review"))
        return result
    finally:
        context.close()


# Chụp nhanh nội dung chữ của mọi phần tử TRƯỚC khi bấm (giữ tham chiếu phần tử trong window.__qaSnap)
JS_SNAPSHOT = r"""
() => {
  const qa = window.__qa, items = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (items.length >= 2000) break;
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'IFRAME'].includes(el.tagName)) continue;
    items.push([el, qa.visible(el) ? (el.innerText || '').trim() : null]);
  }
  window.__qaSnap = items;
}
"""

# So sánh SAU khi bấm: phần tử đổi nội dung hoặc mới hiện ra; giữ phần tử cụ thể nhất,
# ưu tiên phần tử không phải nút/link (VD: số trên giỏ hàng) hơn chính nút vừa bấm
JS_DIFF = r"""
() => {
  const qa = window.__qa;
  const before = new Map(window.__qaSnap || []);
  const textOf = el => { const t = (el.innerText || '').trim(); return t && t.length <= 120 ? t : ''; };
  const leafish = el => el.children.length <= 2;
  // Nội dung đã hiển thị trước khi bấm: phần tử "mới" mà nội dung cũ đã có (VD: React vẽ lại thanh menu)
  // thì không tính là thay đổi
  const shownBefore = new Set(Array.from(before.values()).filter(t => t));
  // Bước kiểm tra chỉ dùng dòng đầu -> chỉ tính là "đổi nội dung" khi chính dòng đầu khác đi
  const firstLine = t => (t || '').split('\n')[0].trim();
  const found = [];
  for (const [el, old] of before) {
    if (!el.isConnected || !qa.visible(el) || !leafish(el) || !textOf(el)) continue;
    if (old === null && !shownBefore.has(textOf(el))) found.push({ el, kind: 'appeared' });
    else if (old !== null && firstLine(old) !== firstLine(el.innerText)) found.push({ el, kind: 'changed' });
  }
  for (const el of document.body.querySelectorAll('*')) {
    if (before.has(el) || ['SCRIPT', 'STYLE'].includes(el.tagName)) continue;
    if (qa.visible(el) && leafish(el) && textOf(el) && !shownBefore.has(textOf(el))) {
      found.push({ el, kind: 'appeared' });
    }
  }
  const els = found.map(f => f.el);
  const specific = found.filter(f => !els.some(o => o !== f.el && f.el.contains(o)));
  // Ưu tiên: chữ thường (0) > nằm trong link (1) > nằm trong nút / ô nhập (2)
  const rank = el => el.closest('button, input, select, textarea, [role=button]') ? 2 : (el.closest('a') ? 1 : 0);
  specific.sort((a, b) => rank(a.el) - rank(b.el));
  return specific.slice(0, 3).map(f => ({
    selector: qa.selector(f.el), text: textOf(f.el).split('\n')[0].trim().slice(0, 100), kind: f.kind }));
}
"""


def _observe_control_case(browser, steps_before: list[TestStep], action: TestStep, control: ControlInfo,
                          timeout_ms: int) -> list[TestStep]:
    """
    Chạy thử: mở trang, bấm nút / tích checkbox, rồi quan sát điều gì xảy ra.
    Thứ tự ưu tiên: chuyển trang > thông báo mới > nội dung thay đổi / phần tử mới hiện > không thấy gì.
    Cuối cùng thêm bước assert_no_js_error (nếu trang không có sẵn lỗi JS từ trước) để phát hiện nút gây lỗi.
    """
    context, page = _new_page(browser)
    page.set_default_timeout(timeout_ms)
    dialogs: list[str] = []
    errors: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    page.on("pageerror", lambda exc: errors.append(str(exc).splitlines()[0]))
    ctx = KeywordContext(screenshot_dir=Path("."), case_slug="sinh_tu_dong", timeout_ms=timeout_ms)
    try:
        try:
            for step in steps_before:
                KEYWORDS[step.keyword](page, step.selector, step.value, ctx)
            page.wait_for_timeout(300)
            errors_before = len(errors)
            before_url = page.url
            before_messages = {m["text"] for m in _safe_messages(page)}
            page.evaluate(JS_SNAPSHOT)
            KEYWORDS[action.keyword](page, action.selector, action.value, ctx)
        except Exception as exc:
            return [TestStep(0, "assert_text", "", NEED_REVIEW_TEXT,
                             f"Không chạy thử được ({_short_error(exc)}) - cần tự điền kết quả", note="review")]

        page.wait_for_timeout(800)
        try:
            page.wait_for_load_state("networkidle", timeout=3_000)
        except Exception:
            pass

        result: list[TestStep] = []
        if dialogs:
            result.append(TestStep(0, "assert_visible", "body", "",
                                   f"Bấm xong trang hiện hộp thoại \"{dialogs[0]}\" - cần xem lại", note="review"))
        if page.url.split("#")[0] != before_url.split("#")[0]:
            expected_url = _url_part(page.url, before_url)
            result.append(TestStep(0, "assert_url", "", expected_url,
                                   f"Chuyển sang trang {expected_url} (tự ghi nhận)", note="auto"))
        else:
            new_messages = [m for m in _safe_messages(page) if m["text"] not in before_messages]
            changes = new_messages or page.evaluate(JS_DIFF)
            if changes:
                change = changes[0]
                what = "Hiện" if change.get("kind", "appeared") == "appeared" else "Nội dung đổi thành"
                result.append(TestStep(0, "assert_text", change["selector"], change["text"],
                                       f"{what} \"{change['text']}\" (tự ghi nhận)", note="auto"))
            else:
                result.append(TestStep(0, "assert_visible", control.selector, "",
                                       f"Không thấy thay đổi rõ ràng sau khi bấm '{control.label}' - cần xem lại",
                                       note="review"))

        if errors_before == 0:  # Trang vốn không có lỗi JS -> kiểm tra việc bấm không gây lỗi JS
            new_errors = errors[errors_before:]
            if new_errors:
                result.append(TestStep(0, "assert_no_js_error", "", "",
                                       f"PHÁT HIỆN LỖI JavaScript khi bấm: \"{new_errors[0]}\" - test này sẽ báo "
                                       "lỗi cho đến khi lỗi được sửa", note="review"))
            else:
                result.append(TestStep(0, "assert_no_js_error", "", "", "Không phát sinh lỗi JavaScript"))
        return result
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 4. TEST CASE CHO LINK, DROPDOWN VÀ HIỂN THỊ TRANG (sinh trực tiếp, không cần chạy thử)
# ---------------------------------------------------------------------------

def _start_steps(scan: PageScan) -> list[TestStep]:
    """Các bước mở đầu của mọi test case: bước chuẩn bị (nếu có, sao chép mới) rồi mở trang."""
    return [replace(s) for s in scan.setup] + [TestStep(0, "open", "", scan.url, "Mở trang")]


def _page_check_case(scan: PageScan) -> TestCase:
    steps = _start_steps(scan)
    if scan.title:
        steps.append(TestStep(0, "assert_title", "", scan.title, "Kiểm tra tiêu đề trang", note="auto"))
    for h in scan.headings:
        steps.append(TestStep(0, "assert_visible", h["selector"], "", f"Hiển thị tiêu đề \"{h['text']}\""))
    for form in scan.forms:
        for f in form.fields:
            steps.append(TestStep(0, "assert_visible", f.selector, "", f"Hiển thị ô {f.label}"))
        if form.submit:
            steps.append(TestStep(0, "assert_visible", form.submit, "", f"Hiển thị nút {form.submit_label}"))
    steps.append(TestStep(0, "screenshot", "", "", "Chụp ảnh trang"))
    return TestCase(name="Hiển thị trang", steps=steps)


def _link_case(scan: PageScan, link: LinkInfo, index: int) -> TestCase:
    steps = _start_steps(scan)
    if link.new_tab:
        steps.append(TestStep(0, "assert_visible", link.selector, "",
                              f"Link '{link.text}' mở ở tab mới - chỉ kiểm tra hiển thị"))
    else:
        steps += [
            TestStep(0, "click", link.selector, "", f"Bấm link '{link.text}'"),
            TestStep(0, "assert_url", "", _url_part(link.href, scan.url), f"Chuyển đến {link.href}"),
        ]
    return TestCase(name=f"L{index:02d} Link {link.text}", steps=steps)


def _link_cases(scan: PageScan, links: list[LinkInfo], observe: bool, browser_name: str,
                timeout_ms: int) -> list[TestCase]:
    """
    Test cho link. Khi chạy thử (observe): bấm link thật và ghi nhận URL đích THỰC TẾ (tính cả chuyển hướng,
    VD: Đăng xuất -> trang đăng nhập) thay vì tin vào href; link tải file sẽ được đánh dấu cần xem lại.
    """
    to_observe = [l for l in links if observe and not l.new_tab]
    if not to_observe:
        return [_link_case(scan, l, i) for i, l in enumerate(links, start=1)]
    cases = []
    with sync_playwright() as p:
        browser = launch_browser(p, browser_name, headless=True)
        try:
            for i, link in enumerate(links, start=1):
                if link.new_tab:
                    cases.append(_link_case(scan, link, i))
                    continue
                before = _start_steps(scan)
                action = TestStep(0, "click", link.selector, "", f"Bấm link '{link.text}'")
                expected = _observe_control_case(browser, before, action, ControlInfo(link.selector, link.text, "link"),
                                                 timeout_ms)
                cases.append(TestCase(name=f"L{i:02d} Link {link.text}", steps=before + [action] + expected))
        finally:
            browser.close()
    return cases


def _select_case(scan: PageScan, select: SelectInfo, index: int) -> TestCase:
    steps = _start_steps(scan)
    for opt in select.options[:8]:
        steps += [
            TestStep(0, "select", select.selector, opt["value"], f"Chọn '{opt['label']}'"),
            TestStep(0, "assert_value", select.selector, opt["value"], f"Ô chọn có giá trị '{opt['value']}'"),
        ]
    return TestCase(name=f"S{index} Dropdown {select.label}", steps=steps)


# ---------------------------------------------------------------------------
# HÀM CHÍNH
# ---------------------------------------------------------------------------

def generate_cases(
    scan: PageScan,
    forms: list[FormInfo],
    techniques: set[str],
    links: list[LinkInfo] = (),
    selects: list[SelectInfo] = (),
    controls: list[ControlInfo] = (),
    include_page_check: bool = True,
    observe: bool = True,
    browser_name: str = "chromium",
    timeout_ms: int = 5_000,
    on_progress: Callable[[int, int, str], None] | None = None,
    name_prefix: str = "",
) -> list[TestCase]:
    """
    Sinh danh sách test case từ các thành phần người dùng đã chọn.
    observe=True: chạy thử từng test case của form để ghi nhận kết quả mong đợi.
    on_progress(đã_xong, tổng, tên_case) để hiện tiến trình.
    name_prefix: tiền tố tên test case (VD: "P2 " khi quét nhiều trang) để biết test thuộc trang nào.
    """
    cases: list[TestCase] = []
    if include_page_check:
        cases.append(_page_check_case(scan))

    # Chuẩn bị bản nháp cho từng form
    form_jobs = []  # (tên case, form, bước trước khi gửi, bước gửi, mục đích)
    for fi, form in enumerate(forms, start=1):
        for di, draft in enumerate(_drafts_for_form(form, techniques), start=1):
            before = _start_steps(scan) + _fill_steps(form, draft.overrides) + draft.pre_submit_checks
            form_jobs.append((f"F{fi}-{di:02d} {draft.name}", form, before, _submit_step(form), draft.purpose))

    total = len(form_jobs) + len(controls)
    browser = None
    placeholder = lambda: [TestStep(0, "assert_text", "", NEED_REVIEW_TEXT, "Điền kết quả mong đợi", note="review")]
    with sync_playwright() as p:
        if observe and (form_jobs or controls):
            browser = launch_browser(p, browser_name, headless=True)
        try:
            for done, (name, form, before, submit, purpose) in enumerate(form_jobs, start=1):
                if on_progress:
                    on_progress(done - 1, total, name)
                if browser:
                    expected = _observe_form_case(browser, scan.url, form, before, submit, timeout_ms)
                else:
                    expected = placeholder()
                steps = before + [submit] + expected
                steps[len(scan.setup)].description = f"Mở trang - Mục đích: {purpose}"  # Bước "open" sau chuẩn bị
                cases.append(TestCase(name=name, steps=steps))

            # Nút bấm / checkbox / radio đứng riêng: bấm rồi ghi nhận điều xảy ra
            for ci, control in enumerate(controls, start=1):
                name = f"C{ci:02d} {control.kind_text} {control.label}"
                if on_progress:
                    on_progress(len(form_jobs) + ci - 1, total, name)
                before = _start_steps(scan)
                action = TestStep(0, "click", control.selector, "", f"Bấm {control.kind_text.lower()} '{control.label}'")
                if browser:
                    expected = _observe_control_case(browser, before, action, control, timeout_ms)
                else:
                    expected = placeholder() + [TestStep(0, "assert_no_js_error", "", "", "Không phát sinh lỗi JavaScript")]
                cases.append(TestCase(name=name, steps=before + [action] + expected))
        finally:
            if browser:
                browser.close()

    cases += _link_cases(scan, links, observe, browser_name, timeout_ms)
    cases += [_select_case(scan, s, i) for i, s in enumerate(selects, start=1)]

    # Đánh lại số thứ tự bước cho từng test case, gắn tiền tố tên (nếu có),
    # đánh dấu "cần xem lại" các bước dùng selector theo vị trí (dễ hỏng)
    for case in cases:
        case.name = name_prefix + case.name
        for i, step in enumerate(case.steps, start=1):
            step.step_no = i
            mark_fragile(step)
    if on_progress:
        on_progress(total, total, "Hoàn tất")
    return cases


GENERATED_NOTES = [
    "File này được công cụ TỰ SINH từ việc quét trang web.",
    "Dòng tô VÀNG: kết quả mong đợi do công cụ tự ghi nhận khi chạy thử (= hành vi hiện tại của trang).",
    "   -> Hãy kiểm tra lại: nếu hành vi hiện tại là SAI so với yêu cầu thì sửa lại giá trị mong đợi.",
    "Dòng tô CAM: công cụ không xác định được kết quả, cần người kiểm thử tự điền/sửa.",
    "   hoặc selector dựa vào vị trí (nth-of-type) - dễ hỏng khi giao diện thay đổi, nên thay bằng selector ổn định hơn.",
    "Kỹ thuật thiết kế test: phân vùng tương đương (hợp lệ/không hợp lệ), bỏ trống trường,",
    "   sai định dạng, phân tích giá trị biên (min-1, min, max, max+1), ký tự đặc biệt (XSS, SQL injection).",
    "Sheet 'Ghi chú' này được bỏ qua khi chạy kiểm thử.",
]
