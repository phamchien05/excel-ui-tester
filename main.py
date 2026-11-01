"""
Chạy công cụ bằng dòng lệnh.

Ví dụ:
    python main.py testcases/saucedemo.xlsx
    python main.py testcases/saucedemo.xlsx --browser firefox --headed
    python main.py --smoke https://www.saucedemo.com      (kiểm tra nhanh bằng link)
    python main.py --generate https://www.saucedemo.com --valid "#user-name=standard_user" --valid "#password=secret_sauce"
    python main.py --generate https://www.saucedemo.com/checkout-step-one.html --login-url https://www.saucedemo.com \
                   --username standard_user --password secret_sauce      (đăng nhập trước khi quét)
    python main.py --record https://www.saucedemo.com -o testcases/ghi_lai.xlsx
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from core.excel_report import export_excel_report
from core.generator import (GENERATED_NOTES, TECHNIQUES, build_login_steps, crawl_site, form_signature,
                            generate_cases, scan_page, setup_from_suite)
from core.history import save_summary
from core.reader import TestCase, read_suite
from core.recorder import record
from core.reporter import generate_report, generate_smoke_report
from core.runner import PASS, SUPPORTED_BROWSERS, run_suite, slugify
from core.smoke import smoke_check
from core.writer import write_cases

# Đảm bảo in được tiếng Việt trên cửa sổ dòng lệnh Windows
sys.stdout.reconfigure(encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description="Chạy kiểm thử giao diện Web theo kịch bản Excel")
    parser.add_argument("file", nargs="?", help="Đường dẫn file Excel chứa kịch bản test")
    parser.add_argument("--smoke", metavar="URL", help="Kiểm tra nhanh một trang web chỉ bằng URL")
    parser.add_argument("--generate", metavar="URL",
                        help="Quét trang và tự sinh file Excel kịch bản (chọn tất cả form, mọi kỹ thuật)")
    parser.add_argument("--valid", metavar="SELECTOR=GIÁ_TRỊ", action="append", default=[],
                        help="Giá trị hợp lệ cho một ô khi dùng --generate, dùng nhiều lần được")
    parser.add_argument("--login-url", metavar="URL", help="--generate: trang đăng nhập (mặc định = URL cần quét)")
    parser.add_argument("--username", help="--generate: tên đăng nhập để đăng nhập trước khi quét")
    parser.add_argument("--password", help="--generate: mật khẩu để đăng nhập trước khi quét")
    parser.add_argument("--setup-file", metavar="FILE.xlsx",
                        help="--generate: file Excel chứa kịch bản chạy trước khi quét (VD: kịch bản đăng nhập)")
    parser.add_argument("--setup-case", metavar="TÊN", help="--generate: tên test case trong --setup-file")
    parser.add_argument("--crawl", metavar="N", type=int, default=1,
                        help="--generate: quét tối đa N trang theo link cùng website (mặc định 1 = chỉ trang đầu vào)")
    parser.add_argument("--extra-url", metavar="URL", action="append", default=[],
                        help="--generate: thêm trang cần quét (trang chỉ mở được bằng nút bấm), dùng nhiều lần được")
    parser.add_argument("--record", metavar="URL", help="Mở trình duyệt và ghi lại thao tác thành file Excel")
    parser.add_argument("--output", "-o", help="File Excel đầu ra cho --generate / --record")
    parser.add_argument("--browser", "-b", default="chromium", choices=SUPPORTED_BROWSERS,
                        help="Trình duyệt dùng để chạy (mặc định: chromium)")
    parser.add_argument("--headed", action="store_true",
                        help="Hiện cửa sổ trình duyệt khi chạy (mặc định chạy ẩn - headless)")
    parser.add_argument("--timeout", "-t", type=float, default=10,
                        help="Thời gian chờ tối đa cho mỗi thao tác, tính bằng giây (mặc định: 10)")
    parser.add_argument("--reports", default="reports", help="Thư mục gốc chứa báo cáo")
    args = parser.parse_args()
    if not (args.file or args.smoke or args.generate or args.record):
        parser.error("Cần truyền đường dẫn file Excel hoặc một trong --smoke / --generate / --record URL")
    return args


def print_progress(done: int, total: int, case_result):
    """In kết quả từng test case ngay khi chạy xong."""
    mark = "✔ PASS" if case_result.status == PASS else "✘ FAIL"
    print(f"[{done}/{total}] {mark}  {case_result.name}  ({case_result.duration:.2f}s)")
    if case_result.error:
        print(f"        └─ {case_result.error}")


def run_excel(args, output_dir: Path) -> int:
    """Chạy bộ test từ file Excel. Trả về mã thoát."""
    suite = read_suite(args.file)
    print(f"Bộ test: {suite.name}  |  Số test case: {len(suite.cases)}  |  "
          f"Trình duyệt: {args.browser} ({'có giao diện' if args.headed else 'headless'})")
    print("-" * 70)

    result = run_suite(suite, output_dir, browser_name=args.browser, headless=not args.headed,
                       timeout_ms=int(args.timeout * 1000), on_progress=print_progress)

    print("-" * 70)
    print(f"Tổng: {result.total}  |  Pass: {result.passed}  |  Fail: {result.failed}  |  "
          f"Tỷ lệ pass: {result.pass_rate}%  |  Thời gian: {result.duration:.2f}s")

    report_path = generate_report(result, output_dir)
    print(f"Báo cáo HTML: {report_path.resolve()}")
    print(f"Kết quả Excel: {export_excel_report(result, output_dir).resolve()}")
    save_summary(result, output_dir)  # Lưu lịch sử cho trang Tổng quan
    # Mã thoát khác 0 khi có test lỗi -> tiện tích hợp CI/CD
    return 0 if result.failed == 0 else 1


def run_smoke(args, output_dir: Path) -> int:
    """Kiểm tra nhanh một URL. Trả về mã thoát."""
    print(f"Kiểm tra nhanh: {args.smoke}")
    result = smoke_check(args.smoke, output_dir, browser_name=args.browser, headless=not args.headed,
                         on_progress=lambda msg: print(f"  ... {msg}"))
    print("-" * 70)
    labels = {"PASS": "✔ Đạt", "FAIL": "✘ Lỗi", "WARN": "! Cảnh báo"}
    for check in result.checks:
        print(f"{labels[check['status']]:<12} {check['name']:<20} {check['detail']}")
    for link in result.broken_links:
        print(f"  Link lỗi: {link.url}  ->  {link.status or ''} {link.error}")
    for img in result.broken_images:
        print(f"  Ảnh lỗi: {img.src}  ->  {img.reason}")
    print("-" * 70)
    report_path = generate_smoke_report(result, output_dir)
    save_summary(result, output_dir)
    print(f"Kết luận: {labels[result.overall]}  |  Báo cáo HTML: {report_path.resolve()}")
    return 0 if result.overall != "FAIL" else 1


def run_generate(args) -> int:
    """Quét trang, sinh test case cho mọi form / dropdown / nút bấm với tất cả kỹ thuật, ghi ra Excel."""
    setup = []
    if args.username and args.password:
        print(f"Đang thử đăng nhập: {args.login_url or args.generate}")
        setup = build_login_steps(args.login_url or args.generate, args.username, args.password,
                                  browser_name=args.browser)
    elif args.setup_file and args.setup_case:
        setup = setup_from_suite(args.setup_file, args.setup_case)
    if setup:
        print(f"  {len(setup)} bước chuẩn bị sẽ được thêm vào đầu mọi test case")
    if args.crawl > 1 or args.extra_url:
        print(f"Đang quét tối đa {max(args.crawl, 1)} trang bắt đầu từ: {args.generate}")
        scans = crawl_site(args.generate, browser_name=args.browser, setup=setup, max_pages=max(args.crawl, 1),
                           extra_urls=args.extra_url)
    else:
        print(f"Đang quét trang: {args.generate}")
        scans = [scan_page(args.generate, browser_name=args.browser, setup=setup)]
    valid = dict(item.split("=", 1) for item in args.valid if "=" in item)
    seen_forms, seen_selects, seen_controls, cases = set(), set(), set(), []
    for p, scan in enumerate(scans, start=1):
        print(f"P{p} {scan.url}  ({scan.title})")
        if scan.redirected:
            print(f"  ! Trang bị chuyển hướng tới {scan.final_url} - có thể cần đăng nhập (--username/--password)")
        # Form / dropdown lặp lại ở nhiều trang (VD: ô tìm kiếm ở đầu trang) chỉ sinh test một lần
        forms = [f for f in scan.forms if form_signature(f) not in seen_forms]
        selects = [s for s in scan.selects if s.selector not in seen_selects]
        seen_forms.update(form_signature(f) for f in forms)
        seen_selects.update(s.selector for s in selects)
        controls = [c for c in scan.controls if c.label not in seen_controls]
        seen_controls.update(c.label for c in controls)
        for form in forms:
            print(f"  Form '{form.title}':")
            for f in form.fields:
                f.valid_value = valid.get(f.selector, f.valid_value)
                print(f"     {f.selector:<35} {f.label:<25} giá trị hợp lệ = {f.valid_value!r}")
        print(f"  {len(scan.links)} link, {len(selects)} dropdown, {len(controls)} nút & điều khiển")
        cases += generate_cases(scan, forms, set(TECHNIQUES), selects=selects, controls=controls,
                                browser_name=args.browser,
                                name_prefix=f"P{p} " if len(scans) > 1 else "",
                                on_progress=lambda done, total, name: print(f"  [{min(done + 1, total)}/{total}] {name}"))
    scan = scans[0]
    output = args.output or f"testcases/tu_sinh_{slugify(urlparse(scan.url).netloc)}.xlsx"
    write_cases(output, cases, GENERATED_NOTES)
    review = sum(any(s.note == "review" for s in c.steps) for c in cases)
    print(f"Đã sinh {len(cases)} test case ({review} cần xem lại) -> {Path(output).resolve()}")
    return 0


def run_record(args) -> int:
    """Mở trình duyệt, ghi lại thao tác đến khi bấm Dừng ghi / đóng trình duyệt."""
    print("Trình duyệt đang mở. Thao tác trên trang, dùng thanh công cụ góc dưới phải để thêm bước kiểm tra.")
    print("Bấm '⏹ Dừng ghi' hoặc đóng trình duyệt khi xong.")
    steps = record(args.record, browser_name=args.browser,
                   on_step=lambda s: print(f"  + {s.keyword:<15} {s.selector:<40} {s.value}"))
    output = args.output or "testcases/ghi_lai_thao_tac.xlsx"
    write_cases(output, [TestCase(name="Ghi lại thao tác", steps=steps)])
    print(f"Đã ghi {len(steps)} bước -> {Path(output).resolve()}")
    return 0


def main():
    args = parse_args()
    if args.generate:
        sys.exit(run_generate(args))
    if args.record:
        sys.exit(run_record(args))
    output_dir = Path(args.reports) / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sys.exit(run_smoke(args, output_dir) if args.smoke else run_excel(args, output_dir))


if __name__ == "__main__":
    main()
