"""
Thành phần giao diện dùng chung cho app.py: header, tiêu đề khu vực, thẻ số liệu, nhãn, biểu đồ...

Mọi khối HTML tự viết đều đi qua các hàm ở đây để toàn ứng dụng cùng một kiểu.
Kiểu dáng (CSS) nằm trong assets/style.css; màu cho bảng (pandas Styler) và biểu đồ (Altair)
lấy từ COLORS bên dưới — trùng với biến CSS trong style.css.
"""

from __future__ import annotations

import re
from html import escape as html_escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ASSETS = Path(__file__).parent / "assets"
CSS_FILE = ASSETS / "style.css"
LOGO_SVG = ASSETS / "logo.svg"
LOGO_PNG = ASSETS / "logo.png"   # Dùng làm biểu tượng trên tab trình duyệt (favicon)

COLORS = {
    "bg": "#0A0A0B", "card": "#141518", "card_hover": "#1A1C20", "border": "#24262B",
    "text": "#F4F4F5", "text_2": "#A1A1AA", "text_muted": "#71717A",
    "blue": "#3B82F6", "blue_soft": "rgba(59,130,246,0.12)",
    "pass": "#22C55E", "pass_soft": "rgba(34,197,94,0.12)",
    "fail": "#EF4444", "fail_soft": "rgba(239,68,68,0.12)",
    "warn": "#F59E0B", "warn_soft": "rgba(245,158,11,0.12)",
}

# Màu chữ cho các giá trị trạng thái hiển thị trong bảng
STATUS_COLOR = {"Đạt": COLORS["pass"], "Sẵn sàng": COLORS["pass"], "Lỗi": COLORS["fail"],
                "Bỏ qua": COLORS["text_muted"], "Cảnh báo": COLORS["warn"],
                "Tự ghi nhận": COLORS["warn"], "Cần xem lại": COLORS["warn"]}
# Nền dòng trong bảng xem trước kịch bản tự sinh
NOTE_BACKGROUND = {"Tự ghi nhận": COLORS["warn_soft"], "Cần xem lại": COLORS["fail_soft"]}

# Biểu tượng (SVG nét mảnh, 18px, màu theo chữ) cho các thẻ tính năng
ICONS = {
    "play": '<polygon points="7 4 20 12 7 20 7 4"/>',
    "sparkles": '<path d="M12 3l1.9 5.8L20 10.7l-6.1 1.9L12 18.5l-1.9-5.9L4 10.7l6.1-1.9z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M8 16v-4"/><path d="M13 16V8"/><path d="M18 16v-6"/>',
}


# ---------------------------------------------------------------------------
# Hàm cơ bản
# ---------------------------------------------------------------------------

