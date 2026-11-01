"""
Sinh báo cáo HTML từ kết quả chạy test bằng Jinja2.

Ảnh chụp màn hình được nhúng thẳng vào HTML dưới dạng base64, nhờ đó file
báo cáo là MỘT file duy nhất, mở trực tiếp bằng trình duyệt, gửi cho người khác
vẫn xem đủ ảnh mà không cần server hay thư mục ảnh đi kèm.
"""

from __future__ import annotations

import base64
import mimetypes
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
REPORT_FILE_NAME = "report.html"


def image_to_data_uri(path: str | None) -> str:
    """Đọc file ảnh và chuyển thành chuỗi data URI (data:image/png;base64,...)."""
    if not path or not Path(path).exists():
        return ""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _create_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),  # Tự escape để nội dung lỗi không phá vỡ HTML
    )
    env.filters["img_data"] = image_to_data_uri  # Dùng trong template: {{ path | img_data }}
    return env


def _render(template_name: str, output_path: Path, **context) -> Path:
    html = _create_env().get_template(template_name).render(
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M:%S"), **context
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def generate_report(result, output_dir: str | Path) -> Path:
    """Sinh báo cáo cho kết quả chạy bộ test Excel. Trả về đường dẫn file HTML."""
    total_steps = sum(len(c.steps) for c in result.cases)
    return _render("report.html", Path(output_dir) / REPORT_FILE_NAME,
                   r=result, total_steps=total_steps)


def generate_smoke_report(result, output_dir: str | Path) -> Path:
    """Sinh báo cáo cho chức năng kiểm tra nhanh bằng link."""
    return _render("smoke_report.html", Path(output_dir) / REPORT_FILE_NAME, r=result)
