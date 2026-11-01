"""
Giao diện web của công cụ, viết bằng Streamlit.

Chạy:  streamlit run app.py
Bố cục:
  - Thanh bên trái: cài đặt chung (trình duyệt, chạy ẩn, thời gian chờ) dùng cho mọi chức năng.
  - 5 tab:
      0. Tổng quan      : giới thiệu, lịch sử các lần chạy, xu hướng, so sánh hồi quy với lần chạy trước.
      1. Chạy kịch bản  : chọn file Excel, chạy và xem kết quả.
      2. Tạo kịch bản   : tự sinh file Excel bằng cách quét trang hoặc ghi lại thao tác.
      3. Kiểm tra nhanh : nhập URL, tự động kiểm tra link, ảnh, lỗi JS, chụp ảnh.
      4. Hướng dẫn      : cách viết file Excel và danh sách từ khóa.
Kiểu dáng: theme trong .streamlit/config.toml, CSS trong assets/style.css, khối giao diện dùng chung trong ui.py.
"""

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import altair as alt
import pandas as pd
import streamlit as st

import ui
from core.excel_report import EXCEL_REPORT_NAME, export_excel_report
from core.generator import (GENERATED_NOTES, TECHNIQUES, FormField, build_login_steps, count_form_cases,
                            crawl_site, form_signature, generate_cases, scan_page, setup_from_suite,
                            should_follow)
from core.history import compare_runs, find_previous, load_history, save_summary
from core.keywords import KEYWORD_DOCS
from core.reader import TestCase, TestStep, read_suite
from core.recorder import record
from core.reporter import generate_report, generate_smoke_report
from core.runner import PASS, SUPPORTED_BROWSERS, install_command, installed_browsers, run_suite, slugify
from core.smoke import smoke_check
from core.writer import write_cases

ROOT = Path(__file__).parent
REPORTS_DIR = ROOT / "reports"
TESTCASES_DIR = ROOT / "testcases"

STATUS_TEXT = {"PASS": "Đạt", "FAIL": "Lỗi", "SKIP": "Bỏ qua", "WARN": "Cảnh báo"}
STATUS_BADGE = {"PASS": ":green-badge[Đạt]", "FAIL": ":red-badge[Lỗi]", "SKIP": ":gray-badge[Bỏ qua]",
                "WARN": ":orange-badge[Cảnh báo]"}
BROWSER_NAMES = {"chromium": "Chromium (Chrome, Edge)", "firefox": "Firefox", "webkit": "WebKit (Safari)"}

st.set_page_config(page_title="Kiểm thử giao diện Web", page_icon=str(ui.LOGO_PNG), layout="wide")


# ===========================================================================
# TIỆN ÍCH DÙNG CHUNG
# ===========================================================================

def new_output_dir() -> Path:
    """Tạo thư mục báo cáo mới theo ngày giờ: reports/2024-05-01_10-30-00"""
    path = REPORTS_DIR / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


