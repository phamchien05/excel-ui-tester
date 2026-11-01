"""
Cấu hình dùng chung cho bộ unit test.

- site_url: bật một web server cục bộ phục vụ thư mục tests/site/ (trang thử nghiệm tự viết),
  nhờ đó các test không phụ thuộc Internet và luôn cho kết quả ổn định.
- make_excel: hàm tiện ích tạo nhanh file Excel kịch bản từ danh sách bước.
"""

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from core.reader import TestCase, TestStep
from core.writer import write_cases

SITE_DIR = Path(__file__).parent / "site"


class QuietHandler(SimpleHTTPRequestHandler):
    """Handler phục vụ file tĩnh, không in log ra màn hình."""

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def site_url():
    """URL gốc của trang thử nghiệm, VD: http://127.0.0.1:54321/"""
    handler = partial(QuietHandler, directory=str(SITE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)  # Cổng 0 = hệ điều hành tự chọn cổng trống
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


@pytest.fixture
def make_excel(tmp_path):
    """
    Tạo file Excel kịch bản. Cách dùng:
        path = make_excel({"Tên case": [("open", "", url, ""), ("click", "#btn", "", "")]})
    """
    def _make(cases: dict, name: str = "bo_test.xlsx") -> Path:
        test_cases = [
            TestCase(case_name, [TestStep(i, kw, sel, val, desc) for i, (kw, sel, val, desc) in enumerate(steps, 1)])
            for case_name, steps in cases.items()
        ]
        return write_cases(tmp_path / name, test_cases)
    return _make
