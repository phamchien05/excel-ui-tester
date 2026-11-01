"""Kiểm thử chức năng quét trang và tự sinh test case (core/generator.py)."""

from urllib.parse import quote

import pytest

from core.generator import (FormField, FormInfo, TECHNIQUES, _fill_steps, _submit_step, _url_part,
                            count_form_cases, generate_cases, guess_valid_value, scan_page)
from core.reader import read_suite
from core.runner import PASS, run_suite
from core.writer import write_cases


def field(selector="#a", label="Ô", tag="input", type="text", **kw):
    return FormField(selector=selector, label=label, tag=tag, type=type, **kw)


def data_url(html: str) -> str:
    """Tạo trang web tạm từ chuỗi HTML (không cần file)."""
    return "data:text/html;charset=utf-8," + quote(html)


# ---------------------------------------------------------------------------
# Đoán giá trị hợp lệ
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("f, expected", [
    (field(type="email"), "test.user@example.com"),
    (field(label="Địa chỉ email"), "test.user@example.com"),
    (field(type="password"), "Abc@12345"),
    (field(type="tel"), "0912345678"),
    (field(type="url"), "https://example.com"),
    (field(type="number", min="18", max="60"), "39"),
    (field(type="range"), "50"),
    (field(type="color"), "#3366ff"),
    (field(type="date"), "2000-01-15"),
    (field(selector="#username"), "testuser"),
    (field(selector="#postal-code"), "100000"),
    (field(tag="textarea", type="textarea"), "Noi dung kiem thu tu dong"),
    (field(selector='input[name="my-colors"]', type="text", label="Màu"), "Kiem thu"),  # "name" trong cú pháp không bị tính
    (field(type="checkbox"), ""),
    (field(type="checkbox", required=True), "check"),
    (field(maxlength=3), "Kie"),
    (field(minlength=12), "Kiem thuaaaa"),
])
def test_doan_gia_tri_hop_le(f, expected):
    assert guess_valid_value(f) == expected


def test_select_bo_qua_lua_chon_huong_dan():
    f = field(tag="select", type="select", options=[{"value": "", "label": "-- Chọn --"}, {"value": "hn", "label": "HN"}])
    assert guess_valid_value(f) == "hn"
    assert guess_valid_value(field(tag="select", type="select", options=[{"value": "x", "label": "X"}])) == "x"


# ---------------------------------------------------------------------------
# Số test case sinh ra theo từng kỹ thuật
# ---------------------------------------------------------------------------

@pytest.fixture
def form():
    return FormInfo("Đăng ký", "#reg", "#submit", "Gửi", [
        field("#name", "Tên", required=True, maxlength=10),
        field("#email", "Email", type="email", required=True),
        field("#age", "Tuổi", type="number", min="18", max="60"),
    ])


@pytest.mark.parametrize("techniques, expected", [
    ({"hop_le"}, 1),
    ({"bo_trong"}, 3),           # 2 ô bắt buộc + bỏ trống tất cả
    ({"dinh_dang"}, 4),          # email: 2 cách sai, số: âm + thập phân
    ({"gia_tri_bien"}, 6),       # Tên: max, max+1; Tuổi: min-1, min, max, max+1
    ({"ky_tu_dac_biet"}, 2),     # XSS + SQL injection
    (set(TECHNIQUES), 16),
])
def test_so_luong_test_case(form, techniques, expected):
    assert count_form_cases(form, techniques) == expected


def test_buoc_dien_form():
    form = FormInfo("F", "form", "", "", [
        field("#t", "Tên"), field("#s", "Chọn", tag="select", type="select"),
        field("#c", "Đồng ý", type="checkbox"), field("#e", "Email", type="email"),
    ])
    steps = _fill_steps(form, {"#t": "", "#s": "hn", "#c": "check", "#e": "a@b.c"})
    assert [(s.keyword, s.selector, s.value) for s in steps] == [
        ("clear", "#t", ""), ("select", "#s", "hn"), ("click", "#c", ""), ("type", "#e", "a@b.c")]
    assert _submit_step(form).keyword == "press_key"  # Không có nút gửi -> nhấn Enter
    assert _submit_step(FormInfo("F", "form", "#ok", "OK", form.fields)).keyword == "click"