def relative(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def report_buttons(report_path: Path, key: str):
    """Nút tải báo cáo HTML và (nếu có) kết quả Excel, đặt cạnh nhau."""
    excel_path = report_path.parent / EXCEL_REPORT_NAME
    cols = st.columns([1, 1, 2] if excel_path.exists() else [1, 3])
    cols[0].download_button("Báo cáo HTML", data=report_path.read_bytes(), icon=":material/download:",
                            file_name=f"bao_cao_{report_path.parent.name}.html", mime="text/html",
                            key=f"{key}_html", type="primary", width="stretch")
    if excel_path.exists():
        cols[1].download_button("Kết quả Excel", data=excel_path.read_bytes(), icon=":material/table_view:",
                                file_name=f"ket_qua_{report_path.parent.name}.xlsx", key=f"{key}_excel",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                width="stretch")
    st.caption(f"Đã lưu tại `{relative(report_path.parent)}`")


@st.cache_data(ttl=60, show_spinner=False)
def browser_status() -> dict[str, bool]:
    """Trình duyệt nào đã được cài (kiểm tra lại sau mỗi 60 giây)."""
    try:
        return installed_browsers()
    except Exception:
        return {name: True for name in SUPPORTED_BROWSERS}  # Không kiểm tra được thì không chặn người dùng


def sidebar_last_run():
    """Tóm tắt lần chạy gần nhất ở thanh bên để xem nhanh từ bất kỳ tab nào."""
    ui.html('<div class="qa-side-title">Lần chạy gần nhất</div>')
    runs = load_history(REPORTS_DIR, limit=1)
    if not runs:
        st.caption("Chưa có lần chạy nào.")
        return
    run = runs[0]
    kind = "Kịch bản" if run["type"] == "suite" else "Kiểm tra nhanh"
    # Kiểm tra nhanh lưu tên là cả URL -> chỉ hiện tên miền cho gọn
    name = run["name"] if run["type"] == "suite" else (urlparse(run["name"]).netloc or run["name"])
    badge = ":green-badge[Đạt hết]" if run["failed"] == 0 else f":red-badge[{run['failed']} lỗi]"
    st.markdown(f"**{ui.md(name)}**  \n{badge} {run['passed']}/{run['total']} đạt · {run['pass_rate']}%")
    st.caption(f"{kind} · {run['browser']} · {run['start']:%H:%M %d/%m/%Y} · {run['duration']:.1f}s")


def sidebar_settings() -> dict:
    """Cài đặt chung ở thanh bên trái, dùng cho mọi tab."""
    status = browser_status()
    with st.sidebar:
        ui.html('<div class="qa-side-title">Cài đặt chạy</div>')
        browser = st.selectbox("Trình duyệt", SUPPORTED_BROWSERS,
                               format_func=lambda b: BROWSER_NAMES[b] + ("" if status.get(b) else " — chưa cài"))
        if not status.get(browser):
            st.warning(f"Chưa cài {BROWSER_NAMES[browser]}. Mở terminal và chạy:\n\n`{install_command(browser)}`",
                       icon=":material/download:")
        headless = st.toggle("Chạy ẩn (headless)", value=True,
                             help="Tắt để thấy cửa sổ trình duyệt mở ra và tự thao tác — phù hợp khi demo.")
        timeout = st.slider("Thời gian chờ mỗi thao tác (giây)", 3, 60, 10,
                            help="Quá thời gian này mà chưa thấy phần tử / điều kiện đúng thì bước bị tính là lỗi.")
        st.divider()
        sidebar_last_run()
        st.divider()
        st.caption("Kết quả mỗi lần chạy được lưu tại `reports/<ngày_giờ>/` gồm báo cáo HTML, "
                   "kết quả Excel và ảnh chụp màn hình.")
    return {"browser": browser, "headless": headless, "timeout": timeout}


def settings_hint(cfg: dict) -> str:
    mode = "chạy ẩn" if cfg["headless"] else "hiện trình duyệt"
    return f"{BROWSER_NAMES[cfg['browser']]} · {mode} · chờ tối đa {cfg['timeout']}s — đổi ở thanh bên trái"


# ===========================================================================
# TAB TỔNG QUAN: giới thiệu + lịch sử các lần chạy + so sánh hồi quy
# ===========================================================================

# (biểu tượng, tiêu đề, mô tả, vị trí, đích khi bấm: số thứ tự tab hoặc #id phần tử cần cuộn tới)
FEATURES = [
    ("play", "Chạy kịch bản Excel", f"Mỗi sheet là một test case, {len(KEYWORD_DOCS)} từ khóa, hỗ trợ data-driven.",
     "Tab Chạy kịch bản", "1"),
    ("sparkles", "Tự sinh kịch bản", "Quét trang và sinh test case theo kỹ thuật thiết kế test, hoặc ghi lại thao tác.",
     "Tab Tạo kịch bản", "2"),
    ("search", "Kiểm tra nhanh", "Chỉ cần URL: link hỏng, ảnh lỗi, lỗi JavaScript, ảnh chụp 3 kích thước.",
     "Tab Kiểm tra nhanh", "3"),
    ("chart", "Báo cáo & lịch sử", "Báo cáo HTML, kết quả Excel theo mẫu test case, so sánh với lần chạy trước.",
     "Ngay bên dưới", "#qa-history"),
]


def run_label(run: dict, index: int) -> str:
    return f"#{index} {run['start']:%H:%M %d/%m}"


def trend_chart(runs: list[dict]):
    """Biểu đồ cột chồng số test đạt / lỗi qua các lần chạy (cũ -> mới), dùng theme chung trong ui.py."""
    rows = []
    for i, run in enumerate(reversed(runs), start=1):
        label = run_label(run, i)
        rows += [{"Lần chạy": label, "Kết quả": "Đạt", "Số test": run["passed"], "Bộ test": run["name"]},
                 {"Lần chạy": label, "Kết quả": "Lỗi", "Số test": run["failed"], "Bộ test": run["name"]}]
    chart = alt.Chart(pd.DataFrame(rows)).mark_bar(size=28).encode(
        x=alt.X("Lần chạy:N", sort=None, title=None, axis=alt.Axis(labelAngle=0 if len(runs) <= 6 else -30)),
        y=alt.Y("Số test:Q", title="Số test case"),
        color=alt.Color("Kết quả:N", title=None,
                        scale=alt.Scale(domain=["Đạt", "Lỗi"], range=[ui.COLORS["pass"], ui.COLORS["fail"]])),
        tooltip=["Lần chạy", "Bộ test", "Kết quả", "Số test"],
    ).properties(height=280)
    st.altair_chart(chart, width="stretch", theme=None)


def regression_panel(runs: list[dict], latest: dict):
    """So sánh lần chạy mới nhất với lần chạy trước của cùng bộ test."""
    previous = find_previous(runs, latest)
    st.markdown(f"**{ui.md(latest['name'])}** · {latest['start']:%H:%M %d/%m/%Y}")
    if not previous:
        st.caption("Chưa có lần chạy trước của bộ test này để so sánh. Chạy lại bộ test để xem thay đổi.")
        st.metric("Tỷ lệ đạt", f"{latest['pass_rate']}%")
        return
    diff = compare_runs(latest, previous)
    delta = latest["pass_rate"] - previous["pass_rate"]
    since = f"so với {previous['start']:%H:%M %d/%m}"
    if delta:
        st.metric("Tỷ lệ đạt", f"{latest['pass_rate']}%", delta=f"{delta:+.1f}% {since}")
    else:
        st.metric("Tỷ lệ đạt", f"{latest['pass_rate']}%")
        st.caption(f"Không đổi {since}")
    groups = [("new_failures", ":red-badge[Lỗi mới]", "Trước đạt, nay lỗi — lỗi hồi quy cần kiểm tra"),
              ("fixed", ":green-badge[Đã sửa]", "Trước lỗi, nay đạt"),
              ("still_failing", ":orange-badge[Vẫn lỗi]", "Lỗi ở cả hai lần"),
              ("added", ":blue-badge[Mới thêm]", "Test case mới"),
              ("removed", ":gray-badge[Đã bỏ]", "Không còn trong bộ test")]
    shown = False
    for key, badge, hint in groups:
        if diff[key]:
            shown = True
            st.markdown(f"{badge} {ui.muted(hint)}", unsafe_allow_html=True)
            st.markdown("\n".join(f"- {ui.md(name)}" for name in diff[key][:8])
                        + (f"\n- … và {len(diff[key]) - 8} test khác" if len(diff[key]) > 8 else ""))
    if not shown:
        st.success("Kết quả giống hệt lần chạy trước.", icon=":material/check_circle:")


def tab_overview():
    ui.hero("Kiểm thử giao diện Web tự động",
            "Viết kịch bản bằng Excel (hoặc để công cụ tự sinh), chạy trên trình duyệt thật "
            "và nhận báo cáo chi tiết kèm ảnh chụp lỗi.", FEATURES)
    runs = load_history(REPORTS_DIR)
    suite_runs = [r for r in runs if r["type"] == "suite"]
    if not runs:
        with ui.card("empty_history"):
            st.markdown("**Chưa có lần chạy nào.** Bắt đầu nhanh trong 3 bước:\n"
                        "1. Sang tab **Chạy kịch bản**, chọn **File có sẵn trong testcases/** → `saucedemo.xlsx`\n"
                        "2. Bấm **Chạy kiểm thử** (khoảng 30 giây)\n"
                        "3. Quay lại đây để xem thống kê, xu hướng và so sánh giữa các lần chạy")
        return

    total_cases = sum(r["total"] for r in suite_runs)
    avg_rate = round(sum(r["pass_rate"] for r in suite_runs) / len(suite_runs), 1) if suite_runs else 0
    last = runs[0]
    ui.metrics([
        ("Số lần chạy", len(runs), ""),
        ("Test case đã chạy", total_cases, ""),
        ("Tỷ lệ đạt trung bình", f"{avg_rate}%", "pass" if avg_rate >= 90 else "warn"),
        ("Lần chạy gần nhất", f"{last['start']:%H:%M %d/%m}", ""),
    ])

    if suite_runs:
        chart_col, diff_col = st.columns([3, 2], gap="medium")
        with chart_col:
            ui.section("Xu hướng kết quả", f"{min(len(suite_runs), 15)} lần chạy kịch bản gần nhất")
            with ui.card("trend"):
                trend_chart(suite_runs[:15])
        with diff_col:
            ui.section("So với lần chạy trước", "kiểm thử hồi quy")
            with ui.card("regression"):
                regression_panel(runs, suite_runs[0])

    ui.section("Lần chạy gần đây", anchor="qa-history")
    table = pd.DataFrame([{
        "Thời gian": f"{r['start']:%H:%M:%S %d/%m/%Y}",
        "Loại": "Kịch bản" if r["type"] == "suite" else "Kiểm tra nhanh",
        "Tên": r["name"], "Kết quả": f"{r['passed']}/{r['total']}", "Tỷ lệ đạt": r["pass_rate"],
        "Thời gian chạy": f"{r['duration']:.1f}s", "Trình duyệt": r["browser"],
    } for r in runs[:20]])
    ui.table(table, column_config={
        "Tỷ lệ đạt": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)})
    pick_col, _ = st.columns([2, 3])
    picked = pick_col.selectbox("Tải lại báo cáo của lần chạy", range(len(runs[:20])),
                                format_func=lambda i: f"{runs[i]['start']:%H:%M:%S %d/%m} · {runs[i]['name']}",
                                key="history_pick")
    report = Path(runs[picked]["dir"]) / "report.html"
    if report.exists():
        report_buttons(report, key="history")


