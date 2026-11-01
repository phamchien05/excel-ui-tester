"""
Ghi lại thao tác của người dùng trên trình duyệt thành kịch bản kiểm thử (recorder).

Cách hoạt động:
  1. Mở trình duyệt CÓ GIAO DIỆN tại URL cho trước (mặc định Google Chrome trên máy, không có thì Chromium).
  2. Nạp đoạn JavaScript lắng nghe sự kiện click, nhập chữ, chọn dropdown, nhấn Enter.
     Mỗi thao tác được gửi về Python qua hàm cầu nối window.__qaRecord (expose_binding).
  3. Trên trang có thanh công cụ nổi để chèn bước kiểm tra:
       ✔ Kiểm tra chữ    : bấm vào một phần tử -> thêm bước assert_text với chữ đang hiển thị
       👁 Kiểm tra hiển thị: bấm vào một phần tử -> thêm bước assert_visible
       🔗 Kiểm tra URL   : thêm bước assert_url với URL hiện tại
       ⏹ Dừng ghi       : kết thúc (hoặc đóng cửa sổ trình duyệt)
  4. Trả về danh sách bước (TestStep) để ghi ra Excel.
"""

from __future__ import annotations

import time
from typing import Callable
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from core.dom import QA_HELPERS_JS, mark_fragile
from core.generator import _url_part
from core.reader import TestStep
from core.runner import launch_browser