@pytest.mark.parametrize("url, before, expected", [
    ("http://x/home.html", "http://x/login.html", "/home.html"),
    ("http://x/search?q=a", "http://x/search", "/search?q=a"),
    ("http://x/", "", "http://x/"),
])
def test_phan_dac_trung_cua_url(url, before, expected):
    assert _url_part(url, before) == expected


# ---------------------------------------------------------------------------
# Quét trang và sinh test case trên trang thử nghiệm (tích hợp)
# ---------------------------------------------------------------------------

def test_quet_trang(site_url):
    scan = scan_page(site_url + "register.html")
    assert scan.title == "Đăng ký - Trang thử nghiệm"
    assert len(scan.forms) == 1
    f = scan.forms[0]
    assert [(x.selector, x.label, x.type, x.required) for x in f.fields] == [
        ("#fullname", "Họ tên", "text", True), ("#email", "Email", "email", True), ("#age", "Tuổi", "number", False)]
    assert f.fields[0].maxlength == 10 and (f.fields[2].min, f.fields[2].max) == ("18", "60")
    assert f.submit == 'text="Đăng ký"'
    assert [(s.selector, s.label) for s in scan.selects] == [("#sort", "Sắp xếp")]  # Dropdown đứng riêng
    assert [l.text for l in scan.links] == ["Đã có tài khoản"]
    assert scan.headings == [{"selector": "h1", "text": "Đăng ký tài khoản"}]


def test_sinh_va_ghi_nhan_ket_qua_roi_chay_lai_deu_dat(site_url, tmp_path):
    scan = scan_page(site_url + "register.html")
    progress = []
    cases = generate_cases(scan, scan.forms, set(TECHNIQUES), links=scan.links, selects=scan.selects,
                           on_progress=lambda d, t, n: progress.append(d))
    by_name = {c.name: c for c in cases}
    last = lambda name: by_name[name].steps[-1]

    assert len(cases) == 1 + 16 + 1 + 1   # Hiển thị trang + form + link + dropdown
    assert progress[-1] == 16
    assert (last("F1-01 Hợp lệ").keyword, last("F1-01 Hợp lệ").value) == ("assert_text", "Đăng ký thành công!")
    assert (last("F1-02 Bỏ trống Họ tên").keyword, last("F1-02 Bỏ trống Họ tên").selector) == ("assert_invalid", "#fullname")
    assert last("F1-05 Sai định dạng Email (email thiếu @)").selector == "#email"
    assert last("F1-11 Biên Tuổi = min-1").keyword == "assert_invalid"
    assert last("F1-12 Biên Tuổi = min").keyword == "assert_text"
    max_plus = by_name["F1-10 Biên Họ tên = max+1"]
    assert any(s.keyword == "assert_value" and s.value == "a" * 10 for s in max_plus.steps)
    assert all(s.note == "auto" for c in cases if c.name.startswith("F1") for s in c.steps[-1:])
    assert [s.step_no for s in cases[1].steps] == list(range(1, len(cases[1].steps) + 1))

    # Ghi ra Excel rồi chạy lại: mọi test case phải đạt vì trang không thay đổi
    path = write_cases(tmp_path / "sinh.xlsx", cases)
    result = run_suite(read_suite(path), tmp_path / "out", timeout_ms=2000)
    assert [c.name for c in result.cases if c.status != PASS] == []


def test_ghi_nhan_thong_bao_loi_va_chuyen_trang(site_url):
    scan = scan_page(site_url + "login.html")
    f = scan.forms[0]
    f.fields[0].valid_value, f.fields[1].valid_value = "admin", "123456"
    cases = generate_cases(scan, [f], {"hop_le", "bo_trong"}, include_page_check=False)
    expected = {c.name: (c.steps[-1].keyword, c.steps[-1].value) for c in cases}
    assert expected == {
        "F1-01 Hợp lệ": ("assert_url", "/home.html"),
        "F1-02 Bỏ trống Tên đăng nhập": ("assert_text", "Vui lòng nhập tên đăng nhập"),
        "F1-03 Bỏ trống Mật khẩu": ("assert_text", "Vui lòng nhập mật khẩu"),
        "F1-04 Bỏ trống tất cả": ("assert_text", "Vui lòng nhập tên đăng nhập"),
    }