# ===========================================================================
# TAB 1: CHẠY KỊCH BẢN EXCEL
# ===========================================================================

def show_suite_result(result, report_path: Path):
    ui.section("Kết quả", f"bắt đầu lúc {result.start_time:%H:%M:%S %d/%m/%Y}")
    chart_col, stats_col = st.columns([1, 3], gap="medium")
    with chart_col:
        ui.donut(result.passed, result.failed)
    with stats_col:
        ui.metrics([
            ("Tổng số test", result.total, ""),
            ("Đạt (Pass)", result.passed, "pass"),
            ("Lỗi (Fail)", result.failed, "fail" if result.failed else ""),
            ("Tỷ lệ đạt", f"{result.pass_rate}%", "pass" if result.failed == 0 else "warn"),
            ("Tổng thời gian", f"{result.duration:.1f}s", ""),
            ("Trình duyệt", result.browser, "text"),
        ])
        report_buttons(report_path, key="suite")

    ui.section("Chi tiết từng test case", "bấm vào để xem các bước")
    for case in result.cases:
        label = f"{STATUS_BADGE[case.status]} **{ui.md(case.name)}** · {case.duration:.2f}s"
        with st.expander(label, expanded=case.status != PASS):
            if case.error:
                st.error(ui.md(case.error), icon=":material/error:")
            if case.data_row:
                ui.chips([f"{k} = {v or '(trống)'}" for k, v in case.data_row.items()])
            steps = pd.DataFrame([{
                "Bước": s.step_no, "Từ khóa": s.keyword, "Selector": s.selector, "Giá trị": s.value,
                "Mô tả": s.description, "Kết quả": STATUS_TEXT[s.status],
                "Thời gian (s)": f"{s.duration:.2f}" if s.status != "SKIP" else "",
            } for s in case.steps])
            ui.table(ui.status_styler(steps, "Kết quả"))
            for s in case.steps:
                if s.screenshot:
                    st.image(s.screenshot, caption=f"Ảnh chụp bước {s.step_no}", width=640)


def choose_excel_file() -> Path | None:
    """Chọn file Excel: tải lên hoặc chọn file có sẵn trong thư mục testcases/."""
    source = st.segmented_control("Nguồn kịch bản", ["Tải file lên", "File có sẵn trong testcases/"],
                                  default="Tải file lên", label_visibility="collapsed", key="run_source")
    if source == "File có sẵn trong testcases/":
        samples = sorted(TESTCASES_DIR.glob("*.xlsx"))
        if not samples:
            st.warning("Chưa có file. Hãy chạy `python testcases/tao_file_mau.py` hoặc dùng tab Tạo kịch bản.")
            return None
        return st.selectbox("Chọn file", samples, format_func=lambda p: p.name, label_visibility="collapsed")

    upload_col, help_col = st.columns([3, 2], gap="medium")
    uploaded = upload_col.file_uploader("Chọn file Excel (.xlsx) — mỗi sheet là một test case", type=["xlsx"])
    with help_col:
        with ui.card("upload_help"):
            st.markdown("**Chưa có kịch bản?**\n"
                        "- Tải file mẫu bên dưới, sửa theo trang web của bạn\n"
                        "- Hoặc chọn **File có sẵn trong testcases/** để chạy thử ngay\n"
                        "- Hoặc sang tab **Tạo kịch bản** để công cụ tự sinh từ URL")
            sample = TESTCASES_DIR / "saucedemo.xlsx"
            if sample.exists():
                st.download_button("Tải file mẫu", data=sample.read_bytes(), file_name=sample.name,
                                   icon=":material/download:", key="run_sample")
    if not uploaded:
        return None
    upload_dir = REPORTS_DIR / "_uploads"  # Lưu file tải lên để openpyxl đọc
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / uploaded.name
    path.write_bytes(uploaded.getvalue())
    return path


def tab_run_excel(cfg: dict):
    ui.section("Chọn kịch bản", number=1)
    excel_path = choose_excel_file()
    if excel_path:
        try:
            suite = read_suite(excel_path)
        except Exception as exc:
            st.error(f"Không đọc được file Excel: {exc}")
            return
        info = [("Bộ test", suite.name), ("Số test case", len(suite.cases)),
                ("Tổng số bước", sum(len(c.steps) for c in suite.cases))]
        if suite.data:
            info.append(("Data-driven", f"{len(suite.data)} bộ dữ liệu"))
        ui.info_bar(info)
        with st.expander("Xem trước danh sách test case"):
            ui.table(pd.DataFrame([{"#": i, "Test case": c.name, "Số bước": len(c.steps)}
                                   for i, c in enumerate(suite.cases, 1)]))

        ui.section("Chạy kiểm thử", settings_hint(cfg), number=2)
        if st.button("Chạy kiểm thử", type="primary", icon=":material/play_arrow:", width="stretch"):
            output_dir = new_output_dir()
            progress = st.progress(0.0, text="Đang khởi động trình duyệt...")
            live = st.empty()  # Nhật ký tạm thời trong lúc chạy, xóa đi khi xong để không lặp với phần kết quả
            lines = []

            def on_progress(done, total, case_result):
                progress.progress(done / total, text=f"Đã chạy {done}/{total} test case")
                lines.append(f"{STATUS_BADGE[case_result.status]} {ui.md(case_result.name)} · "
                             f"{case_result.duration:.2f}s")
                live.container(border=True).markdown("  \n".join(lines[-8:]))

            try:
                result = run_suite(suite, output_dir, browser_name=cfg["browser"], headless=cfg["headless"],
                                   timeout_ms=cfg["timeout"] * 1000, on_progress=on_progress)
            except Exception as exc:
                st.error(f"Lỗi khi chạy: {exc}")
                st.info("Nếu lỗi do chưa cài trình duyệt, hãy chạy: `python -m playwright install`")
                return
            progress.empty()
            live.empty()
            report_path = generate_report(result, output_dir)
            export_excel_report(result, output_dir)
            save_summary(result, output_dir)
            # Lưu vào session_state để kết quả không mất khi Streamlit chạy lại script,
            # rồi chạy lại để tab Tổng quan cập nhật lần chạy mới
            st.session_state["suite_result"] = (result, report_path)
            st.rerun()

    if "suite_result" in st.session_state:
        show_suite_result(*st.session_state["suite_result"])


