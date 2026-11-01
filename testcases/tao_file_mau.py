"""
Script tạo các file Excel kịch bản mẫu để kiểm thử trang https://www.saucedemo.com

Chạy:  python testcases/tao_file_mau.py
Kết quả:
  - testcases/saucedemo.xlsx                 : 13 test case chức năng
  - testcases/dang_nhap_data_driven.xlsx     : 1 kịch bản + sheet DATA (nhiều tài khoản)
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

OUT_DIR = Path(__file__).parent
BASE_URL = "https://www.saucedemo.com/"
HEADERS = ["Bước", "Từ khóa", "Selector", "Giá trị", "Mô tả"]
ERROR_BOX = '[data-test="error"]'

# Các bước đăng nhập thành công dùng lại cho nhiều test case.
# Mỗi bước là bộ (từ khóa, selector, giá trị, mô tả)
LOGIN_STEPS = [
    ("open", "", BASE_URL, "Mở trang đăng nhập"),
    ("type", "#user-name", "standard_user", "Nhập tên đăng nhập"),
    ("type", "#password", "secret_sauce", "Nhập mật khẩu"),
    ("click", "#login-button", "", "Bấm nút Login"),
    ("assert_url", "", "inventory.html", "Đã vào trang sản phẩm"),
]

TEST_CASES = {
    "TC01 Đăng nhập thành công": [
        ("open", "", BASE_URL, "Mở trang đăng nhập"),
        ("assert_title", "", "Swag Labs", "Kiểm tra tiêu đề trang"),
        ("type", "#user-name", "standard_user", "Nhập tên đăng nhập hợp lệ"),
        ("type", "#password", "secret_sauce", "Nhập mật khẩu đúng"),
        ("click", "#login-button", "", "Bấm nút Login"),
        ("assert_url", "", "inventory.html", "Chuyển sang trang sản phẩm"),
        ("assert_text", ".title", "Products", "Tiêu đề trang là Products"),
        ("assert_visible", ".inventory_list", "", "Danh sách sản phẩm hiển thị"),
    ],
    "TC02 Đăng nhập sai mật khẩu": [
        ("open", "", BASE_URL, "Mở trang đăng nhập"),
        ("type", "#user-name", "standard_user", "Nhập tên đăng nhập"),
        ("type", "#password", "sai_mat_khau", "Nhập mật khẩu sai"),
        ("press_key", "#password", "Enter", "Nhấn Enter để đăng nhập"),
        ("assert_visible", ERROR_BOX, "", "Hiện hộp thông báo lỗi"),
        ("assert_text", ERROR_BOX, "Username and password do not match", "Nội dung lỗi đúng"),
        ("assert_not_visible", ".inventory_list", "", "Không vào được trang sản phẩm"),
    ],
    "TC03 Bỏ trống tên đăng nhập": [
        ("open", "", BASE_URL, "Mở trang đăng nhập"),
        ("type", "#password", "secret_sauce", "Chỉ nhập mật khẩu"),
        ("click", "#login-button", "", "Bấm nút Login"),
        ("assert_text", ERROR_BOX, "Username is required", "Báo lỗi thiếu tên đăng nhập"),
    ],
    "TC04 Tài khoản bị khóa": [
        ("open", "", BASE_URL, "Mở trang đăng nhập"),
        ("type", "#user-name", "locked_out_user", "Nhập tài khoản bị khóa"),
        ("type", "#password", "secret_sauce", "Nhập mật khẩu"),
        ("click", "#login-button", "", "Bấm nút Login"),
        ("assert_text", ERROR_BOX, "Sorry, this user has been locked out", "Báo lỗi tài khoản bị khóa"),
        ("assert_url", "", BASE_URL, "Vẫn ở trang đăng nhập"),
    ],
    "TC05 Thêm 1 sản phẩm vào giỏ": LOGIN_STEPS + [
        ("click", "#add-to-cart-sauce-labs-backpack", "", "Thêm Sauce Labs Backpack"),
        ("assert_text", ".shopping_cart_badge", "1", "Biểu tượng giỏ hàng hiện số 1"),
        ("assert_visible", "#remove-sauce-labs-backpack", "", "Nút chuyển thành Remove"),
        ("click", ".shopping_cart_link", "", "Mở giỏ hàng"),
        ("assert_text", ".cart_item", "Sauce Labs Backpack", "Sản phẩm có trong giỏ"),
    ],
    "TC06 Thêm nhiều sản phẩm": LOGIN_STEPS + [
        ("click", "#add-to-cart-sauce-labs-backpack", "", "Thêm Backpack"),
        ("click", "#add-to-cart-sauce-labs-bike-light", "", "Thêm Bike Light"),
        ("click", "#add-to-cart-sauce-labs-bolt-t-shirt", "", "Thêm Bolt T-Shirt"),
        ("assert_text", ".shopping_cart_badge", "3", "Giỏ hàng hiện số 3"),
    ],
    "TC07 Xóa sản phẩm khỏi giỏ": LOGIN_STEPS + [
        ("click", "#add-to-cart-sauce-labs-backpack", "", "Thêm Backpack"),
        ("click", "#add-to-cart-sauce-labs-bike-light", "", "Thêm Bike Light"),
        ("click", ".shopping_cart_link", "", "Mở giỏ hàng"),
        ("click", "#remove-sauce-labs-backpack", "", "Xóa Backpack khỏi giỏ"),
        ("assert_not_visible", "text=Sauce Labs Backpack", "", "Backpack không còn trong giỏ"),
        ("assert_visible", "text=Sauce Labs Bike Light", "", "Bike Light vẫn còn"),
        ("assert_text", ".shopping_cart_badge", "1", "Giỏ hàng còn 1 sản phẩm"),
    ],
    "TC08 Sắp xếp theo giá": LOGIN_STEPS + [
        ("select", ".product_sort_container", "lohi", "Sắp xếp giá thấp -> cao"),
        ("assert_text", ".inventory_item_price", "$7.99", "Sản phẩm đầu tiên rẻ nhất ($7.99)"),
        ("select", ".product_sort_container", "Price (high to low)", "Sắp xếp giá cao -> thấp (chọn theo nhãn)"),
        ("assert_text", ".inventory_item_price", "$49.99", "Sản phẩm đầu tiên đắt nhất ($49.99)"),
        ("screenshot", "", "", "Chụp ảnh danh sách đã sắp xếp"),
    ],
    "TC09 Thanh toán thành công": LOGIN_STEPS + [
        ("click", "#add-to-cart-sauce-labs-backpack", "", "Thêm Backpack"),
        ("click", ".shopping_cart_link", "", "Mở giỏ hàng"),
        ("click", "#checkout", "", "Bấm Checkout"),
        ("type", "#first-name", "Nguyen", "Nhập tên"),
        ("type", "#last-name", "Van A", "Nhập họ"),
        ("type", "#postal-code", "100000", "Nhập mã bưu điện"),
        ("click", "#continue", "", "Bấm Continue"),
        ("assert_url", "", "checkout-step-two.html", "Sang bước xác nhận đơn"),
        ("assert_text", ".summary_total_label", "Total", "Hiện tổng tiền"),
        ("click", "#finish", "", "Bấm Finish"),
        ("assert_text", ".complete-header", "Thank you for your order!", "Đặt hàng thành công"),
        ("screenshot", "", "", "Chụp ảnh trang hoàn tất"),
    ],
    "TC10 Thanh toán thiếu thông tin": LOGIN_STEPS + [
        ("click", "#add-to-cart-sauce-labs-backpack", "", "Thêm Backpack"),
        ("click", ".shopping_cart_link", "", "Mở giỏ hàng"),
        ("click", "#checkout", "", "Bấm Checkout"),
        ("type", "#first-name", "Nguyen", "Chỉ nhập tên"),
        ("click", "#continue", "", "Bấm Continue"),
        ("assert_text", ERROR_BOX, "Last Name is required", "Báo lỗi thiếu họ"),
        ("type", "#last-name", "Van A", "Nhập họ"),
        ("type", "#postal-code", "100000", "Nhập mã bưu điện"),
        ("clear", "#first-name", "", "Xóa ô tên"),
        ("click", "#continue", "", "Bấm Continue"),
        ("assert_text", ERROR_BOX, "First Name is required", "Báo lỗi thiếu tên"),
    ],
    "TC11 Đăng xuất": LOGIN_STEPS + [
        ("click", "#react-burger-menu-btn", "", "Mở menu"),
        ("wait_for", "#logout_sidebar_link", "5", "Chờ menu hiện ra"),
        ("click", "#logout_sidebar_link", "", "Bấm Logout"),
        ("assert_visible", "#login-button", "", "Quay về trang đăng nhập"),
        ("assert_not_visible", ".shopping_cart_link", "", "Không còn biểu tượng giỏ hàng"),
    ],
    "TC12 Xem chi tiết sản phẩm": LOGIN_STEPS + [
        ("hover", "text=Sauce Labs Bolt T-Shirt", "", "Rê chuột lên tên sản phẩm"),
        ("click", "text=Sauce Labs Bolt T-Shirt", "", "Bấm vào tên sản phẩm (selector dạng text=)"),
        ("assert_url", "", "inventory-item.html", "Mở trang chi tiết"),
        ("assert_text", ".inventory_details_price", "$15.99", "Giá hiển thị đúng"),
        ("click", "#back-to-products", "", "Quay lại danh sách"),
        ("wait", "", "1", "Chờ 1 giây"),
        ("assert_url", "", "inventory.html", "Đã quay lại trang sản phẩm"),
    ],
    "TC13 Cố ý sai - Giá sản phẩm": LOGIN_STEPS + [
        ("assert_visible", "text=Sauce Labs Backpack", "", "Thấy sản phẩm Backpack"),
        ("assert_text", ".inventory_item_price", "$19.99",
         "CỐ Ý SAI: giá thật là $29.99, dùng để minh họa công cụ phát hiện lỗi"),
        ("click", "#add-to-cart-sauce-labs-backpack", "", "Bước này sẽ bị bỏ qua"),
    ],
}

# ----- Bộ test data-driven: cùng một kịch bản, chạy với nhiều bộ dữ liệu -----
DATA_DRIVEN_CASES = {
    "Đăng nhập nhiều tài khoản": [
        ("open", "", BASE_URL, "Mở trang đăng nhập"),
        ("type", "#user-name", "${username}", "Nhập tên đăng nhập từ sheet DATA"),
        ("type", "#password", "${password}", "Nhập mật khẩu từ sheet DATA"),
        ("click", "#login-button", "", "Bấm nút Login"),
        ("assert_text", "${selector_kiem_tra}", "${ket_qua_mong_doi}", "Kiểm tra kết quả mong đợi"),
    ],
}
# Cột đầu tiên (truong_hop) được dùng làm nhãn cho từng lần chạy trong báo cáo
DATA_ROWS = [
    ["truong_hop", "username", "password", "selector_kiem_tra", "ket_qua_mong_doi"],
    ["Tài khoản chuẩn", "standard_user", "secret_sauce", ".title", "Products"],
    ["Tài khoản lỗi giao diện", "problem_user", "secret_sauce", ".title", "Products"],
    ["Tài khoản chậm", "performance_glitch_user", "secret_sauce", ".title", "Products"],
    ["Tài khoản visual", "visual_user", "secret_sauce", ".title", "Products"],
    ["Tài khoản bị khóa", "locked_out_user", "secret_sauce", ERROR_BOX, "locked out"],
    ["Sai mật khẩu", "standard_user", "sai_mat_khau", ERROR_BOX, "do not match"],
    ["Bỏ trống tên", "", "secret_sauce", ERROR_BOX, "Username is required"],
]

# ----- Định dạng cho đẹp -----
HEADER_FILL = PatternFill("solid", fgColor="2F5597")
HEADER_FONT = Font(bold=True, color="FFFFFF")
COLUMN_WIDTHS = [7, 18, 40, 30, 55]


def style_header(ws, widths):
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
    for i, width in enumerate(widths):
        ws.column_dimensions[chr(ord("A") + i)].width = width
    ws.freeze_panes = "A2"  # Cố định dòng tiêu đề


def write_workbook(path: Path, cases: dict, data_rows: list | None = None):
    wb = Workbook()
    wb.remove(wb.active)  # Bỏ sheet mặc định
    for name, steps in cases.items():
        ws = wb.create_sheet(title=name[:31])  # Excel giới hạn tên sheet 31 ký tự
        ws.append(HEADERS)
        for i, (kw, selector, value, desc) in enumerate(steps, start=1):
            ws.append([i, kw, selector, value, desc])
        style_header(ws, COLUMN_WIDTHS)
    if data_rows:
        ws = wb.create_sheet(title="DATA")
        for row in data_rows:
            ws.append(row)
        style_header(ws, [26] * len(data_rows[0]))
    wb.save(path)
    print(f"Đã tạo {path}")


if __name__ == "__main__":
    write_workbook(OUT_DIR / "saucedemo.xlsx", TEST_CASES)
    write_workbook(OUT_DIR / "dang_nhap_data_driven.xlsx", DATA_DRIVEN_CASES, DATA_ROWS)