RECORDER_JS = r"""
(() => {
  if (window.__qaRecorderLoaded || window.top !== window) return;  // Chỉ chạy ở khung chính
  window.__qaRecorderLoaded = true;

  let mode = null;              // null | 'text' | 'visible' : đang chờ chọn phần tử để kiểm tra
  let host = null, countEl = null, statusEl = null, box = null;

  const send = (payload) => window.__qaRecord(payload)
    .then(n => { if (countEl && typeof n === 'number') countEl.textContent = n + ' bước'; })
    .catch(() => {});
  const fromToolbar = (e) => host && e.composedPath().includes(host);
  const NON_TEXT = ['checkbox', 'radio', 'submit', 'button', 'image', 'reset', 'file', 'range', 'color', 'hidden'];
  const isTextInput = (el) => (el.tagName === 'INPUT' && !NON_TEXT.includes(el.type)) || el.tagName === 'TEXTAREA';
  const INTERACTIVE = 'a, button, input, select, textarea, label, summary, [role=button], [role=link], ' +
                      '[role=tab], [role=menuitem], [role=checkbox], [onclick]';
  const info = (el) => ({ selector: window.__qa.target(el), label: window.__qa.label(el) });
  const setStatus = (t) => { if (statusEl) statusEl.textContent = t; };

  function buildToolbar() {
    if (host || !document.body) return;
    host = document.createElement('div');
    host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;';
    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>
        .bar { font: 13px Segoe UI, Arial, sans-serif; background: #1f2937; color: #fff; padding: 10px 12px;
               border-radius: 10px; box-shadow: 0 6px 20px rgba(0,0,0,.35); display: flex; flex-wrap: wrap;
               gap: 6px; align-items: center; max-width: 470px; }
        .dot { width: 10px; height: 10px; border-radius: 50%; background: #ef4444; animation: b 1s infinite; }
        @keyframes b { 50% { opacity: .3; } }
        button { font: inherit; border: 0; border-radius: 6px; padding: 5px 9px; cursor: pointer; background: #374151; color: #fff; }
        button:hover { background: #4b5563; } button.on { background: #2563eb; } button.stop { background: #dc2626; }
        #status { width: 100%; color: #fbbf24; font-size: 12px; min-height: 0; }
      </style>
      <div class="bar">
        <span class="dot"></span><b>Đang ghi</b><span id="count" style="opacity:.8;margin-right:6px">...</span>
        <button data-a="text">✔ Kiểm tra chữ</button>
        <button data-a="visible">👁 Kiểm tra hiển thị</button>
        <button data-a="url">🔗 Kiểm tra URL</button>
        <button data-a="stop" class="stop">⏹ Dừng ghi</button>
        <div id="status"></div>
      </div>`;
    countEl = root.getElementById('count');
    statusEl = root.getElementById('status');
    root.querySelectorAll('button').forEach(btn => btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const a = btn.dataset.a;
      if (a === 'url') { send({ action: 'assert_url', value: location.href }); setStatus('Đã thêm bước kiểm tra URL'); }
      else if (a === 'stop') { send({ action: 'stop' }); setStatus('Đã dừng ghi. Quay lại công cụ để lưu kịch bản.'); }
      else {
        mode = (mode === a) ? null : a;
        root.querySelectorAll('button[data-a=text], button[data-a=visible]').forEach(b => b.classList.toggle('on', b.dataset.a === mode));
        setStatus(mode ? 'Bấm vào phần tử cần kiểm tra (Esc để hủy)' : '');
      }
    }));
    document.documentElement.appendChild(host);

    // Khung đỏ bao quanh phần tử khi đang ở chế độ chọn phần tử kiểm tra
    box = document.createElement('div');
    box.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483646;border:2px solid #e11d48;' +
                        'background:rgba(225,29,72,.08);display:none;';
    document.documentElement.appendChild(box);
    send({ action: 'ping' });
  }

  function endPickMode() {
    mode = null; box.style.display = 'none'; setStatus('');
    host.shadowRoot.querySelectorAll('button.on').forEach(b => b.classList.remove('on'));
  }

  // ----- Chế độ chọn phần tử để kiểm tra -----
  window.addEventListener('mousemove', (e) => {
    if (!mode || fromToolbar(e)) { if (box) box.style.display = 'none'; return; }
    const r = e.target.getBoundingClientRect();
    Object.assign(box.style, { display: 'block', left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: r.height + 'px' });
  }, true);
  for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup']) {
    window.addEventListener(type, (e) => {
      if (mode && !fromToolbar(e)) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);
  }

  // ----- Click -----
  window.addEventListener('click', (e) => {
    if (fromToolbar(e) || !e.isTrusted) return;  // Bỏ qua click tự sinh (VD: click label -> click input)
    if (mode) {
      e.preventDefault(); e.stopImmediatePropagation();
      const el = e.target;
      if (mode === 'text') {
        const text = (el.innerText || el.value || '').trim().split('\n')[0].trim().slice(0, 100);
        send({ action: text ? 'assert_text' : 'assert_visible', value: text, ...info(el) });
      } else {
        send({ action: 'assert_visible', ...info(el) });
      }
      endPickMode();
      return;
    }
    const el = e.target.closest(INTERACTIVE) ||
               (getComputedStyle(e.target).cursor === 'pointer' ? e.target : null);
    if (!el || isTextInput(el) || el.tagName === 'SELECT') return;  // Click để đặt con trỏ vào ô nhập thì bỏ qua
    send({ action: 'click', ...info(el) });
  }, true);

  // ----- Nhập chữ, chọn dropdown, nhấn Enter -----
  window.addEventListener('input', (e) => {
    const el = e.target;
    if (fromToolbar(e) || !isTextInput(el)) return;
    send({ action: 'type', value: el.value, ...info(el) });
  }, true);
  window.addEventListener('change', (e) => {
    const el = e.target;
    if (el.tagName !== 'SELECT') return;
    send({ action: 'select', value: el.value, option: (el.selectedOptions[0] || {}).text || el.value, ...info(el) });
  }, true);
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && mode) { endPickMode(); return; }
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && isTextInput(e.target) && !fromToolbar(e)) {
      send({ action: 'press_key', value: 'Enter', ...info(e.target) });
    }
  }, true);

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', buildToolbar);
  else buildToolbar();
})();
"""