def test_khong_chay_thu_thi_danh_dau_can_xem_lai(site_url):
    scan = scan_page(site_url + "login.html")
    cases = generate_cases(scan, scan.forms, {"hop_le"}, include_page_check=False, observe=False)
    assert cases[0].steps[-1].note == "review"


def test_form_khong_phan_hoi_va_canh_bao_xss():
    html = """<title>T</title>
      <form id="f"><input id="q"><button id="go">Gửi</button></form>
      <script>document.getElementById('f').onsubmit = function (e) {
        e.preventDefault(); var v = document.getElementById('q').value;
        if (v.indexOf('<script') >= 0) alert('XSS!');  // Mô phỏng trang có lỗ hổng
      };</script>"""
    scan = scan_page(data_url(html))
    cases = generate_cases(scan, scan.forms, {"hop_le", "ky_tu_dac_biet"}, include_page_check=False)
    by_name = {c.name: c for c in cases}
    assert by_name["F1-01 Hợp lệ"].steps[-1].note == "review"           # Không thấy thay đổi gì
    xss_notes = [s.description for s in by_name["F1-02 XSS"].steps if s.note == "review"]
    assert any("XSS!" in d for d in xss_notes)                            # Phát hiện hộp thoại alert


def test_o_nhap_ngoai_form_va_khong_co_nut_gui():
    html = "<title>T</title><div><input id='a' aria-label='Tìm kiếm' type='search'></div>"
    scan = scan_page(data_url(html))
    assert len(scan.forms) == 1 and scan.forms[0].submit == "" and scan.forms[0].selector == "body"
    cases = generate_cases(scan, scan.forms, {"hop_le"}, include_page_check=False, observe=False)
    assert cases[0].steps[-2].keyword == "press_key"


def test_buoc_dien_loi_thi_danh_dau_can_xem_lai(site_url):
    scan = scan_page(site_url + "login.html")
    scan.forms[0].fields[0].selector = "#khong-ton-tai"   # Giả lập selector sai
    cases = generate_cases(scan, scan.forms, {"hop_le"}, include_page_check=False, timeout_ms=500)
    assert "Không chạy thử được" in cases[0].steps[-1].description


# ---------------------------------------------------------------------------
# PHẦN A: Đăng nhập / bước chuẩn bị trước khi quét (dùng shop thử nghiệm: tests/site/shop, tài khoản demo/demo123)
# ---------------------------------------------------------------------------

from core.generator import SETUP_PREFIX, SetupError, build_login_steps, setup_from_suite  # noqa: E402


@pytest.fixture(scope="module")
def shop_login(site_url):
    """Bước đăng nhập shop (tạo một lần cho cả file test)."""
    return build_login_steps(site_url + "shop/login.html", "demo", "demo123")


def test_tu_tim_form_dang_nhap(shop_login, site_url):
    assert [(s.keyword, s.selector, s.value) for s in shop_login] == [
        ("open", "", site_url + "shop/login.html"), ("type", "#username", "demo"),
        ("type", "#password", "demo123"), ("click", 'text="Đăng nhập"', "")]
    assert all(s.description.startswith(SETUP_PREFIX) for s in shop_login)


def test_dang_nhap_sai_bao_loi_kem_thong_bao_cua_trang(site_url):
    with pytest.raises(SetupError, match='Đăng nhập không thành công: "Sai thông tin đăng nhập"'):
        build_login_steps(site_url + "shop/login.html", "demo", "sai-mat-khau")


def test_trang_khong_co_o_mat_khau(site_url):
    with pytest.raises(SetupError, match="Không tìm thấy ô mật khẩu"):
        build_login_steps(site_url + "home.html", "a", "b")


def test_chua_dang_nhap_thi_bi_chuyen_ve_trang_dang_nhap(site_url):
    scan = scan_page(site_url + "shop/contact.html")
    assert scan.redirected and scan.final_url.endswith("shop/login.html")
    assert [f.title for f in scan.forms] == ["Đăng nhập"]