# ===========================================================================
# TAB 2: TẠO KỊCH BẢN TỰ ĐỘNG (quét trang hoặc ghi lại thao tác)
# ===========================================================================

NOTE_TEXT = {"auto": "Tự ghi nhận", "review": "Cần xem lại", "": ""}
STEP_COLUMNS = ["Bước", "Từ khóa", "Selector", "Giá trị", "Mô tả"]


def steps_to_df(steps: list[TestStep]) -> pd.DataFrame:
    return pd.DataFrame([{"Bước": s.step_no, "Từ khóa": s.keyword, "Selector": s.selector,
                          "Giá trị": s.value, "Mô tả": s.description} for s in steps], columns=STEP_COLUMNS)


def df_to_steps(df: pd.DataFrame) -> list[TestStep]:
    """Chuyển bảng (sau khi người dùng sửa) về danh sách bước, bỏ dòng không có từ khóa."""
    steps = []
    for _, row in df.iterrows():
        keyword = str(row["Từ khóa"] or "").strip()
        if keyword and keyword != "None":
            text = lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
            steps.append(TestStep(len(steps) + 1, keyword, text(row["Selector"]), text(row["Giá trị"]),
                                  text(row["Mô tả"])))
    return steps


def preview_cases(cases: list[TestCase]):
    """Tóm tắt các test case vừa sinh. Dòng tự ghi nhận tô vàng, dòng cần xem lại tô cam."""
    need_review = sum(any(s.note == "review" for s in c.steps) for c in cases)
    ui.metrics([("Test case đã sinh", len(cases), ""),
                ("Sẵn sàng chạy", len(cases) - need_review, "pass"),
                ("Cần xem lại", need_review, "warn" if need_review else "")])
    summary = pd.DataFrame([{
        "Test case": c.name, "Số bước": len(c.steps),
        "Kết quả mong đợi": c.steps[-1].description if c.steps else "",
        "Trạng thái": "Cần xem lại" if any(s.note == "review" for s in c.steps) else "Sẵn sàng",
    } for c in cases])
    ui.table(ui.status_styler(summary, "Trạng thái", fail_rows=False))
    with st.expander("Xem chi tiết các bước (vàng = tự ghi nhận, cam = cần xem lại)"):
        for c in cases:
            st.markdown(f"**{ui.md(c.name)}**")
            df = steps_to_df(c.steps)
            df["Loại"] = [NOTE_TEXT.get(s.note, "") for s in c.steps]
            ui.table(ui.note_styler(df))


def save_cases_ui(cases: list[TestCase], notes: list[str] | None, default_name: str, key: str):
    """Đặt tên file, lưu vào thư mục testcases/ và cho tải về."""
    col1, col2 = st.columns([3, 1], vertical_alignment="bottom")
    name = col1.text_input("Tên file Excel", value=default_name, key=f"{key}_name")
    if col2.button("Lưu file Excel", type="primary", icon=":material/save:", key=f"{key}_save", width="stretch"):
        path = write_cases(TESTCASES_DIR / (slugify(name) + ".xlsx"), cases, notes)
        st.session_state[f"{key}_saved"] = path
    saved = st.session_state.get(f"{key}_saved")
    if saved and Path(saved).exists():
        st.success(f"Đã lưu `{relative(saved)}`. Sang tab **Chạy kịch bản** → **File có sẵn trong testcases/** "
                   "để chạy ngay.", icon=":material/check_circle:")
        st.download_button("Tải file Excel về máy", data=Path(saved).read_bytes(), file_name=Path(saved).name,
                           icon=":material/download:", key=f"{key}_download")


def field_limits(f: FormField) -> str:
    parts = []
    if f.maxlength:
        parts.append(f"tối đa {f.maxlength} ký tự")
    if f.minlength:
        parts.append(f"tối thiểu {f.minlength} ký tự")
    if f.min:
        parts.append(f"min {f.min}")
    if f.max:
        parts.append(f"max {f.max}")
    return ", ".join(parts)


LOGIN_MODES = ["Không cần", "Bằng tài khoản", "Bằng kịch bản có sẵn"]


def login_options(url: str) -> dict:
    """Mục 'Đăng nhập trước khi quét': chọn cách đăng nhập và nhập thông tin tương ứng."""
    with st.expander("Đăng nhập trước khi quét (cho trang yêu cầu đăng nhập)",
                     expanded=st.session_state.get("gen_login_mode", "Không cần") != "Không cần"):
        mode = st.segmented_control("Cách đăng nhập", LOGIN_MODES, default="Không cần", key="gen_login_mode",
                                    label_visibility="collapsed") or "Không cần"
        if mode == "Bằng tài khoản":
            st.caption("Công cụ tự tìm form đăng nhập (ô mật khẩu, ô tên đăng nhập, nút gửi) và thử đăng nhập trước. "
                       "Mật khẩu được ghi vào file Excel để test case tự đăng nhập — chỉ dùng tài khoản thử nghiệm.")
            c1, c2, c3 = st.columns([2, 1, 1])
            login_url = c1.text_input("URL trang đăng nhập", placeholder=url or "để trống = dùng URL ở trên",
                                      key="gen_login_url")
            username = c2.text_input("Tên đăng nhập", key="gen_login_user")
            password = c3.text_input("Mật khẩu", type="password", key="gen_login_pass")
            return {"mode": mode, "login_url": login_url.strip() or url.strip(), "username": username,
                    "password": password}
        if mode == "Bằng kịch bản có sẵn":
            st.caption("Chọn một test case (VD: kịch bản đăng nhập đã ghi lại) để chạy trước khi quét.")
            files = sorted(TESTCASES_DIR.glob("*.xlsx"))
            if not files:
                st.warning("Chưa có file kịch bản trong testcases/.")
                return {"mode": "Không cần"}
            c1, c2 = st.columns(2)
            file = c1.selectbox("File kịch bản", files, format_func=lambda p: p.name, key="gen_setup_file")
            try:
                names = [c.name for c in read_suite(file).cases]
            except Exception as exc:
                st.error(f"Không đọc được file: {exc}")
                return {"mode": "Không cần"}
            case = c2.selectbox("Test case dùng làm bước chuẩn bị", names, key="gen_setup_case")
            return {"mode": mode, "file": file, "case": case}
    return {"mode": "Không cần"}


