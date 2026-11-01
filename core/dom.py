"""
Đoạn JavaScript dùng chung, được nạp vào trang web để:
  - Sinh selector ổn định cho một phần tử (dùng cho cả quét trang và ghi thao tác).
  - Lấy nhãn dễ đọc của phần tử (để viết cột Mô tả).
  - Kiểm tra phần tử có đang hiển thị không.

Sau khi nạp, trang có đối tượng window.__qa với các hàm: selector(el), target(el), label(el), visible(el).

Thứ tự ưu tiên khi sinh selector (càng ổn định càng ưu tiên):
  #id  >  [data-test=...]  >  tag[name=...]  >  a[href=...]  >  text="..."  >  [placeholder]  >  [aria-label]
  >  theo ảnh bên trong (link/nút chỉ có ảnh, VD: logo: a:has(img[alt="..."]))  >  đường dẫn CSS

Đường dẫn CSS có :nth-of-type(n) phụ thuộc vào VỊ TRÍ phần tử nên dễ hỏng khi giao diện thay đổi
(thêm/bớt một phần tử là lệch). Các bước dùng selector loại này được đánh dấu "cần xem lại" (mark_fragile).
"""

QA_HELPERS_JS = r"""
(() => {
  if (window.__qa) return;

  // Selector có khớp đúng 1 phần tử không
  const unique = (sel) => { try { return document.querySelectorAll(sel).length === 1; } catch (e) { return false; } };
  const quote = (v) => v.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  // Bỏ qua id sinh ngẫu nhiên (VD: ":r1:", "ember123", "id-48213")
  const goodId = (id) => /^[A-Za-z][\w-]*$/.test(id) && !/\d{3,}/.test(id);
  // Mã phiên trong đường dẫn (VD: "index.htm;jsessionid=AB12...") thay đổi mỗi lần truy cập -> không dùng làm selector
  const hasSession = (v) => /;jsessionid=|[?&](jsessionid|phpsessid|sessionid|sid)=/i.test(v);

  function visible(el) {
    if (!el || !el.getClientRects || el.getClientRects().length === 0) return false;
    // Nằm trong vùng bị đánh dấu ẩn (VD: menu trượt đang đóng có aria-hidden="true")
    if (el.closest && el.closest('[aria-hidden="true"], [hidden], [inert]')) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || parseFloat(st.opacity || '1') === 0) return false;
    const r = el.getBoundingClientRect();
    // Kích thước 0 (VD: thẻ <a> bao quanh ảnh được float/định vị riêng như logo parabank):
    // bản thân phần tử không bấm được, chỉ coi là hiển thị nếu có phần tử con hiển thị
    if (r.width === 0 || r.height === 0) return Array.from(el.children).some(visible);
    // Bị đẩy hẳn ra ngoài trang (VD: menu trượt dùng transform: translateX(-100%))
    return r.right + window.scrollX > 0 && r.bottom + window.scrollY > 0;
  }

  function cssPath(el) {
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && cur !== document.documentElement) {
      if (cur.id && goodId(cur.id) && unique('#' + CSS.escape(cur.id))) { parts.unshift('#' + CSS.escape(cur.id)); break; }
      let part = cur.tagName.toLowerCase();
      const parent = cur.parentElement;
      if (parent) {
        const same = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
        if (same.length > 1) part += ':nth-of-type(' + (same.indexOf(cur) + 1) + ')';
      }
      parts.unshift(part);
      if (unique(parts.join(' > '))) break;
      cur = parent;
    }
    return parts.join(' > ');
  }

  // Link/nút chỉ chứa ảnh (VD: logo): dựa vào thuộc tính của ảnh bên trong thay vì vị trí
  function byImage(el, tag) {
    if ((el.innerText || '').trim()) return '';
    const img = el.querySelector('img');
    if (!img) return '';
    const inner = [];
    for (const attr of ['alt', 'title']) {
      const v = (img.getAttribute(attr) || '').trim();
      if (v) inner.push(`img[${attr}="${quote(v)}"]`);
    }
    const src = img.getAttribute('src') || '';
    const file = src.startsWith('data:') ? '' : src.split(/[?#;]/)[0].split('/').pop();
    if (file) inner.push(`img[src*="${quote(file)}"]`);
    for (const c of img.classList) if (/^[A-Za-z][\w-]*$/.test(c)) inner.push('img.' + c);
    for (const part of inner) { const s = `${tag}:has(${part})`; if (unique(s)) return s; }
    return '';
  }

  // Selector để BẤM vào phần tử: phần tử kích thước 0 (link bao ảnh) thì bấm vào ảnh bên trong
  function target(el) {
    const sel = selector(el);
    const r = el.getBoundingClientRect();
    if (r.width && r.height) return sel;
    const child = Array.from(el.querySelectorAll('img, svg')).find(visible);
    return child ? `${sel} ${child.tagName.toLowerCase()}` : sel;
  }

  function selector(el) {
    if (!el || el.nodeType !== 1) return '';
    const tag = el.tagName.toLowerCase();
    if (el.id && goodId(el.id) && unique('#' + CSS.escape(el.id))) return '#' + CSS.escape(el.id);
    for (const attr of ['data-test', 'data-testid', 'data-test-id', 'data-qa', 'data-cy']) {
      const v = el.getAttribute(attr);
      if (v) { const s = `[${attr}="${quote(v)}"]`; if (unique(s)) return s; }
    }
    const name = el.getAttribute('name');
    if (name) { const s = `${tag}[name="${quote(name)}"]`; if (unique(s)) return s; }
    if (tag === 'a') {
      const href = el.getAttribute('href');
      if (href && href !== '#' && !hasSession(href)) { const s = `a[href="${quote(href)}"]`; if (unique(s)) return s; }
    }
    if (['a', 'button', 'label', 'summary'].includes(tag) || el.getAttribute('role') === 'button') {
      const text = (el.innerText || '').trim();
      if (text && text.length <= 40 && !text.includes('\n')) {
        const same = Array.from(document.querySelectorAll('a,button,label,summary,[role=button]'))
          .filter(x => (x.innerText || '').trim() === text);
        if (same.length === 1) return `text="${quote(text)}"`;
      }
    }
    for (const attr of ['placeholder', 'aria-label', 'title', 'alt']) {
      const v = el.getAttribute(attr);
      if (v) { const s = `${tag}[${attr}="${quote(v)}"]`; if (unique(s)) return s; }
    }
    if (['a', 'button'].includes(tag) || el.getAttribute('role') === 'button') {
      const s = byImage(el, tag);
      if (s) return s;
    }
    return cssPath(el);
  }

  // Nhãn của link/nút chỉ có ảnh: lấy alt/title của ảnh bên trong
  function imageLabel(el) {
    const img = el.querySelector && el.querySelector('img[alt], img[title]');
    return img ? (img.getAttribute('alt') || img.getAttribute('title') || '').replace(/\s+/g, ' ').trim().slice(0, 50) : '';
  }

  function label(el) {
    if (!el) return '';
    const clean = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 50);
    if (el.id) {
      const lb = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lb && clean(lb.innerText)) return clean(lb.innerText);
    }
    const parentLabel = el.closest && el.closest('label');
    if (parentLabel) {
      // Bỏ chữ của chính ô nhập (VD: các <option> của select) ra khỏi nhãn
      const copy = parentLabel.cloneNode(true);
      copy.querySelectorAll('input, select, textarea').forEach(x => x.remove());
      if (clean(copy.textContent)) return clean(copy.textContent);
    }
    return clean(el.getAttribute('aria-label')) || clean(el.getAttribute('placeholder'))
      || clean(el.getAttribute('title')) || clean(el.getAttribute('alt'))
      || (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) ? '' : clean(el.innerText))
      || imageLabel(el)
      || (el.tagName === 'INPUT' && ['submit', 'button', 'reset'].includes(el.type) ? clean(el.value) : '')
      || clean(el.getAttribute('name')) || clean(el.id) || clean(el.getAttribute('data-test'))
      || (el.tagName === 'SELECT' ? '' : clean(el.value)) || el.tagName.toLowerCase();
  }

  window.__qa = { selector, target, label, visible, unique };
})();
"""


FRAGILE_NOTE = "selector dựa vào vị trí (nth-of-type), dễ hỏng khi giao diện thay đổi - cần xem lại"


def is_fragile_selector(selector: str) -> bool:
    """Selector có phụ thuộc vào vị trí phần tử (thứ tự trong trang) không."""
    return ":nth-of-type(" in (selector or "")


def mark_fragile(step):
    """Đánh dấu "cần xem lại" (tô cam trong Excel) cho bước dùng selector theo vị trí. Trả lại chính bước đó."""
    if is_fragile_selector(step.selector):
        step.note = "review"
        if FRAGILE_NOTE not in step.description:
            step.description = f"{step.description} ({FRAGILE_NOTE})".strip()
    return step