def test_dang_nhap_roi_quet_va_sinh_test_chay_lai_deu_dat(shop_login, site_url, tmp_path):
    scan = scan_page(site_url + "shop/contact.html", setup=shop_login)
    assert not scan.redirected and scan.setup == shop_login
    contact = next(f for f in scan.forms if f.title == "Liên hệ")
    # Nhóm radio 2 nút được gộp thành 1 trường; radio/checkbox không bị coi là ô email
    assert [f.type for f in contact.fields].count("radio") == 1
    assert next(f for f in contact.fields if f.type == "radio").kind == "other"

    cases = generate_cases(scan, [contact], {"hop_le", "bo_trong", "dinh_dang"})
    by_name = {c.name: c for c in cases}
    assert not any("Liên hệ qua email (email" in n for n in by_name)       # Không sinh test sai định dạng cho radio
    assert by_name["F1-01 Hợp lệ"].steps[-1].value == "Đã gửi liên hệ"
    assert by_name["F1-05 Không chọn Đồng ý điều khoản"].steps[-1].keyword == "assert_invalid"
    # Mọi test case bắt đầu bằng 4 bước đăng nhập rồi mới mở trang cần test
    for c in cases:
        assert [s.keyword for s in c.steps[:5]] == ["open", "type", "type", "click", "open"]
        assert c.steps[4].value == site_url + "shop/contact.html"

    result = run_suite(read_suite(write_cases(tmp_path / "a.xlsx", cases)), tmp_path / "out", timeout_ms=3000)
    assert [c.name for c in result.cases if c.status != PASS] == []


def test_buoc_chuan_bi_lay_tu_file_excel(make_excel, site_url):
    path = make_excel({"Đăng nhập shop": [("open", "", site_url + "shop/login.html", "Mở"),
                                          ("type", "#username", "demo", ""), ("type", "#password", "demo123", ""),
                                          ("press_key", "#password", "Enter", "")]})
    setup = setup_from_suite(path, "Đăng nhập shop")
    assert [s.keyword for s in setup] == ["open", "type", "type", "press_key"]
    assert setup[0].description == SETUP_PREFIX + "Mở" and setup[1].description == SETUP_PREFIX + "type"
    scan = scan_page(site_url + "shop/contact.html", setup=setup)
    assert not scan.redirected
    with pytest.raises(SetupError, match="Không tìm thấy test case"):
        setup_from_suite(path, "Không có")


def test_buoc_chuan_bi_loi_thi_bao_ro_buoc_nao(site_url):
    from core.reader import TestStep
    bad = [TestStep(1, "open", "", site_url + "shop/login.html"), TestStep(2, "click", "#khong-co")]
    with pytest.raises(SetupError, match=r"Bước chuẩn bị 2 \(click #khong-co\) bị lỗi"):
        scan_page(site_url + "shop/contact.html", setup=bad, timeout_ms=500)


def test_khong_chon_nham_nut_huy_lam_nut_gui():
    html = """<title>T</title><form id="f"><input id="name">
      <button id="cancel">Cancel</button><button id="back">Quay lại</button>
      <input type="submit" id="continue" value="Continue"></form>"""
    scan = scan_page(data_url(html))
    assert scan.forms[0].submit == "#continue"


def test_url_chi_khac_dau_gach_cuoi_khong_tinh_la_chuyen_huong():
    from core.generator import PageScan
    scan = PageScan(url="https://a.com", title="", headings=[], forms=[], links=[], selects=[],
                    final_url="https://a.com/")
    assert not scan.redirected


# ---------------------------------------------------------------------------
# PHẦN B: Quét nhiều trang
# ---------------------------------------------------------------------------

from core.generator import crawl_site, form_signature, page_template, should_follow  # noqa: E402


def test_quet_nhieu_trang_sau_khi_dang_nhap(shop_login, site_url):
    progress = []
    scans = crawl_site(site_url + "shop/index.html", setup=shop_login,
                       on_progress=lambda done, total, url: progress.append(url))
    assert [s.url.split("/")[-1] for s in scans] == ["index.html", "products.html", "contact.html"]
    assert not any(s.redirected for s in scans)
    assert all(s.setup == shop_login for s in scans)     # Test case sinh ra ở mọi trang đều tự đăng nhập
    assert progress[-1] == "Hoàn tất"
    # Không đi vào: đăng xuất (mất phiên), website khác, file PDF
    visited = " ".join(s.url for s in scans)
    assert "logout" not in visited and "example.com" not in visited and ".pdf" not in visited