def build_setup(login: dict, cfg: dict) -> list[TestStep]:
    """Tạo các bước chuẩn bị theo lựa chọn đăng nhập (ném lỗi nếu đăng nhập thử thất bại)."""
    if login["mode"] == "Bằng tài khoản":
        if not login["username"] or not login["password"]:
            raise ValueError("Vui lòng nhập tên đăng nhập và mật khẩu")
        with st.spinner("Đang thử đăng nhập..."):
            return build_login_steps(login["login_url"], login["username"], login["password"],
                                     browser_name=cfg["browser"])
    if login["mode"] == "Bằng kịch bản có sẵn":
        return setup_from_suite(login["file"], login["case"])
    return []


def scope_options() -> dict:
    """Mục 'Phạm vi quét': chỉ trang này hoặc nhiều trang (đi theo link cùng website)."""
    with st.expander("Phạm vi quét", expanded=st.session_state.get("gen_scope", "Chỉ trang này") != "Chỉ trang này"):
        scope = st.segmented_control("Phạm vi", ["Chỉ trang này", "Nhiều trang (đi theo link)"],
                                     default="Chỉ trang này", key="gen_scope",
                                     label_visibility="collapsed") or "Chỉ trang này"
        if scope == "Chỉ trang này":
            return {"multi": False}
        st.caption("Công cụ đi theo các link cùng website (bỏ qua link đăng xuất, xóa, tải file, website khác). "
                   "Các trang cùng khuôn mẫu (VD: /product/123, /product/456) chỉ quét một trang đại diện.")
        c1, c2 = st.columns([1, 2])
        max_pages = c1.slider("Số trang tối đa", 2, 20, 8, key="gen_max_pages")
        extra = c2.text_area("Thêm URL cần quét (mỗi dòng một URL)", height=96, key="gen_extra_urls",
                             placeholder="Dùng cho trang chỉ mở được bằng nút bấm, VD:\n"
                                         "https://www.saucedemo.com/cart.html")
        return {"multi": True, "max_pages": max_pages,
                "extra_urls": [u.strip() for u in extra.splitlines() if u.strip()]}


def run_scan(url: str, login: dict, scope: dict, cfg: dict) -> list:
    """Chạy bước chuẩn bị (nếu có) rồi quét một hoặc nhiều trang. Trả về danh sách PageScan."""
    setup = build_setup(login, cfg)
    if not scope["multi"]:
        with st.spinner("Đang mở và phân tích trang..."):
            return [scan_page(url, browser_name=cfg["browser"], setup=setup)]
    progress = st.progress(0.0, text="Đang quét...")

    def on_progress(done, total, current):
        progress.progress(min(done / total, 1.0) if total else 1.0, text=f"Đã quét {done}/{total} trang · {current}")

    scans = crawl_site(url, browser_name=cfg["browser"], setup=setup, max_pages=scope["max_pages"],
                       extra_urls=scope["extra_urls"], on_progress=on_progress)
    progress.empty()
    return scans


def page_label(p: int, scan) -> str:
    path = urlparse(scan.url).path or "/"
    return f"P{p} · {ui.md(scan.title or path)} — `{path}`"


def form_editor(form, key: str):
    """Bảng ô nhập của form, cho sửa cột Giá trị hợp lệ."""
    st.caption("Sửa cột **Giá trị hợp lệ** cho đúng với trang (VD: tài khoản đăng nhập thật). Các test "
               "case không hợp lệ chỉ thay đổi một ô, các ô còn lại dùng giá trị này.")
    df = pd.DataFrame([{"Ô nhập": f.label, "Selector": f.selector, "Loại": f.type,
                        "Bắt buộc": "✔" if f.required else "", "Ràng buộc": field_limits(f),
                        "Giá trị hợp lệ": f.valid_value} for f in form.fields])
    edited = st.data_editor(df, key=key, hide_index=True, width="stretch", row_height=44,
                            disabled=["Ô nhập", "Selector", "Loại", "Bắt buộc", "Ràng buộc"],
                            column_config={"Giá trị hợp lệ": st.column_config.TextColumn(help="Bấm đúp vào ô để sửa")})
    for f, value in zip(form.fields, edited["Giá trị hợp lệ"]):
        f.valid_value = "" if value is None else str(value)


def page_selection(p: int, scan, seen: dict) -> dict:
    """
    Các lựa chọn cho một trang. seen ghi nhớ thành phần đã gặp ở trang trước:
    thành phần lặp lại (thanh menu, ô tìm kiếm ở đầu mọi trang) mặc định không chọn để tránh test trùng.
    """
    chosen = {"scan": scan, "forms": [], "selects": [], "links": [], "controls": []}
    chosen["page_check"] = st.checkbox("Hiển thị trang — tiêu đề, các ô nhập, nút bấm", value=True,
                                       key=f"gen_p{p}_page")
    for i, form in enumerate(scan.forms):
        sig = form_signature(form)
        first_page = seen["forms"].setdefault(sig, p)
        repeat = f" · giống form ở P{first_page}" if first_page != p else ""
        with ui.card(f"p{p}_form_{i}"):
            label = (f"**Form {ui.md(form.title)}** — {len(form.fields)} ô nhập, "
                     f"nút gửi: {ui.md(form.submit_label) or 'nhấn Enter'}{repeat}")
            if st.checkbox(label, value=not repeat, key=f"gen_p{p}_form_{i}"):
                form_editor(form, key=f"gen_p{p}_form_edit_{i}")
                chosen["forms"].append(form)
    for i, s in enumerate(scan.selects):
        first_page = seen["selects"].setdefault(s.selector, p)
        repeat = f" · giống ở P{first_page}" if first_page != p else ""
        if st.checkbox(f"Dropdown **{ui.md(s.label)}** — {len(s.options)} lựa chọn{repeat}", value=not repeat,
                       key=f"gen_p{p}_select_{i}"):
            chosen["selects"].append(s)
    if scan.links:
        host = urlparse(scan.url).netloc
        default = []
        for i, link in enumerate(scan.links):
            # Mặc định chỉ chọn link cùng website, bỏ link đăng xuất / xóa / tải file và link đã gặp ở trang trước
            if should_follow(link.href, link.text, host) and link.href not in seen["links"] and len(default) < 5:
                default.append(i)
            seen["links"].add(link.href)
        picked = st.multiselect(f"Link điều hướng cần kiểm tra ({len(scan.links)} link trên trang)",
                                options=list(range(len(scan.links))), default=default,
                                format_func=lambda i: f"{scan.links[i].text}  →  {scan.links[i].href}",
                                key=f"gen_p{p}_links")
        chosen["links"] = [scan.links[i] for i in picked]
    if scan.controls:
        default = []
        for i, control in enumerate(scan.controls):
            if control.label not in seen["controls"] and len(default) < 8:
                default.append(i)
            seen["controls"].add(control.label)
        picked = st.multiselect(f"Nút bấm & điều khiển ({len(scan.controls)} trên trang) — công cụ bấm thử và ghi "
                                "nhận kết quả, kèm kiểm tra không phát sinh lỗi JavaScript",
                                options=list(range(len(scan.controls))), default=default,
                                format_func=lambda i: f"{scan.controls[i].kind_text}: {scan.controls[i].label}",
                                key=f"gen_p{p}_controls")
        chosen["controls"] = [scan.controls[i] for i in picked]
    return chosen


