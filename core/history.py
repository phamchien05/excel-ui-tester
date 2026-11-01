"""
Lưu và đọc lịch sử các lần chạy, phục vụ trang Tổng quan và so sánh hồi quy.

Mỗi lần chạy ghi thêm file reports/<ngày_giờ>/summary.json chứa thống kê ngắn gọn.
Trang Tổng quan đọc tất cả các file này để vẽ xu hướng và so sánh lần chạy mới nhất
với lần chạy trước của cùng bộ test (test nào mới bị lỗi, test nào đã được sửa).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SUMMARY_FILE = "summary.json"


def save_summary(result, output_dir: str | Path) -> Path:
    """Ghi tóm tắt kết quả (SuiteResult hoặc SmokeResult) ra summary.json."""
    output_dir = Path(output_dir)
    if hasattr(result, "cases"):  # Kết quả chạy bộ test Excel
        data = {
            "type": "suite", "name": result.name, "source": result.file_path, "browser": result.browser,
            "start": result.start_time.isoformat(timespec="seconds"), "duration": round(result.duration, 2),
            "total": result.total, "passed": result.passed, "failed": result.failed, "pass_rate": result.pass_rate,
            "cases": [{"name": c.name, "status": c.status, "duration": round(c.duration, 2), "error": c.error}
                      for c in result.cases],
        }
    else:  # Kết quả kiểm tra nhanh: mỗi hạng mục kiểm tra tính như một "test"
        checks = result.checks
        passed = sum(c["status"] != "FAIL" for c in checks)
        data = {
            "type": "smoke", "name": result.url, "source": result.url, "browser": result.browser,
            "start": result.start_time.isoformat(timespec="seconds"), "duration": round(result.duration, 2),
            "total": len(checks), "passed": passed, "failed": len(checks) - passed,
            "pass_rate": round(passed * 100 / len(checks), 1), "overall": result.overall,
            "cases": [{"name": c["name"], "status": "FAIL" if c["status"] == "FAIL" else "PASS",
                       "duration": 0, "error": c["detail"] if c["status"] == "FAIL" else ""} for c in checks],
        }
    path = output_dir / SUMMARY_FILE
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_history(reports_dir: str | Path, limit: int = 100) -> list[dict]:
    """Đọc các summary.json trong thư mục reports, mới nhất đứng đầu. File hỏng được bỏ qua."""
    runs = []
    for path in Path(reports_dir).glob(f"*/{SUMMARY_FILE}"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["start"] = datetime.fromisoformat(data["start"])
        except (ValueError, KeyError, OSError):
            continue
        data["dir"] = path.parent
        runs.append(data)
    runs.sort(key=lambda r: r["start"], reverse=True)
    return runs[:limit]


def find_previous(runs: list[dict], run: dict) -> dict | None:
    """Tìm lần chạy liền trước của cùng bộ test (cùng loại, cùng tên). runs đã sắp xếp mới -> cũ."""
    older = [r for r in runs if r["start"] < run["start"] and r["type"] == run["type"] and r["name"] == run["name"]]
    return older[0] if older else None


def compare_runs(new: dict, old: dict) -> dict:
    """
    So sánh hồi quy giữa hai lần chạy:
      new_failures : trước đạt, nay lỗi  -> lỗi hồi quy cần chú ý
      fixed        : trước lỗi, nay đạt
      still_failing: lỗi cả hai lần
      added/removed: test case mới thêm / đã bỏ
    """
    before = {c["name"]: c["status"] for c in old["cases"]}
    after = {c["name"]: c["status"] for c in new["cases"]}
    common = [name for name in after if name in before]
    return {
        "new_failures": [n for n in common if before[n] == "PASS" and after[n] == "FAIL"],
        "fixed": [n for n in common if before[n] == "FAIL" and after[n] == "PASS"],
        "still_failing": [n for n in common if before[n] == "FAIL" and after[n] == "FAIL"],
        "added": [n for n in after if n not in before],
        "removed": [n for n in before if n not in after],
    }