def test_gioi_han_so_trang_va_them_url_thu_cong(shop_login, site_url):
    assert len(crawl_site(site_url + "shop/index.html", setup=shop_login, max_pages=2)) == 2
    scans = crawl_site(site_url + "shop/contact.html", setup=shop_login, max_pages=1,
                       extra_urls=[site_url + "shop/products.html"])
    assert [s.url.split("/")[-1] for s in scans] == ["contact.html"]
    scans = crawl_site(site_url + "shop/contact.html", setup=shop_login, max_pages=2,
                       extra_urls=[site_url + "shop/products.html", "  "])
    assert [s.url.split("/")[-1] for s in scans] == ["contact.html", "products.html"]


def test_chua_dang_nhap_cac_trang_chuyen_huong_chi_giu_mot(site_url):
    scans = crawl_site(site_url + "shop/index.html", extra_urls=[site_url + "shop/contact.html"])
    assert len(scans) == 1 and scans[0].redirected and scans[0].final_url.endswith("login.html")


def test_form_lap_lai_o_nhieu_trang_co_cung_dau_hieu(shop_login, site_url):
    scans = crawl_site(site_url + "shop/index.html", setup=shop_login)
    search_forms = [f for s in scans for f in s.forms if any(x.selector == "#q" for x in f.fields)]
    assert len(search_forms) == 3 and len({form_signature(f) for f in search_forms}) == 1


@pytest.mark.parametrize("href, text, ok", [
    ("https://a.com/san-pham", "Sản phẩm", True),
    ("https://b.com/x", "Đối tác", False),                  # Website khác
    ("https://a.com/files/hd.pdf", "Tải về", False),        # File
    ("https://a.com/logout", "Thoát", False),               # Đăng xuất
    ("https://a.com/x", "Đăng xuất", False),
    ("https://a.com/item/5/delete", "Bỏ", False),           # Xóa dữ liệu
    ("mailto:a@a.com", "Email", False),
])
def test_link_nao_duoc_di_theo(href, text, ok):
    assert should_follow(href, text, "a.com") is ok


def test_khuon_mau_trang():
    assert page_template("https://a.com/product/01M64D4165EW1MFKCSP4R7CQTK") == \
        page_template("https://a.com/product/01M64D416KM2CFS7R2CJDY917D")
    assert page_template("https://a.com/user/12") == page_template("https://a.com/user/345/")
    assert page_template("https://a.com/category/hand-tools") != page_template("https://a.com/category/power-tools")
    assert page_template("https://a.com/list?page=1") == page_template("https://a.com/list?page=2")


def test_tien_to_ten_test_case_theo_trang(shop_login, site_url):
    scan = scan_page(site_url + "shop/contact.html", setup=shop_login)
    cases = generate_cases(scan, [], set(), links=scan.links[:1], observe=False, name_prefix="P3 ")
    assert [c.name.split(" ")[0] for c in cases] == ["P3", "P3"] and cases[0].name == "P3 Hiển thị trang"


# ---------------------------------------------------------------------------
# PHẦN C: Nút bấm và điều khiển đứng riêng (ngoài form)
# ---------------------------------------------------------------------------

from core.generator import ControlInfo  # noqa: E402


@pytest.fixture(scope="module")
def products_scan(shop_login, site_url):
    return scan_page(site_url + "shop/products.html", setup=shop_login)


def test_quet_nut_bam_va_dieu_khien_ngoai_form(products_scan):
    s = products_scan
    assert [f.title for f in s.forms] == ["Tìm"]                       # Checkbox/dropdown không bị gộp thành form giả
    assert [x.selector for x in s.selects] == ["#sort"]
    assert [(c.kind, c.label, c.selector) for c in s.controls] == [
        ("checkbox", "Chỉ hàng còn", "#in-stock"), ("button", "Thêm vào giỏ", "#add-1"),
        ("button", "Xem chi tiết", "#detail-1"), ("button", "Làm mới", "#btn-noop"),
        ("button", "Báo lỗi", "#btn-broken")]
    # Bỏ qua: nút "Tìm" (thuộc form tìm kiếm), nút "Thêm vào giỏ" thứ 2 (trùng tên), "Xóa tài khoản" (nguy hiểm)
    assert not any(c.selector in ("#search-btn", "#add-2", "#btn-delete-account") for c in s.controls)