def section_generate(cfg: dict):
    st.caption("Công cụ quét trang tìm form, link, dropdown, nút bấm → bạn chọn phần muốn kiểm thử → công cụ tự "
               "sinh test case theo các kỹ thuật thiết kế test và chạy thử để ghi nhận kết quả mong đợi.")
    col1, col2 = st.columns([4, 1], vertical_alignment="bottom")
    url = col1.text_input("URL trang cần kiểm thử", placeholder="https://www.saucedemo.com", key="gen_url")
    scan_clicked = col2.button("Quét trang", type="primary", icon=":material/search:", key="gen_scan", width="stretch")
    login = login_options(url)
    scope = scope_options()

    if scan_clicked:
        if not url.strip():
            st.warning("Vui lòng nhập URL")
            return
        try:
            st.session_state["scans"] = run_scan(url.strip(), login, scope, cfg)
        except Exception as exc:
            st.error(f"Không quét được trang: {ui.md(exc)}", icon=":material/error:")
            return
        for k in ("gen_cases", "gen_saved"):
            st.session_state.pop(k, None)

    scans = st.session_state.get("scans")
    if not scans:
        return
    if scans[0].setup:
        with st.expander(f"Đã chạy {len(scans[0].setup)} bước chuẩn bị (đăng nhập) — các bước này được thêm vào "
                         "đầu mọi test case sinh ra"):
            ui.table(steps_to_df(scans[0].setup))
    for scan in scans:
        if scan.redirected:
            st.warning(f"`{scan.url}` bị chuyển hướng tới `{scan.final_url}` — có thể trang yêu cầu đăng nhập. "
                       "Hãy dùng mục **Đăng nhập trước khi quét** rồi quét lại.", icon=":material/warning:")
    ui.info_bar([("Số trang", len(scans)), ("Form", sum(len(s.forms) for s in scans)),
                 ("Link", sum(len(s.links) for s in scans)), ("Dropdown", sum(len(s.selects) for s in scans)),
                 ("Nút & điều khiển", sum(len(s.controls) for s in scans))])

    # ----- Bước 1: chọn phần muốn kiểm thử, từng trang -----
    ui.section("Chọn phần muốn kiểm thử", "thành phần lặp lại ở nhiều trang được bỏ chọn sẵn" if len(scans) > 1
               else "", number=1)
    seen = {"forms": {}, "selects": {}, "links": set(), "controls": set()}
    selections = []
    for p, scan in enumerate(scans, start=1):
        if len(scans) == 1:
            selections.append(page_selection(p, scan, seen))
        else:
            with st.expander(page_label(p, scan), expanded=p == 1):
                selections.append(page_selection(p, scan, seen))

    # ----- Bước 2: chọn kỹ thuật thiết kế test -----
    any_form = any(sel["forms"] for sel in selections)
    techniques = set()
    if any_form:
        ui.section("Chọn kỹ thuật thiết kế test cho form", number=2)
        techniques = set(st.pills("Kỹ thuật", options=list(TECHNIQUES), format_func=TECHNIQUES.get,
                                  selection_mode="multi", default=list(TECHNIQUES), key="gen_techs",
                                  label_visibility="collapsed") or [])
    observe = st.toggle("Chạy thử để tự ghi nhận kết quả mong đợi (khuyến nghị)", value=True, key="gen_observe",
                        help="Công cụ chạy từng test case của form và ghi lại điều xảy ra (chuyển trang, "
                             "thông báo lỗi, trình duyệt chặn gửi...). Tắt đi thì bạn phải tự điền kết quả.")

    total = sum(int(sel["page_check"]) + sum(count_form_cases(f, techniques) for f in sel["forms"])
                + len(sel["links"]) + len(sel["selects"]) + len(sel["controls"]) for sel in selections)

    # ----- Bước 3: sinh -----
    ui.section("Sinh kịch bản", number=3 if any_form else 2)
    if st.button(f"Sinh {total} test case", type="primary", icon=":material/auto_awesome:",
                 disabled=total == 0, key="gen_run"):
        progress = st.progress(0.0, text="Đang chuẩn bị...")
        cases = []
        try:
            for p, sel in enumerate(selections, start=1):
                def on_progress(done, all_jobs, name, p=p):
                    progress.progress((p - 1 + (done / all_jobs if all_jobs else 1.0)) / len(selections),
                                      text=f"Trang {p}/{len(selections)} · đang chạy thử {done}/{all_jobs}: {name}")

                cases += generate_cases(sel["scan"], sel["forms"], techniques, links=sel["links"],
                                        selects=sel["selects"], controls=sel["controls"],
                                        include_page_check=sel["page_check"],
                                        observe=observe, browser_name=cfg["browser"], on_progress=on_progress,
                                        name_prefix=f"P{p} " if len(selections) > 1 else "")
        except Exception as exc:
            st.error(f"Lỗi khi sinh kịch bản: {ui.md(exc)}")
            return
        progress.empty()
        st.session_state["gen_cases"] = cases
        st.session_state.pop("gen_saved", None)

    cases = st.session_state.get("gen_cases")
    if cases:
        preview_cases(cases)
        save_cases_ui(cases, GENERATED_NOTES, "tu_sinh_" + slugify(urlparse(scans[0].url).netloc or "trang"),
                      key="gen")


