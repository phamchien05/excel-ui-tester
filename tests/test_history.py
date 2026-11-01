"""Kiểm thử lưu/đọc lịch sử chạy và so sánh hồi quy (core/history.py)."""

import json
from datetime import datetime

from core.history import SUMMARY_FILE, compare_runs, find_previous, load_history, save_summary
from core.runner import CaseResult, SuiteResult
from core.smoke import SmokeResult


def suite(name, start, statuses: dict):
    cases = [CaseResult(n, s, 1.0, error="lỗi" if s == "FAIL" else "") for n, s in statuses.items()]
    return SuiteResult(name, f"{name}.xlsx", "chromium", True, start, start, cases)


def test_luu_va_doc_lai(tmp_path):
    for i, (day, statuses) in enumerate([(1, {"A": "PASS", "B": "PASS"}), (3, {"A": "PASS", "B": "FAIL"}),
                                         (2, {"A": "FAIL", "B": "PASS"})]):
        out = tmp_path / f"run{i}"
        out.mkdir()
        save_summary(suite("bo_test", datetime(2026, 1, day, 9), statuses), out)

    runs = load_history(tmp_path)
    assert [r["start"].day for r in runs] == [3, 2, 1]          # Mới nhất đứng đầu
    latest = runs[0]
    assert (latest["total"], latest["passed"], latest["failed"], latest["pass_rate"]) == (2, 1, 1, 50.0)
    assert latest["cases"][1] == {"name": "B", "status": "FAIL", "duration": 1.0, "error": "lỗi"}
    assert latest["dir"].name == "run1"
    assert load_history(tmp_path, limit=2)[-1]["start"].day == 2


def test_bo_qua_file_hong(tmp_path):
    (tmp_path / "hong").mkdir()
    (tmp_path / "hong" / SUMMARY_FILE).write_text("{không phải json", encoding="utf-8")
    (tmp_path / "thieu").mkdir()
    (tmp_path / "thieu" / SUMMARY_FILE).write_text('{"name": "x"}', encoding="utf-8")
    assert load_history(tmp_path) == []


def test_luu_ket_qua_kiem_tra_nhanh(tmp_path):
    r = SmokeResult("http://x", "chromium", datetime(2026, 1, 1), page_ok=True, status=200, load_time=5)
    save_summary(r, tmp_path)
    run = json.loads((tmp_path / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert run["type"] == "smoke" and run["total"] == 6
    assert run["overall"] == "WARN"           # Tải chậm (5s) chỉ là cảnh báo
    assert run["failed"] == 0 and run["pass_rate"] == 100.0


def test_so_sanh_hoi_quy():
    old = {"cases": [{"name": n, "status": s} for n, s in
                     [("A", "PASS"), ("B", "FAIL"), ("C", "FAIL"), ("D", "PASS")]]}
    new = {"cases": [{"name": n, "status": s} for n, s in
                     [("A", "FAIL"), ("B", "PASS"), ("C", "FAIL"), ("E", "PASS")]]}
    assert compare_runs(new, old) == {"new_failures": ["A"], "fixed": ["B"], "still_failing": ["C"],
                                      "added": ["E"], "removed": ["D"]}


def test_tim_lan_chay_truoc_cung_bo_test():
    runs = [{"type": "suite", "name": n, "start": datetime(2026, 1, d)} for n, d in
            [("A", 5), ("B", 4), ("A", 3), ("A", 1)]]
    assert find_previous(runs, runs[0])["start"].day == 3
    assert find_previous(runs, runs[1]) is None
    assert find_previous(runs, runs[3]) is None
