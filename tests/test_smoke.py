"""Kiểm thử chức năng kiểm tra nhanh bằng link (core/smoke.py)."""

import pytest

from core.smoke import (_analyze_images, _filter_links, check_link, describe_http_status, smoke_check)


def test_check_link_tot_va_hong(site_url):
    assert check_link(site_url + "home.html").status == 200
    broken = check_link(site_url + "khong-co.html")
    assert (broken.status, broken.ok, broken.error) == (404, False, "Không tìm thấy trang")


def test_check_link_khong_ket_noi_duoc():
    result = check_link("http://127.0.0.1:1/", timeout=2)
    assert result.status is None and not result.ok
    assert result.error


def test_loc_link():
    links = ["https://a.com/x#phan", "https://a.com/x", "mailto:a@b.c", "javascript:void(0)", "http://b.com/",
             "https://a.com/trang-nay#neo"]
    assert _filter_links(links, "https://a.com/trang-nay") == ["https://a.com/x", "http://b.com/"]


def test_phan_tich_anh():
    images = _analyze_images([
        {"src": "data:ok", "alt": "Tốt", "complete": True, "naturalWidth": 10},
        {"src": "http://x/hong.png", "alt": None, "complete": True, "naturalWidth": 0},
        {"src": "", "alt": "", "complete": True, "naturalWidth": 0},
    ])
    assert [i.broken for i in images] == [False, True, True]
    assert images[2].reason == "Thiếu thuộc tính src"


@pytest.mark.parametrize("code, text", [(404, "Không tìm thấy trang"), (418, "Lỗi phía máy khách (4xx)"),
                                        (599, "Lỗi phía máy chủ (5xx)")])
def test_dien_giai_ma_http(code, text):
    assert describe_http_status(code) == text


def test_smoke_check_phat_hien_dung_cac_loi(site_url, tmp_path):
    messages = []
    r = smoke_check(site_url + "smoke.html", tmp_path, on_progress=messages.append)

    assert r.page_ok and r.status == 200 and r.title.startswith("Kiểm tra nhanh")
    # Link: chỉ kiểm tra 2 link http (bỏ #neo, mailto), 1 link hỏng
    assert len(r.links) == 2
    assert [l.url.split("/")[-1] for l in r.broken_links] == ["khong-ton-tai.html"]
    # Ảnh: 3 ảnh, 1 hỏng, 1 thiếu alt
    assert len(r.images) == 3
    assert len(r.broken_images) == 1 and r.broken_images[0].src.endswith("khong-co-anh.png")
    assert r.broken_images[0].reason == "HTTP 404 - Không tìm thấy trang"  # Hỏi lại máy chủ để biết lý do
    assert len(r.images_missing_alt) == 1
    # Lỗi JavaScript: console.error + lỗi chưa bắt (+ lỗi tải ảnh 404 trong console)
    assert any("Lỗi thử nghiệm" in e for e in r.console_errors)
    assert any("Lỗi chưa được bắt" in e for e in r.console_errors)
    # Ảnh chụp 3 kích thước
    assert len(r.screenshots) == 3 and all(r.screenshots.values())

    checks = {c["name"]: c["status"] for c in r.checks}
    assert checks == {"Tải trang": "PASS", "Thời gian tải": "PASS", "Link hỏng": "FAIL",
                      "Ảnh không tải được": "FAIL", "Ảnh thiếu alt": "WARN", "Lỗi JavaScript": "FAIL"}
    assert r.overall == "FAIL"
    assert messages[-1] == "Hoàn tất"


def test_smoke_check_trang_tot(site_url, tmp_path):
    r = smoke_check(site_url + "home.html", tmp_path, max_links=1)
    assert r.overall == "PASS"
    assert r.links_total_found == 1


def test_smoke_check_trang_404(site_url, tmp_path):
    r = smoke_check(site_url + "khong-co.html", tmp_path)
    assert not r.page_ok and r.status == 404
    assert "HTTP 404" in r.error
    assert r.overall == "FAIL"


def test_smoke_check_khong_ket_noi_duoc(tmp_path):
    r = smoke_check("http://127.0.0.1:1/", tmp_path)
    assert r.status is None and "Không tải được trang" in r.error
    assert r.screenshots == {}  # Không tải được thì không chụp


def test_anh_may_chu_tra_ve_binh_thuong_nhung_trinh_duyet_khong_hien_thi(site_url, tmp_path):
    r = smoke_check(site_url + "format.html", tmp_path)
    assert len(r.broken_images) == 1
    assert r.broken_images[0].reason.startswith("Máy chủ trả ảnh bình thường (HTTP 200)")
    assert r.broken_images[0].reason.endswith("định dạng .avif")