def test_sinh_test_cho_nut_bam_va_phat_hien_loi_javascript(products_scan, tmp_path):
    cases = generate_cases(products_scan, [], set(), controls=products_scan.controls, include_page_check=False)
    result = {c.name: [(s.keyword, s.selector, s.value, s.note) for s in c.steps[5:]] for c in cases}
    assert result["C01 Checkbox Chỉ hàng còn"] == [("click", "#in-stock", "", ""),
        ("assert_text", "#result-count", "Hiển thị 2 sản phẩm", "auto"), ("assert_no_js_error", "", "", "")]
    assert result["C02 Nút Thêm vào giỏ"][1] == ("assert_text", "#cart-count", "1", "auto")
    assert result["C03 Nút Xem chi tiết"][1] == ("assert_text", "#modal", "Chi tiết sản phẩm Áo thun", "auto")
    assert result["C04 Nút Làm mới"][1][3] == "review"                  # Không thấy thay đổi -> cần xem lại
    assert result["C05 Nút Báo lỗi"][-1][:1] == ("assert_no_js_error",) and result["C05 Nút Báo lỗi"][-1][3] == "review"

    run = run_suite(read_suite(write_cases(tmp_path / "c.xlsx", cases)), tmp_path / "out", timeout_ms=3000)
    failed = [(c.name, c.error) for c in run.cases if c.status != PASS]
    assert len(failed) == 1 and failed[0][0] == "C05 Nút Báo lỗi"     # Nút gây lỗi JS -> test thất bại khi chạy lại
    assert "undefinedFunction is not defined" in failed[0][1]


def test_bo_qua_phan_tu_an_trong_menu_truot_va_aria_hidden():
    html = """<title>T</title>
      <button id="open">Mở menu</button>
      <div id="menu" aria-hidden="true" style="position:fixed;left:0;transform:translateX(-110%)">
        <button id="m1">Trang chủ</button></div>
      <div style="position:absolute;left:-500px"><button id="far">Ngoài màn hình</button></div>
      <script>document.getElementById('open').onclick = function () {
        var m = document.getElementById('menu'); m.style.transform = 'none'; m.removeAttribute('aria-hidden'); };</script>"""
    scan = scan_page(data_url(html))
    assert [c.selector for c in scan.controls] == ["#open"]
    case = generate_cases(scan, [], set(), controls=scan.controls, include_page_check=False)[0]
    assert (case.steps[2].keyword, case.steps[2].selector, case.steps[2].value) == ("assert_text", "#m1", "Trang chủ")


def test_trang_ve_lai_giao_dien_khong_bi_ghi_nhan_nham():
    # Mỗi lần bấm, phần đầu trang được vẽ lại bằng phần tử mới cùng nội dung (giống React) và số đếm tăng
    html = """<title>T</title><div id="header"></div><span id="count">0</span><button id="add">Thêm</button>
      <script>var n = 0;
        function draw() { document.getElementById('header').innerHTML = '<b>Cửa hàng</b><i>Menu</i>'; }
        draw();
        document.getElementById('add').onclick = function () { draw(); n++; document.getElementById('count').textContent = n; };
      </script>"""
    scan = scan_page(data_url(html))
    case = generate_cases(scan, [], set(), controls=scan.controls, include_page_check=False)[0]
    assert (case.steps[2].selector, case.steps[2].value) == ("#count", "1")


def test_khong_chay_thu_van_co_buoc_kiem_tra_loi_js(products_scan):
    case = generate_cases(products_scan, [], set(), controls=products_scan.controls[:1], observe=False,
                          include_page_check=False)[0]
    assert [s.keyword for s in case.steps[-2:]] == ["assert_text", "assert_no_js_error"]
    assert case.steps[-2].note == "review"


def test_ten_loai_dieu_khien():
    assert [ControlInfo("#a", "x", k).kind_text for k in ("button", "checkbox", "radio")] == ["Nút", "Checkbox", "Radio"]