def _to_step(payload: dict) -> TestStep:
    """Chuyển một thao tác (gửi từ JavaScript) thành bước kịch bản kèm mô tả tiếng Việt."""
    action = payload["action"]
    selector = payload.get("selector", "")
    value = payload.get("value", "")
    label = payload.get("label", "") or selector
    if action == "click":
        return TestStep(0, "click", selector, "", f"Bấm '{label}'")
    if action == "type":
        return TestStep(0, "type", selector, value, f"Nhập vào ô {label}")
    if action == "select":
        return TestStep(0, "select", selector, value, f"Chọn '{payload.get('option', value)}' ở ô {label}")
    if action == "press_key":
        return TestStep(0, "press_key", selector, value, f"Nhấn {value} tại ô {label}")
    if action == "assert_text":
        return TestStep(0, "assert_text", selector, value, f"Kiểm tra hiển thị chữ \"{value}\"")
    if action == "assert_visible":
        return TestStep(0, "assert_visible", selector, "", f"Kiểm tra '{label}' đang hiển thị")
    if action == "assert_url":
        part = _url_part(value)
        return TestStep(0, "assert_url", "", part, f"Kiểm tra đang ở trang {part}")
    raise ValueError(f"Thao tác không hỗ trợ: {action}")


def _launch_for_recording(playwright, browser_name: str, headless: bool):
    """
    Mở trình duyệt để ghi thao tác. Với chromium: ưu tiên Google Chrome đã cài trên máy
    (người dùng quen thuộc hơn), nếu máy không có Chrome thì dùng Chromium đi kèm Playwright.
    """
    if browser_name == "chromium":
        args = ["--start-maximized"]
        try:
            return launch_browser(playwright, "chromium", channel="chrome", headless=headless, args=args)
        except Exception:
            return launch_browser(playwright, "chromium", headless=headless, args=args)
    return launch_browser(playwright, browser_name, headless=headless)


def record(
    url: str,
    browser_name: str = "chromium",
    on_step: Callable[[TestStep], None] | None = None,
    max_minutes: int = 30,
    headless: bool = False,
    script: Callable | None = None,
) -> list[TestStep]:
    """
    Mở trình duyệt (mặc định Google Chrome), ghi lại thao tác cho đến khi người dùng bấm "Dừng ghi"
    hoặc đóng trình duyệt.
    on_step(bước) được gọi mỗi khi ghi thêm một bước (để hiện trực tiếp lên giao diện).
    headless, script: chỉ dùng khi tự kiểm thử bộ ghi - script(page) tự thao tác thay cho người dùng.
    """
    if not urlparse(url).scheme:
        url = "https://" + url
    steps: list[TestStep] = [TestStep(1, "open", "", url, "Mở trang")]
    state = {"stop": False}

    def on_record(source, payload: dict):
        """Hàm Python được JavaScript gọi mỗi khi có thao tác. Trả về số bước hiện có."""
        action = payload.get("action")
        if action == "stop":
            state["stop"] = True
        elif action != "ping":
            step = mark_fragile(_to_step(payload))  # Selector theo vị trí -> tô cam "cần xem lại"
            last = steps[-1]
            # Mỗi ký tự gõ vào sinh một sự kiện -> gộp các lần gõ liên tiếp vào cùng một ô
            if step.keyword == "type" and last.keyword == "type" and last.selector == step.selector:
                last.value = step.value
            else:
                step.step_no = len(steps) + 1
                steps.append(step)
                if on_step:
                    on_step(step)
        return len(steps)

    with sync_playwright() as p:
        browser = _launch_for_recording(p, browser_name, headless)
        try:
            # Có giao diện: dùng kích thước cửa sổ thật; headless: đặt kích thước cố định
            context = browser.new_context(**({"viewport": {"width": 1366, "height": 768}} if headless
                                              else {"no_viewport": True}))
            context.expose_binding("__qaRecord", on_record)
            context.add_init_script(QA_HELPERS_JS)
            context.add_init_script(RECORDER_JS)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            if script:
                script(page)

            # Vòng chờ: nhường cho Playwright xử lý sự kiện cho đến khi dừng ghi / đóng trình duyệt
            deadline = time.time() + max_minutes * 60
            while not state["stop"] and time.time() < deadline:
                open_pages = [pg for pg in context.pages if not pg.is_closed()]
                if not open_pages or not browser.is_connected():
                    break
                try:
                    open_pages[0].wait_for_timeout(200)
                except Exception:
                    break  # Người dùng đóng trình duyệt
        finally:
            try:
                browser.close()
            except Exception:
                pass

    for i, step in enumerate(steps, start=1):
        step.step_no = i
    return steps