def load_css():
    """Nạp assets/style.css một lần ở đầu app."""
    st.markdown(f"<style>{CSS_FILE.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def html(markup: str):
    """Hiển thị HTML. Không thụt đầu dòng trong chuỗi HTML (Markdown sẽ hiểu là khối code)."""
    st.markdown(markup, unsafe_allow_html=True)


def md(text) -> str:
    """Escape ký tự $ trước khi đưa vào Markdown: Streamlit hiểu $...$ là công thức toán
    (VD: thông báo lỗi 'mong đợi "$19.99" nhưng thực tế là "$29.99"' sẽ bị méo chữ)."""
    return str(text).replace("$", "\\$")


def esc(text) -> str:
    """Escape chuỗi để chèn vào HTML (kể cả ký tự $ vì lý do như trên)."""
    return html_escape(str(text)).replace("$", "&#36;")


def muted(text: str) -> str:
    """Đoạn chữ mờ nhỏ, dùng chèn cạnh huy hiệu trong Markdown."""
    return f'<span class="qa-muted">{esc(text)}</span>'


def card(key: str):
    """Khung thẻ (nền thẻ, viền, bo góc 12px). key phải duy nhất trong trang."""
    return st.container(border=True, key=f"card_{key}")


def table(data: pd.DataFrame | pd.io.formats.style.Styler, **kwargs):
    """Bảng dữ liệu cùng một kiểu: không hiện cột chỉ số, rộng hết khung, dòng cao 44px."""
    st.dataframe(data, hide_index=True, width="stretch", row_height=44, **kwargs)


# ---------------------------------------------------------------------------
# Khối giao diện
# ---------------------------------------------------------------------------

def logo_svg() -> str:
    """Nội dung assets/logo.svg gộp thành một dòng (bỏ chú thích) để chèn thẳng vào HTML."""
    text = re.sub(r"<!--.*?-->", "", LOGO_SVG.read_text(encoding="utf-8"), flags=re.S)
    return " ".join(line.strip() for line in text.splitlines() if line.strip())


def header(title: str, subtitle: str):
    html(f'<div class="qa-header"><div class="qa-logo">{logo_svg()}</div><div>'
         f'<div class="qa-title">{esc(title)}</div><div class="qa-sub">{esc(subtitle)}</div></div></div>')


def section(title: str, hint: str = "", number=None, anchor: str = ""):
    """Tiêu đề khu vực 18px; có thể kèm số thứ tự bước, dòng gợi ý mờ và id để cuộn tới (anchor)."""
    badge = f'<span class="n">{number}</span>' if number is not None else ""
    hint_html = f'<span class="hint">{esc(hint)}</span>' if hint else ""
    anchor_attr = f' id="{esc(anchor)}"' if anchor else ""
    html(f'<div class="qa-section"{anchor_attr}>{badge}<span class="t">{esc(title)}</span>{hint_html}</div>')


def metrics(items: list[tuple]):
    """Hàng ô số liệu cùng kiểu. items = [(nhãn, giá trị, màu)] với màu: '' (xanh), 'pass', 'fail', 'warn', 'text'."""
    cells = "".join(f'<div class="qa-card qa-metric"><div class="l">{esc(label)}</div>'
                    f'<div class="v {tone}">{esc(value)}</div></div>' for label, value, tone in items)
    cols = len(items) if len(items) <= 5 else 3  # 6 ô -> 2 hàng x 3 cột cho cân
    html(f'<div class="qa-metrics cols-{cols}">{cells}</div>')


def info_bar(items: list[tuple]):
    """
    Thanh thông tin chỉ để đọc (không phải nút): mỗi mục gồm nhãn nhỏ phía trên và giá trị phía dưới,
    ngăn cách bằng vạch dọc. items = [(nhãn, giá trị)].
    """
    cells = "".join(f'<div class="item"><div class="l">{esc(label)}</div><div class="v">{esc(value)}</div></div>'
                    for label, value in items)
    html(f'<div class="qa-info">{cells}</div>')


def chips(texts: list[str], bold_first: bool = False):
    """Hàng nhãn nhỏ. bold_first=True: in đậm nhãn đầu tiên (thường là tên)."""
    items = [f"<b>{esc(t)}</b>" if bold_first and i == 0 else esc(t) for i, t in enumerate(texts)]
    html('<div class="qa-chips">' + "".join(f'<span class="qa-chip">{t}</span>' for t in items) + "</div>")


def verdict(tone: str, text: str):
    """Kết luận dạng viên thuốc lớn: tone = pass / fail / warn."""
    html(f'<div class="qa-verdict {tone}">{esc(text)}</div>')


def hero(title: str, subtitle: str, features: list[tuple]):
    """
    Khối giới thiệu + thẻ tính năng. features = [(icon, tiêu đề, mô tả, vị trí, đích)]
    đích: số thứ tự tab cần mở khi bấm thẻ ("1", "2"...) hoặc id của phần tử cần cuộn tới ("#qa-history").
    """
    cards = "".join(
        f'<div class="qa-card qa-feature" data-target="{esc(target)}" role="link" tabindex="0">'
        f'<div class="ico"><svg width="18" height="18" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'{ICONS[icon]}</svg></div><div class="t">{esc(t)}</div><div class="d">{esc(d)}</div>'
        f'<div class="go">→ {esc(where)}</div></div>' for icon, t, d, where, target in features)
    html(f'<div class="qa-card qa-hero"><div class="qa-hero-title">{esc(title)}</div>'
         f'<div class="qa-hero-sub">{esc(subtitle)}</div><div class="qa-features">{cards}</div></div>')


# Bấm thẻ tính năng -> bấm hộ vào tab tương ứng (st.tabs không cho chọn tab từ HTML tự viết),
# hoặc cuộn tới phần tử có id. Gắn lại sự kiện mỗi khi Streamlit vẽ lại trang.
CARD_NAVIGATION_JS = """
<script>
(function () {
  function go(card) {
    var target = card.getAttribute('data-target');
    if (!target) return;
    if (target.charAt(0) === '#') {
      var el = document.querySelector(target);
      if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
      return;
    }
    var tab = document.querySelectorAll('[data-testid="stTab"]')[parseInt(target, 10)];
    if (tab) { tab.click(); window.scrollTo({top: 0, behavior: 'smooth'}); }
  }
  function bind() {
    document.querySelectorAll('.qa-feature[data-target]').forEach(function (card) {
      if (card.dataset.bound) return;
      card.dataset.bound = '1';
      card.addEventListener('click', function () { go(card); });
      card.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(card); });
    });
  }
  bind();
  new MutationObserver(bind).observe(document.body, {childList: true, subtree: true});
})();
</script>
"""


def enable_card_navigation():
    """Nạp đoạn JavaScript cho phép bấm thẻ tính năng để chuyển tab."""
    st.html(CARD_NAVIGATION_JS, unsafe_allow_javascript=True)


def donut(passed: int, failed: int):
    """Biểu đồ tròn pass/fail bằng SVG trong một thẻ. Chu vi r=15.915 ≈ 100 nên độ dài nét = phần trăm."""
    total = passed + failed
    rate = round(passed * 100 / total, 1) if total else 0
    base = COLORS["fail"] if total else COLORS["border"]
    arc = (f'<circle cx="21" cy="21" r="15.915" fill="none" stroke="{COLORS["pass"]}" stroke-width="4" '
           f'stroke-dasharray="{rate} {100 - rate}" stroke-dashoffset="25"></circle>') if passed else ""
    html(f'<div class="qa-card qa-donut"><svg viewBox="0 0 42 42" width="168" height="168">'
         f'<circle cx="21" cy="21" r="15.915" fill="none" stroke="{base}" stroke-width="4"></circle>{arc}'
         f'<text class="rate" x="21" y="21.5" text-anchor="middle" font-size="7" font-weight="700">{rate:g}%</text>'
         f'<text class="cap" x="21" y="27" text-anchor="middle" font-size="2.9">tỷ lệ đạt</text></svg>'
         f'<div class="qa-legend"><span><i class="p"></i>Pass {passed}</span>'
         f'<span><i class="f"></i>Fail {failed}</span></div></div>')


# ---------------------------------------------------------------------------
# Tô màu bảng
# ---------------------------------------------------------------------------

def status_styler(df: pd.DataFrame, column: str, fail_rows: bool = True):
    """Tô màu chữ cột trạng thái; dòng lỗi có nền đỏ nhạt."""
    styler = df.style.map(lambda v: f"color: {STATUS_COLOR[v]}; font-weight: 600" if v in STATUS_COLOR else "",
                          subset=[column])
    if fail_rows:
        styler = styler.apply(lambda row: [f"background-color: {COLORS['fail_soft']}" if row[column] == "Lỗi"
                                           else "" for _ in row], axis=1)
    return styler


def note_styler(df: pd.DataFrame, column: str = "Loại"):
    """Tô nền dòng theo loại ghi chú (tự ghi nhận / cần xem lại) trong bảng xem trước kịch bản."""
    return df.style.apply(lambda row: [f"background-color: {NOTE_BACKGROUND[row[column]]}"
                                       if row[column] in NOTE_BACKGROUND else "" for _ in row], axis=1)


# ---------------------------------------------------------------------------
# Theme biểu đồ Altair dùng chung (gọi st.altair_chart(..., theme=None) để áp dụng)
# ---------------------------------------------------------------------------

@alt.theme.register("qa_dark", enable=True)
def chart_theme() -> alt.theme.ThemeConfig:
    axis = {"labelFontSize": 12, "labelColor": COLORS["text_2"], "titleFontSize": 13,
            "titleColor": COLORS["text_2"], "titleFontWeight": 500, "gridColor": COLORS["border"],
            "domain": False, "ticks": False, "labelPadding": 8, "titlePadding": 12,
            "labelFont": "Inter", "titleFont": "Inter"}
    return {"config": {
        "background": "transparent",
        "font": "Inter",
        "view": {"stroke": None},
        "axis": axis,
        "axisX": {"grid": False},
        "legend": {"labelFontSize": 13, "labelColor": COLORS["text_2"], "titleFontSize": 13,
                   "titleColor": COLORS["text_2"], "symbolType": "circle", "symbolSize": 80,
                   "labelFont": "Inter", "orient": "top"},
        "bar": {"cornerRadiusTopLeft": 4, "cornerRadiusTopRight": 4},
        "range": {"category": [COLORS["blue"], COLORS["pass"], COLORS["fail"], COLORS["warn"]]},
    }}