def section_record(cfg: dict):
    with ui.card("record_help"):
        st.markdown(
            "**Cách dùng:** bấm **Bắt đầu ghi** → cửa sổ trình duyệt mở ra → thao tác như người dùng bình thường. "
            "Mỗi cú click, mỗi lần nhập chữ được ghi thành một bước.  \n"
            "Thanh công cụ ở **góc dưới bên phải** trình duyệt dùng để thêm bước kiểm tra: "
            "**Kiểm tra chữ** / **Kiểm tra hiển thị** (rồi bấm vào phần tử), **Kiểm tra URL**, "
            "và **Dừng ghi** khi xong (hoặc đóng trình duyệt).")
    recorded: list[TestCase] = st.session_state.setdefault("recorded", [])
    col1, col2, col3 = st.columns([3, 2, 1], vertical_alignment="bottom")
    url = col1.text_input("URL bắt đầu", placeholder="https://www.saucedemo.com", key="rec_url")
    case_name = col2.text_input("Tên test case", value=f"Ghi lại {len(recorded) + 1}", key=f"rec_case_{len(recorded)}")
    start = col3.button("Bắt đầu ghi", type="primary", icon=":material/fiber_manual_record:", key="rec_start",
                        width="stretch")
    st.caption("Ghi thao tác bằng Google Chrome trên máy (không có Chrome thì dùng Chromium). "
               "Cửa sổ trình duyệt luôn hiện ra để bạn thao tác.")

    if start:
        if not url.strip():
            st.warning("Vui lòng nhập URL")
        else:
            live = st.status("Đang ghi... hãy thao tác trên cửa sổ trình duyệt vừa mở", expanded=True)
            try:
                steps = record(url.strip(), browser_name="chromium", on_step=lambda s: live.write(
                    f"`{s.keyword}` {ui.md(s.selector)} {('→ ' + ui.md(s.value)) if s.value else ''}"))
            except Exception as exc:
                live.update(label="Có lỗi xảy ra", state="error")
                st.error(f"Lỗi khi ghi: {exc}")
                return
            live.update(label=f"Đã ghi {len(steps)} bước", state="complete", expanded=False)
            recorded.append(TestCase(name=case_name, steps=steps))
            st.session_state.pop("rec_saved", None)

    if not recorded:
        return
    ui.section("Các test case đã ghi", "sửa trực tiếp trong bảng: đổi giá trị, xóa dòng, thêm dòng ở cuối bảng")
    final_cases = []
    for i, case in enumerate(recorded):
        with st.expander(f"**{ui.md(case.name)}** · {len(case.steps)} bước", expanded=i == len(recorded) - 1):
            # Bảng gốc giữ nguyên trong session, bản đã sửa chỉ dùng khi lưu (tránh áp dụng sửa đổi 2 lần)
            edited = st.data_editor(
                steps_to_df(case.steps), key=f"rec_edit_{i}", num_rows="dynamic", hide_index=True, width="stretch",
                row_height=44,
                column_config={"Từ khóa": st.column_config.SelectboxColumn(options=list(KEYWORD_DOCS), required=True),
                               "Bước": st.column_config.NumberColumn(disabled=True)})
            final_cases.append(TestCase(name=case.name, steps=df_to_steps(edited)))
            if st.button("Xóa test case này", icon=":material/delete:", key=f"rec_del_{i}"):
                recorded.pop(i)
                st.rerun()
    save_cases_ui(final_cases, None, "ghi_lai_thao_tac", key="rec")


def tab_create(cfg: dict):
    mode = st.segmented_control("Cách tạo kịch bản", ["Quét trang & tự sinh test case", "Ghi lại thao tác"],
                                default="Quét trang & tự sinh test case", label_visibility="collapsed",
                                key="create_mode")
    if mode == "Ghi lại thao tác":
        section_record(cfg)
    else:
        section_generate(cfg)


# ===========================================================================
# TAB 3: KIỂM TRA NHANH BẰNG LINK
# ===========================================================================

def show_smoke_result(result, report_path: Path):
    tone = result.overall.lower()
    ui.verdict(tone, {"pass": "Trang đạt yêu cầu", "fail": "Phát hiện lỗi", "warn": "Đạt, có cảnh báo"}[tone])
    if result.title:
        st.caption(f"Tiêu đề trang: {ui.md(result.title)} · kiểm tra trong {result.duration:.1f}s")

    ui.metrics([
        ("Thời gian tải", f"{result.load_time:.2f}s", "pass" if result.load_time <= 3 else "warn"),
        ("Link lỗi", f"{len(result.broken_links)}/{len(result.links)}", "fail" if result.broken_links else "pass"),
        ("Ảnh lỗi", f"{len(result.broken_images)}/{len(result.images)}", "fail" if result.broken_images else "pass"),
        ("Ảnh thiếu alt", len(result.images_missing_alt), "warn" if result.images_missing_alt else "pass"),
        ("Lỗi JavaScript", len(result.console_errors), "fail" if result.console_errors else "pass"),
    ])
    checks = pd.DataFrame([{"Hạng mục": c["name"], "Kết quả": STATUS_TEXT[c["status"]], "Chi tiết": c["detail"]}
                           for c in result.checks])
    ui.table(ui.status_styler(checks, "Kết quả", fail_rows=False))
    report_buttons(report_path, key="smoke")

    if result.screenshots:
        ui.section("Ảnh chụp ở các kích thước màn hình")
        cols = st.columns([1, 1.6, 2.4], gap="medium")
        for i, (col, (name, path)) in enumerate(zip(cols, result.screenshots.items())):
            with col:
                with ui.card(f"shot_{i}"):
                    st.markdown(f"**{name}**")
                    if path:
                        st.image(path, width="stretch")
                    else:
                        st.warning("Không chụp được ảnh")

    ui.section("Chi tiết")
    with st.expander(f"Link lỗi ({len(result.broken_links)})", expanded=bool(result.broken_links)):
        if result.broken_links:
            ui.table(pd.DataFrame([{"URL": l.url, "Mã HTTP": l.status, "Lỗi": l.error} for l in result.broken_links]))
        else:
            st.success(f"Tất cả {len(result.links)} link đều hoạt động.")
        if result.links_total_found > len(result.links):
            st.caption(f"Đã kiểm tra {len(result.links)}/{result.links_total_found} link tìm thấy.")

    with st.expander(f"Ảnh ({len(result.images)})", expanded=bool(result.broken_images)):
        if result.images:
            images = pd.DataFrame([{
                "Nguồn ảnh": i.src,
                "Alt": "Thiếu alt" if i.alt is None else (i.alt or "(rỗng - ảnh trang trí)"),
                "Kết quả": "Lỗi" if i.broken else "Đạt", "Lý do": i.reason,
            } for i in result.images])
            ui.table(ui.status_styler(images, "Kết quả"))
        else:
            st.info("Trang không có ảnh nào.")

    with st.expander(f"Lỗi JavaScript ({len(result.console_errors)})", expanded=bool(result.console_errors)):
        if result.console_errors:
            ui.table(pd.DataFrame({"#": range(1, len(result.console_errors) + 1),
                                   "Thông báo lỗi": result.console_errors}))
        else:
            st.success("Không có lỗi JavaScript nào.")