def test_link_ghi_nhan_dich_thuc_te_ke_ca_chuyen_huong(shop_login, site_url):
    scan = scan_page(site_url + "shop/index.html", setup=shop_login)
    links = {l.text: l for l in scan.links}
    cases = generate_cases(scan, [], set(), links=[links["Đăng xuất"], links["Tải hướng dẫn"], links["Sản phẩm"]],
                           include_page_check=False)
    last = {c.name: next(s for s in c.steps[6:] if s.keyword != "assert_no_js_error") for c in cases}
    assert (last["L01 Link Đăng xuất"].keyword, last["L01 Link Đăng xuất"].value) == ("assert_url", "/shop/login.html")
    assert last["L02 Link Tải hướng dẫn"].note == "review"          # Link tải file: không chuyển trang -> cần xem lại
    assert last["L03 Link Sản phẩm"].value == "/shop/products.html"
    assert all(c.steps[-1].keyword == "assert_no_js_error" for c in cases)


def test_link_chi_co_anh_sinh_selector_theo_anh_ben_trong(site_url, tmp_path):
    # Nguyên nhân 2 test parabank lỗi: link logo chỉ có ảnh -> trước đây phải dùng a:nth-of-type(n)
    from openpyxl import load_workbook
    from core.dom import FRAGILE_NOTE
    scan = scan_page(site_url + "logo.html")
    links = {l.href.split("/", 3)[-1]: l for l in scan.links}
    assert {k: l.selector for k, l in links.items()} == {
        "login.html": "a:has(img.admin)",                     # alt, src trùng nhau -> dùng class của ảnh
        "home.html": "a:has(img.logo)",
        "widgets.html": 'a:has(img[alt="Giỏ hàng"])',
        "register.html": 'a:has(img[src*="dang-ky.svg"])',   # Không có alt -> theo tên file ảnh
        "format.html": "div:nth-of-type(2) > a:nth-of-type(3)",  # Không còn cách nào khác
        "shop/login.html": 'a:has(img[alt="Logo nổi"]) img',  # Thẻ <a> kích thước 0 -> bấm vào ảnh bên trong
    }
    assert [links[k].text for k in ("login.html", "widgets.html")] == ["Cửa hàng", "Giỏ hàng"]  # Nhãn lấy từ alt
    cases = generate_cases(scan, [], set(), links=list(links.values()), include_page_check=False)
    clicks = {c.name: next(s for s in c.steps if s.keyword == "click") for c in cases}
    fragile = [s for s in clicks.values() if ":nth-of-type(" in s.selector]
    assert len(fragile) == 1 and fragile[0].note == "review" and FRAGILE_NOTE in fragile[0].description
    assert all(s.note != "review" for s in clicks.values() if s not in fragile)

    # Trong Excel: chỉ bước dùng selector theo vị trí bị tô cam; chạy lại thì tất cả đều đạt
    path = write_cases(tmp_path / "logo.xlsx", cases)
    wb = load_workbook(path)
    orange = [row[2].value for ws in wb for row in ws.iter_rows(min_row=2)
              if row[0].fill.fgColor.rgb == "00F8CBAD" and row[1].value == "click"]
    assert orange == [fragile[0].selector]
    result = run_suite(read_suite(path), tmp_path / "out", timeout_ms=3000)
    assert [c.status for c in result.cases] == [PASS] * 6


def test_danh_dau_selector_theo_vi_tri():
    from core.dom import is_fragile_selector, mark_fragile
    from core.reader import TestStep
    assert is_fragile_selector("#top > a:nth-of-type(1)") and not is_fragile_selector('a:has(img[alt="Logo"])')
    step = mark_fragile(TestStep(1, "click", "ul > li:nth-of-type(2)", "", "Bấm mục 2"))
    assert step.note == "review" and step.description.startswith("Bấm mục 2 (selector dựa vào vị trí")
    mark_fragile(step)                                                   # Gọi lại không lặp ghi chú
    assert step.description.count("nth-of-type") == 1
    assert mark_fragile(TestStep(1, "click", "#ok", "", "Bấm", note="auto")).note == "auto"
