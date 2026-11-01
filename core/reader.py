"""
Đọc bộ test từ file Excel.

Quy ước file Excel:
  - Mỗi file = một bộ test (test suite).
  - Mỗi sheet = một test case, tên sheet chính là tên test case.
  - Dòng đầu tiên của sheet là tiêu đề cột: Bước | Từ khóa | Selector | Giá trị | Mô tả
  - Sheet đặc biệt tên "DATA" (nếu có) chứa dữ liệu cho kiểm thử hướng dữ liệu
    (data-driven): dòng đầu là tên biến, mỗi dòng sau là một bộ dữ liệu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

# Tên sheet chứa dữ liệu cho data-driven testing
DATA_SHEET_NAME = "DATA"

# Ánh xạ tên cột (đã chuẩn hóa về chữ thường) -> tên thuộc tính trong TestStep.
# Chấp nhận cả tên tiếng Việt lẫn tiếng Anh để file Excel linh hoạt hơn.
COLUMN_ALIASES = {
    "bước": "step_no", "buoc": "step_no", "step": "step_no", "stt": "step_no",
    "từ khóa": "keyword", "từ khoá": "keyword", "tu khoa": "keyword", "keyword": "keyword",
    "selector": "selector", "locator": "selector",
    "giá trị": "value", "gia tri": "value", "value": "value",
    "mô tả": "description", "mo ta": "description", "description": "description",
}


@dataclass
class TestStep:
    """Một bước trong test case (tương ứng một dòng trong sheet)."""
    __test__ = False  # Báo cho pytest: đây không phải class chứa unit test (tên bắt đầu bằng "Test")
    step_no: int
    keyword: str
    selector: str = ""
    value: str = ""
    description: str = ""
    # Chỉ dùng khi công cụ tự sinh kịch bản: "auto" = kết quả mong đợi do công cụ tự ghi nhận,
    # "review" = cần người kiểm tra xem lại. Khi ghi ra Excel các dòng này được tô màu.
    note: str = ""


@dataclass
class TestCase:
    """Một test case (tương ứng một sheet)."""
    __test__ = False
    name: str
    steps: list[TestStep] = field(default_factory=list)
    data_row: dict | None = None  # Bộ dữ liệu đã dùng (chỉ có khi chạy data-driven)


@dataclass
class TestSuite:
    """Một bộ test (tương ứng một file Excel)."""
    __test__ = False
    name: str
    file_path: str
    cases: list[TestCase] = field(default_factory=list)
    data: list[dict] = field(default_factory=list)  # Các dòng của sheet DATA (nếu có)


def _cell_to_str(value) -> str:
    """Chuyển giá trị ô Excel thành chuỗi. Số nguyên kiểu 3.0 được đổi thành '3'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _map_header(header_row) -> dict[str, int]:
    """Xác định cột nào ứng với thuộc tính nào dựa vào dòng tiêu đề."""
    mapping = {}
    for idx, cell in enumerate(header_row):
        name = _cell_to_str(cell).lower()
        if name in COLUMN_ALIASES:
            mapping[COLUMN_ALIASES[name]] = idx
    if "keyword" not in mapping:
        raise ValueError("Không tìm thấy cột 'Từ khóa' ở dòng tiêu đề")
    return mapping


def _read_case_sheet(ws) -> TestCase:
    """Đọc một sheet thành một TestCase. Sheet không có cột 'Từ khóa' (VD: sheet ghi chú) trả về case rỗng."""
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return TestCase(name=ws.title)

    try:
        mapping = _map_header(rows[0])
    except ValueError:
        return TestCase(name=ws.title)  # Không phải sheet kịch bản -> bỏ qua

    def get(row, attr):
        idx = mapping.get(attr)
        return _cell_to_str(row[idx]) if idx is not None and idx < len(row) else ""

    case = TestCase(name=ws.title)
    for row in rows[1:]:
        keyword = get(row, "keyword").lower()
        if not keyword:  # Bỏ qua dòng trống
            continue
        step_no_text = get(row, "step_no")
        step_no = int(step_no_text) if step_no_text.isdigit() else len(case.steps) + 1
        case.steps.append(TestStep(
            step_no=step_no,
            keyword=keyword,
            selector=get(row, "selector"),
            value=get(row, "value"),
            description=get(row, "description"),
        ))
    return case


def _read_data_sheet(ws) -> list[dict]:
    """Đọc sheet DATA: dòng đầu là tên biến, mỗi dòng sau là một bộ dữ liệu."""
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [_cell_to_str(h) for h in rows[0]]
    data = []
    for row in rows[1:]:
        values = [_cell_to_str(v) for v in row]
        if not any(values):  # Bỏ qua dòng trống
            continue
        data.append({h: v for h, v in zip(headers, values) if h})
    return data


# Mẫu biến trong kịch bản: ${ten_bien}
VARIABLE_PATTERN = re.compile(r"\$\{\s*(\w+)\s*\}")


def substitute(text: str, data: dict) -> str:
    """Thay các biến ${ten_bien} trong chuỗi bằng giá trị trong data.
    Biến không có trong data được giữ nguyên để người dùng dễ phát hiện."""
    return VARIABLE_PATTERN.sub(lambda m: data.get(m.group(1), m.group(0)), text)


def _uses_variables(case: TestCase) -> bool:
    """Test case có dùng biến ${...} ở cột Selector, Giá trị hoặc Mô tả hay không."""
    return any(VARIABLE_PATTERN.search(f"{s.selector} {s.value} {s.description}") for s in case.steps)


def expand_data_driven(cases: list[TestCase], data: list[dict]) -> list[TestCase]:
    """
    Kiểm thử hướng dữ liệu: với mỗi test case có dùng biến, tạo ra N bản sao
    (N = số dòng của sheet DATA), mỗi bản sao thay biến bằng dữ liệu của một dòng.
    Test case không dùng biến thì giữ nguyên, chạy một lần.
    """
    if not data:
        return cases
    expanded = []
    for case in cases:
        if not _uses_variables(case):
            expanded.append(case)
            continue
        for index, row in enumerate(data, start=1):
            # Lấy giá trị cột đầu tiên làm nhãn để dễ phân biệt các lần chạy
            label = next(iter(row.values()), "") or "(trống)"
            expanded.append(TestCase(
                name=f"{case.name} [#{index}: {label}]",
                steps=[TestStep(s.step_no, s.keyword, substitute(s.selector, row),
                                substitute(s.value, row), substitute(s.description, row))
                       for s in case.steps],
                data_row=row,
            ))
    return expanded


def read_suite(file_path: str | Path) -> TestSuite:
    """Đọc toàn bộ file Excel và trả về một TestSuite."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {file_path}")

    wb = load_workbook(file_path, data_only=True, read_only=True)
    suite = TestSuite(name=file_path.stem, file_path=str(file_path))
    for ws in wb.worksheets:
        if ws.title.strip().upper() == DATA_SHEET_NAME:
            suite.data = _read_data_sheet(ws)
        else:
            case = _read_case_sheet(ws)
            if case.steps:  # Chỉ lấy sheet có ít nhất một bước
                suite.cases.append(case)
    wb.close()
    # Nếu có sheet DATA thì nhân bản test case theo từng dòng dữ liệu
    suite.cases = expand_data_driven(suite.cases, suite.data)
    return suite