def tab_smoke(cfg: dict):
    st.caption("Chỉ cần nhập địa chỉ trang web: công cụ tự kiểm tra tải trang, link hỏng, ảnh lỗi / thiếu alt, "
               "lỗi JavaScript và chụp ảnh ở 3 kích thước màn hình (điện thoại, tablet, máy tính).")
    col1, col2 = st.columns([4, 1], vertical_alignment="bottom")
    url = col1.text_input("URL cần kiểm tra", placeholder="https://www.saucedemo.com", key="smoke_url")
    run = col2.button("Kiểm tra", type="primary", icon=":material/travel_explore:", width="stretch", key="smoke_run")
    with st.expander("Tùy chọn"):
        max_links = st.slider("Số link tối đa cần kiểm tra", 10, 300, 100, step=10)

    if run:
        if not url.strip():
            st.warning("Vui lòng nhập URL")
        else:
            output_dir = new_output_dir()
            error = None
            with st.status("Đang kiểm tra...", expanded=True) as status:
                try:
                    result = smoke_check(url.strip(), output_dir, browser_name=cfg["browser"],
                                         headless=cfg["headless"], max_links=max_links, on_progress=st.write)
                except Exception as exc:
                    error = exc
                    status.update(label="Có lỗi xảy ra", state="error", expanded=False)
                else:
                    status.update(label=f"Hoàn tất sau {result.duration:.1f}s", state="complete", expanded=False)
            if error:
                # Hiện lỗi bên ngoài khung trạng thái để người dùng thấy ngay (khung đã thu gọn)
                st.error(f"Lỗi khi kiểm tra: {ui.md(error)}", icon=":material/error:")
                return
            report_path = generate_smoke_report(result, output_dir)
            save_summary(result, output_dir)
            st.session_state["smoke_result"] = (result, report_path)
            st.rerun()

    if "smoke_result" in st.session_state:
        show_smoke_result(*st.session_state["smoke_result"])


# ===========================================================================
# TAB 4: HƯỚNG DẪN
# ===========================================================================

def tab_guide():
    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("""
#### Cấu trúc file Excel
- **Mỗi file** là một bộ test, **mỗi sheet** là một test case (tên sheet = tên test case).
- Dòng đầu của sheet là tiêu đề 5 cột: **Bước · Từ khóa · Selector · Giá trị · Mô tả**.

| Bước | Từ khóa | Selector | Giá trị |
|---|---|---|---|
| 1 | open | | https://www.saucedemo.com |
| 2 | type | #user-name | standard_user |
| 3 | type | #password | secret_sauce |
| 4 | click | #login-button | |
| 5 | assert_text | .title | Products |

#### Cách viết Selector
| Kiểu | Ví dụ |
|---|---|
| Theo id | `#login-button` |
| Theo class | `.inventory_item` |
| Theo thuộc tính | `[data-test="error"]` |
| Theo chữ hiển thị | `text=Add to cart` |

Nếu selector khớp nhiều phần tử, công cụ dùng phần tử **đầu tiên**.
""")
    with col2:
        st.markdown("""
#### Data-driven (kiểm thử hướng dữ liệu)
- Thêm sheet tên **`DATA`**: dòng đầu là tên biến, mỗi dòng sau là một bộ dữ liệu.
- Trong kịch bản viết `${ten_bien}` ở cột Selector / Giá trị.
- Mỗi dòng DATA chạy thành **một lần test riêng**; cột đầu tiên dùng làm nhãn.

| truong_hop | username | password |
|---|---|---|
| Tài khoản đúng | standard_user | secret_sauce |
| Tài khoản bị khóa | locked_out_user | secret_sauce |

#### Không muốn viết Excel bằng tay?
Dùng tab **Tạo kịch bản**:
- **Quét trang & tự sinh**: chọn form/link/dropdown/nút bấm và kỹ thuật thiết kế test, công cụ sinh test case và
  tự ghi nhận kết quả mong đợi (dòng **vàng** = tự ghi nhận, **cam** = cần xem lại).
  - Trang cần đăng nhập: mở mục **Đăng nhập trước khi quét**, nhập tài khoản thử nghiệm.
  - Nhiều trang: mục **Phạm vi quét** → *Nhiều trang*; trang chỉ mở bằng nút bấm thì thêm URL thủ công.
  - Nút bấm: công cụ bấm thử, ghi nhận thay đổi và kiểm tra không phát sinh lỗi JavaScript.
- **Ghi lại thao tác**: thao tác trên trình duyệt, công cụ ghi thành các bước.

#### Cơ chế chạy
- Mỗi test case chạy trên **phiên trình duyệt mới**, độc lập với nhau.
- Bước lỗi → dừng test case, ghi lỗi, **tự chụp màn hình**, các bước sau *Bỏ qua*.
- Các từ khóa `assert_...` tự chờ đến khi điều kiện đúng hoặc hết thời gian chờ.
""")
    ui.section("Danh sách từ khóa", f"{len(KEYWORD_DOCS)} từ khóa")
    ui.table(pd.DataFrame([{"Từ khóa": name, "Selector": d["selector"] or "-",
                            "Giá trị": d["value"] or "-", "Chức năng": d["doc"]}
                           for name, d in KEYWORD_DOCS.items()]))
    sample = TESTCASES_DIR / "saucedemo.xlsx"
    if sample.exists():
        st.download_button("Tải file Excel mẫu", data=sample.read_bytes(), file_name=sample.name,
                           icon=":material/download:")


# ===========================================================================
# BỐ CỤC CHÍNH
# ===========================================================================

ui.load_css()
settings = sidebar_settings()
ui.header("Công cụ kiểm thử tự động giao diện Web",
          "Kiểm thử hướng từ khóa (keyword-driven) theo kịch bản Excel · Playwright + Python")

tab0, tab1, tab2, tab3, tab4 = st.tabs([
    ":material/dashboard: Tổng quan", ":material/play_circle: Chạy kịch bản", ":material/auto_awesome: Tạo kịch bản",
    ":material/travel_explore: Kiểm tra nhanh", ":material/menu_book: Hướng dẫn"])
with tab0:
    tab_overview()
with tab1:
    tab_run_excel(settings)
with tab2:
    tab_create(settings)
with tab3:
    tab_smoke(settings)
with tab4:
    tab_guide()

# Đặt cuối trang để khối script không chiếm chỗ trong bố cục (script tác động lên toàn trang)
ui.enable_card_navigation()
