# Công cụ kiểm thử tự động giao diện Web theo kịch bản Excel

Bài tập lớn môn **Đánh giá và kiểm định chất lượng phần mềm**.

Công cụ cho phép viết kịch bản kiểm thử giao diện Web bằng **file Excel** theo phương pháp
**kiểm thử hướng từ khóa (keyword-driven testing)**: người viết test không cần biết lập trình, chỉ cần
ghi các bước như *mở trang, nhập chữ, bấm nút, kiểm tra kết quả* vào bảng tính. Công cụ sẽ điều khiển
trình duyệt thật (qua Playwright) để thực hiện từng bước và sinh báo cáo HTML.

## Video demo

▶️ **[Xem video demo (Google Drive)](https://drive.google.com/file/d/1vKAFIfoBWd7Cp6PBkj51IsoN5Jeiyb6i/view?usp=sharing)**

Báo cáo bài tập lớn (Word) và hình minh họa nằm trong thư mục [`bao_cao/`](bao_cao/).

## Chức năng chính

| Chức năng | Mô tả |
|---|---|
| Chạy kịch bản Excel | Mỗi file là một bộ test, mỗi sheet là một test case. Hỗ trợ 18 từ khóa. |
| Tự sinh kịch bản | Nhập URL → (đăng nhập trước nếu cần) → quét một hoặc nhiều trang → chọn form/link/dropdown/nút bấm → tự sinh test case theo kỹ thuật thiết kế test, chạy thử để ghi nhận kết quả mong đợi. |
| Ghi lại thao tác | Thao tác trên trình duyệt như người dùng, công cụ ghi thành các bước Excel. |
| Data-driven | Sheet `DATA` chứa nhiều bộ dữ liệu → một kịch bản chạy thành nhiều lần test. |
| Xử lý lỗi | Bước lỗi → dừng test case, ghi lỗi, tự chụp màn hình, chạy tiếp test case sau. |
| Đa trình duyệt | Chromium, Firefox, WebKit; chạy ẩn (headless) hoặc hiện trình duyệt. |
| Kiểm tra nhanh bằng link | Chỉ nhập URL: kiểm tra tải trang, link hỏng, ảnh lỗi/thiếu alt, lỗi JavaScript, chụp ảnh 3 kích thước màn hình. |
| Báo cáo HTML | Tổng quan, biểu đồ tròn pass/fail, chi tiết từng bước, ảnh chụp lỗi. Một file duy nhất, mở trực tiếp bằng trình duyệt. |
| Kết quả Excel | File `ket_qua.xlsx` theo mẫu test case: ID, các bước, dữ liệu, kết quả mong đợi, kết quả thực tế, trạng thái. |
| Unit test | 170 test tự động cho chính công cụ (pytest), độ phủ câu lệnh 96,1%, độ phủ nhánh 91,6%. |
| Giao diện Web | Streamlit với 5 tab: Tổng quan (dashboard lịch sử + so sánh hồi quy), Chạy kịch bản, Tạo kịch bản, Kiểm tra nhanh, Hướng dẫn. |

## Cấu trúc thư mục

```
ui-test-tool/
├── app.py                  # Giao diện Streamlit
├── main.py                 # Chạy bằng dòng lệnh
├── core/
│   ├── reader.py           # Đọc Excel, xử lý data-driven (thay biến ${...})
│   ├── keywords.py         # Định nghĩa các từ khóa
│   ├── runner.py           # Chạy test case, đo thời gian, chụp ảnh khi lỗi
│   ├── smoke.py            # Kiểm tra nhanh bằng link
│   ├── reporter.py         # Sinh báo cáo HTML bằng Jinja2
│   ├── generator.py        # Quét trang + tự sinh test case
│   ├── recorder.py         # Ghi lại thao tác thành kịch bản
│   ├── writer.py           # Ghi test case ra file Excel
│   ├── excel_report.py     # Xuất kết quả chạy ra Excel theo mẫu test case
│   ├── history.py          # Lưu lịch sử chạy (summary.json), so sánh hồi quy giữa hai lần chạy
│   └── dom.py              # JavaScript dùng chung: sinh selector, lấy nhãn phần tử
├── templates/
│   ├── base.html           # Khung + CSS chung của báo cáo
│   ├── report.html         # Báo cáo chạy kịch bản
│   └── smoke_report.html   # Báo cáo kiểm tra nhanh
├── testcases/
│   ├── tao_file_mau.py             # Script sinh các file Excel mẫu
│   ├── saucedemo.xlsx              # 13 test case cho https://www.saucedemo.com
│   ├── dang_nhap_data_driven.xlsx  # Ví dụ data-driven (7 bộ tài khoản)
│   └── tu_sinh_saucedemo.xlsx      # Ví dụ file do công cụ tự sinh
├── tests/                  # Unit test cho chính công cụ
│   ├── site/               # Website thử nghiệm (chạy trên server cục bộ, không cần Internet)
│   ├── conftest.py         # Bật web server cục bộ, hàm tiện ích tạo Excel
│   └── test_*.py           # Test cho từng module trong core/
├── reports/                # Kết quả: reports/<ngày_giờ>/report.html + ket_qua.xlsx + screenshots/
├── requirements.txt
├── requirements-dev.txt    # pytest, pytest-cov
├── pytest.ini, .coveragerc # Cấu hình unit test và đo độ phủ
└── README.md
```

## Cài đặt

Yêu cầu **Python 3.10 trở lên**.

```bash
pip install -r requirements.txt
playwright install            # tải Chromium, Firefox, WebKit (cần cho lựa chọn trình duyệt trên giao diện)
# hoặc chỉ tải Chromium cho nhẹ:  playwright install chromium
```

> Trên Windows nếu lệnh `pip`/`playwright` không nhận, dùng `python -m pip ...` và `python -m playwright install`.

Tạo lại các file Excel mẫu (đã có sẵn, chỉ cần khi muốn sinh lại):

```bash
python testcases/tao_file_mau.py
```

## Cách chạy

### 1. Giao diện Web (Streamlit)

```bash
streamlit run app.py
```

Trình duyệt sẽ mở `http://localhost:8501`:

- **Tab "Chạy kịch bản"**: tải file Excel lên (hoặc chọn file mẫu), chọn trình duyệt, bật/tắt headless,
  bấm **Chạy kiểm thử**. Kết quả hiện theo thời gian thực, cuối cùng có biểu đồ và nút **Tải báo cáo HTML**.
- **Tab "Tạo kịch bản"**: tự sinh file Excel bằng cách quét trang hoặc ghi lại thao tác (xem mục bên dưới).
- **Tab "Kiểm tra nhanh"**: nhập URL, bấm **Kiểm tra**.
- **Tab "Hướng dẫn"**: cách viết file Excel và danh sách từ khóa.

### 2. Dòng lệnh

```bash
# Chạy bộ test (mặc định Chromium, headless)
python main.py testcases/saucedemo.xlsx

# Chạy bằng Firefox, hiện cửa sổ trình duyệt, thời gian chờ 15 giây
python main.py testcases/saucedemo.xlsx --browser firefox --headed --timeout 15

# Chạy bộ test data-driven
python main.py testcases/dang_nhap_data_driven.xlsx

# Kiểm tra nhanh một trang web chỉ bằng URL
python main.py --smoke https://the-internet.herokuapp.com/broken_images

# Tự sinh kịch bản từ URL (khai báo giá trị hợp lệ cho các ô bằng --valid)
python main.py --generate https://www.saucedemo.com --valid "#user-name=standard_user" --valid "#password=secret_sauce"

# Đăng nhập trước rồi quét nhiều trang (thêm trang chỉ mở được bằng nút bấm bằng --extra-url)
python main.py --generate https://www.saucedemo.com/inventory.html --login-url https://www.saucedemo.com                --username standard_user --password secret_sauce --crawl 5                --extra-url https://www.saucedemo.com/checkout-step-one.html

# Ghi lại thao tác thành file Excel
python main.py --record https://www.saucedemo.com -o testcases/ghi_lai.xlsx
```

| Tham số | Ý nghĩa |
|---|---|
| `file` | Đường dẫn file Excel |
| `--smoke URL` | Kiểm tra nhanh một URL (thay cho file Excel) |
| `--generate URL` | Quét trang và tự sinh file Excel kịch bản |
| `--valid SELECTOR=GIÁ_TRỊ` | Giá trị hợp lệ cho một ô khi dùng `--generate` (dùng nhiều lần được) |
| `--record URL` | Mở trình duyệt, ghi lại thao tác thành file Excel |
| `--output`, `-o` | File Excel đầu ra cho `--generate` / `--record` |
| `--login-url`, `--username`, `--password` | `--generate`: đăng nhập trước khi quét (công cụ tự tìm form đăng nhập) |
| `--setup-file`, `--setup-case` | `--generate`: dùng một test case trong file Excel làm bước chuẩn bị (VD: kịch bản đăng nhập đã ghi lại) |
| `--crawl N` | `--generate`: quét tối đa N trang theo link cùng website |
| `--extra-url URL` | `--generate`: thêm trang cần quét, dùng nhiều lần được |
| `--browser`, `-b` | `chromium` (mặc định), `firefox`, `webkit` |
| `--headed` | Hiện cửa sổ trình duyệt (mặc định chạy ẩn) |
| `--timeout`, `-t` | Thời gian chờ tối đa mỗi thao tác, giây (mặc định 10) |
| `--reports` | Thư mục gốc chứa báo cáo (mặc định `reports`) |

Kết quả mẫu:

```
Bộ test: saucedemo  |  Số test case: 13  |  Trình duyệt: chromium (headless)
----------------------------------------------------------------------
[1/13] ✔ PASS  TC01 Đăng nhập thành công  (0.82s)
...
[13/13] ✘ FAIL  TC13 Cố ý sai - Giá sản phẩm  (10.74s)
        └─ Bước 7 (assert_text): Mong đợi '.inventory_item_price' chứa văn bản "$19.99" nhưng thực tế là "$29.99"
----------------------------------------------------------------------
Tổng: 13  |  Pass: 12  |  Fail: 1  |  Tỷ lệ pass: 92.3%  |  Thời gian: 22.23s
Báo cáo HTML: ...\reports\2026-10-28_00-22-12\report.html
```

Lệnh trả về mã thoát `0` nếu tất cả pass và `1` nếu có test lỗi, nên có thể dùng trong CI/CD.

### Kết quả sau mỗi lần chạy

Thư mục `reports/<ngày_giờ>/` gồm:

| File | Nội dung |
|---|---|
| `report.html` | Báo cáo trực quan: biểu đồ, chi tiết từng bước, ảnh lỗi nhúng sẵn |
| `ket_qua.xlsx` | Kết quả theo mẫu test case, dán thẳng vào tài liệu kiểm thử. Sheet **Tổng quan**, **Test case** (ID, Tên, Dữ liệu, Các bước thực hiện, Kết quả mong đợi, Kết quả thực tế, Trạng thái, Thời gian, Ảnh lỗi), **Chi tiết bước** |
| `screenshots/` | Ảnh chụp khi lỗi và ảnh do từ khóa `screenshot` tạo |
| `summary.json` | Tóm tắt lần chạy, dùng cho tab **Tổng quan** (lịch sử, biểu đồ xu hướng, so sánh với lần chạy trước) |

Trên giao diện web có nút **📊 Tải kết quả Excel** bên cạnh nút tải báo cáo HTML.

## Cách viết file Excel

- Mỗi **file** là một bộ test, mỗi **sheet** là một test case (**tên sheet = tên test case**).
- Dòng đầu của sheet là tiêu đề gồm 5 cột:

| Bước | Từ khóa | Selector | Giá trị | Mô tả |
|---|---|---|---|---|
| 1 | open | | https://www.saucedemo.com | Mở trang đăng nhập |
| 2 | type | #user-name | standard_user | Nhập tên đăng nhập |
| 3 | type | #password | secret_sauce | Nhập mật khẩu |
| 4 | click | #login-button | | Bấm nút Login |
| 5 | assert_url | | inventory.html | Đã vào trang sản phẩm |
| 6 | assert_text | .title | Products | Tiêu đề là Products |

- Dòng không có từ khóa sẽ bị bỏ qua. Từ khóa không phân biệt hoa thường.

### Cách viết Selector

| Kiểu | Ví dụ | Ý nghĩa |
|---|---|---|
| Theo id | `#login-button` | Phần tử có `id="login-button"` |
| Theo class | `.inventory_item` | Phần tử có `class="inventory_item"` |
| Theo thuộc tính | `[data-test="error"]` | Phần tử có `data-test="error"` |
| Theo chữ hiển thị | `text=Add to cart` | Phần tử chứa chữ "Add to cart" (cú pháp của Playwright) |

Nếu selector khớp nhiều phần tử, công cụ dùng phần tử **đầu tiên**.

### Data-driven (kiểm thử hướng dữ liệu)

1. Thêm một sheet tên **`DATA`**. Dòng đầu là tên biến, mỗi dòng sau là một bộ dữ liệu:

   | truong_hop | username | password | selector_kiem_tra | ket_qua_mong_doi |
   |---|---|---|---|---|
   | Tài khoản chuẩn | standard_user | secret_sauce | .title | Products |
   | Tài khoản bị khóa | locked_out_user | secret_sauce | [data-test="error"] | locked out |

2. Trong kịch bản, dùng `${ten_bien}` ở cột Selector, Giá trị hoặc Mô tả:

   | Bước | Từ khóa | Selector | Giá trị |
   |---|---|---|---|
   | 2 | type | #user-name | ${username} |
   | 5 | assert_text | ${selector_kiem_tra} | ${ket_qua_mong_doi} |

3. Mỗi dòng DATA chạy thành **một lần test riêng**, tên dạng `Tên test case [#1: Tài khoản chuẩn]`
   (giá trị cột đầu tiên được dùng làm nhãn). Test case không dùng biến vẫn chỉ chạy một lần.

## Danh sách từ khóa

| Từ khóa | Selector | Giá trị | Chức năng |
|---|---|---|---|
| `open` | – | URL | Mở một trang web |
| `click` | bắt buộc | – | Nhấp chuột vào phần tử |
| `type` | bắt buộc | nội dung | Nhập văn bản vào ô (xóa nội dung cũ trước) |
| `clear` | bắt buộc | – | Xóa nội dung ô nhập |
| `select` | bắt buộc | value hoặc nhãn | Chọn một lựa chọn trong ô `<select>` |
| `hover` | bắt buộc | – | Rê chuột lên phần tử |
| `press_key` | tùy chọn | tên phím (`Enter`, `Tab`, `Control+A`...) | Nhấn phím; có selector thì nhấn trên phần tử đó |
| `wait` | – | số giây | Chờ cố định một khoảng thời gian |
| `wait_for` | bắt buộc | số giây tối đa (tùy chọn) | Chờ đến khi phần tử xuất hiện |
| `assert_text` | tùy chọn | văn bản mong đợi | Phần tử (hoặc cả trang nếu bỏ trống selector) có chứa văn bản |
| `assert_value` | bắt buộc | giá trị mong đợi | Giá trị hiện tại của ô nhập / ô chọn bằng đúng giá trị |
| `assert_invalid` | bắt buộc | – | Ô nhập bị trình duyệt đánh dấu không hợp lệ (HTML5 validation chặn gửi form) |
| `assert_no_js_error` | – | – | Trang không phát sinh lỗi JavaScript chưa được bắt (kể từ đầu test case) |
| `assert_visible` | bắt buộc | – | Phần tử đang hiển thị |
| `assert_not_visible` | bắt buộc | – | Phần tử không hiển thị hoặc không tồn tại |
| `assert_url` | – | URL hoặc một phần URL | URL hiện tại có chứa giá trị |
| `assert_title` | – | tiêu đề hoặc một phần | Tiêu đề trang có chứa giá trị |
| `screenshot` | tùy chọn | tên file (tùy chọn) | Chụp ảnh trang (hoặc chỉ phần tử nếu có selector) |

Các từ khóa `assert_...` **tự chờ** đến khi điều kiện đúng hoặc hết thời gian chờ, giúp giảm lỗi chập chờn
khi trang tải chậm.

### Thêm từ khóa mới

Mở `core/keywords.py`, viết một hàm và gắn decorator `@keyword`:

```python
@keyword("double_click", selector="bắt buộc", doc="Nhấp đúp vào phần tử")
def kw_double_click(page, selector, value, ctx):
    _locate(page, selector).dblclick()
```

Từ khóa mới tự động dùng được trong Excel và hiện trong tab Hướng dẫn.

## Tự sinh kịch bản (không cần viết Excel bằng tay)

### Cách 1: Quét trang và tự sinh test case

1. Nhập URL rồi bấm **Quét trang**. Công cụ tìm các form (ô nhập + nút gửi), link điều hướng, dropdown và
   **nút bấm / checkbox / radio đứng riêng** (ngoài form).
   - **Đăng nhập trước khi quét** (cho trang yêu cầu đăng nhập): nhập tài khoản → công cụ tự tìm form đăng nhập
     (ô mật khẩu, ô tên đăng nhập, nút gửi) và **thử đăng nhập ngay** (sai tài khoản thì báo kèm thông báo của trang);
     hoặc chọn một test case có sẵn trong file Excel (VD: kịch bản đăng nhập đã ghi lại). Các bước đăng nhập được
     **chèn vào đầu mọi test case** sinh ra (mỗi test case chạy trên phiên trình duyệt mới).
   - **Phạm vi quét — nhiều trang**: công cụ đi theo link cùng website (tối đa N trang, dùng chung phiên đăng nhập),
     bỏ qua link đăng xuất / xóa / tải file / website khác; các trang cùng khuôn mẫu (`/product/123`, `/product/456`)
     chỉ quét một trang đại diện. Trang chỉ mở được bằng nút bấm (VD: giỏ hàng) thì thêm vào ô **Thêm URL cần quét**.
     Thành phần lặp lại ở nhiều trang (thanh menu, ô tìm kiếm đầu trang) được bỏ chọn sẵn để tránh test trùng.
2. Tick các phần muốn kiểm thử. Với mỗi form, sửa cột **Giá trị hợp lệ** cho đúng với trang
   (VD: tài khoản đăng nhập thật). Công cụ đã đoán sẵn theo loại ô (email, mật khẩu, số điện thoại...).
3. Chọn kỹ thuật thiết kế test rồi bấm **Sinh test case**:

| Kỹ thuật | Test case sinh ra |
|---|---|
| Phân vùng tương đương – hợp lệ | Tất cả ô nhập giá trị hợp lệ |
| Bỏ trống trường | Lần lượt để trống từng ô (ô `required` nếu có), và bỏ trống tất cả |
| Sai định dạng | Email thiếu `@` / thiếu tên miền, số điện thoại có chữ, URL sai, số âm, số thập phân |
| Giá trị biên | Độ dài tại `maxlength`, `maxlength+1`, `minlength-1`, `minlength`; số tại `min-1`, `min`, `max`, `max+1` |
| Ký tự đặc biệt | Chuỗi XSS `<script>`, chuỗi SQL injection `' OR '1'='1' --` |

4. **Tự ghi nhận kết quả mong đợi**: công cụ chạy thử từng test case và quan sát điều xảy ra sau khi gửi form:
   - Chuyển trang → sinh bước `assert_url`.
   - Hiện thông báo mới (lỗi / thành công) → sinh bước `assert_text` với đúng nội dung thông báo.
   - Trình duyệt chặn gửi (HTML5 validation) → sinh bước `assert_invalid`.
   - Trang hiện hộp thoại `alert` khi chèn XSS → cảnh báo nghi ngờ lỗ hổng.
   - Không thấy thay đổi rõ ràng → đánh dấu **cần xem lại**.

5. **Nút bấm, checkbox, radio và link**: công cụ bấm thử rồi ghi nhận theo thứ tự ưu tiên: chuyển trang (URL đích
   thực tế, kể cả chuyển hướng) → thông báo mới → nội dung thay đổi (VD: số trên giỏ hàng 0 → 1) → phần tử mới hiện
   ra (VD: cửa sổ chi tiết). Mỗi test kết thúc bằng bước `assert_no_js_error`: nút nào gây lỗi JavaScript thì test
   **thất bại khi chạy lại** — phát hiện lỗi thật. Nút nguy hiểm (đăng xuất, xóa tài khoản) bị bỏ qua.

Trong file Excel sinh ra, dòng **tô vàng** là kết quả tự ghi nhận, dòng **tô cam** là chỗ cần người kiểm thử tự điền.

> ⚠️ Kết quả tự ghi nhận là **hành vi hiện tại** của trang, không phải là yêu cầu. Nếu trang đang có lỗi
> thì kết quả ghi nhận cũng sai theo. Người kiểm thử cần đối chiếu với tài liệu yêu cầu và sửa lại.
> Khi trang thay đổi về sau, các test case này sẽ phát hiện thay đổi đó (kiểm thử hồi quy).

### Cách 2: Ghi lại thao tác

Bấm **Bắt đầu ghi**. Trình duyệt mở ra, bạn thao tác như người dùng bình thường. Công cụ ghi lại:
click → `click`, nhập chữ → `type` (gõ liên tục vào một ô được gộp thành một bước),
chọn dropdown → `select`, nhấn Enter → `press_key`.

Thanh công cụ ở góc dưới bên phải trình duyệt dùng để chèn bước kiểm tra:
**✔ Kiểm tra chữ** / **👁 Kiểm tra hiển thị** (sau đó bấm vào phần tử), **🔗 Kiểm tra URL**, **⏹ Dừng ghi**.

Cách này hợp với các luồng nghiệp vụ nhiều trang (đăng nhập → giỏ hàng → thanh toán), loại luồng mà cách 1 không tự đoán được.
Sau khi ghi, có thể sửa / xóa / thêm bước ngay trong bảng trên giao diện trước khi lưu.

### Selector được sinh như thế nào

Ưu tiên selector ổn định nhất và kiểm tra selector chỉ khớp đúng 1 phần tử:
`#id` → `[data-test=...]` → `tag[name=...]` → `a[href=...]` → `text="..."` → `[placeholder=...]` / `[aria-label=...]`
→ **theo ảnh bên trong** → đường dẫn CSS.

- Bỏ qua id sinh ngẫu nhiên (chứa dãy số dài) và đường dẫn có mã phiên (VD: `index.htm;jsessionid=AB12...`).
  Mã phiên đổi sau mỗi lần truy cập nên selector chứa nó sẽ hỏng ở lần chạy sau.
- **Link/nút chỉ có ảnh** (VD: logo) dùng thuộc tính của ảnh bên trong, theo thứ tự alt → title → tên file ảnh → class.
  Ví dụ: `a:has(img[alt="ParaBank"])`, `a:has(img[src*="logo.gif"])`, `a:has(img.logo)`.
- Thẻ `<a>` có **kích thước 0** (ảnh bên trong được định vị riêng) thì không bấm trực tiếp được. Khi đó công cụ bấm vào
  ảnh bên trong, ví dụ `a:has(img.logo) img`.
- Đường dẫn CSS có `:nth-of-type(n)` phụ thuộc vào **vị trí** phần tử: thêm hoặc bớt một phần tử là lệch. Bước dùng
  selector loại này được **tô cam "cần xem lại"** trong Excel để người kiểm thử thay bằng selector ổn định hơn.

## Kiểm tra nhanh bằng link

| Hạng mục | Cách kiểm tra | Mức độ |
|---|---|---|
| Tải trang | Mã HTTP < 400 | Lỗi nếu không tải được |
| Thời gian tải | Thời gian đến sự kiện `load` | Cảnh báo nếu > 3 giây |
| Link hỏng | Gửi HEAD (lỗi thì thử GET) tới mọi link `http/https`, song song 10 luồng | Lỗi nếu 4xx, 5xx, timeout |
| Ảnh lỗi | Ảnh đã tải xong nhưng `naturalWidth = 0` (cuộn trang trước để kích hoạt ảnh lazy-load) | Lỗi |
| Ảnh thiếu alt | Ảnh không có thuộc tính `alt` (alt rỗng được coi là ảnh trang trí, hợp lệ) | Cảnh báo |
| Lỗi JavaScript | Thông điệp `error` trong console và lỗi chưa được bắt | Lỗi |
| Ảnh chụp | Toàn trang ở 375px (điện thoại), 768px (tablet), 1366px (máy tính) | – |

## Kiểm thử chính công cụ (unit test)

Công cụ kiểm thử cũng cần được kiểm thử. Bộ test trong thư mục `tests/` chạy trên một **website thử nghiệm
tự viết** (`tests/site/`) được phục vụ bởi web server cục bộ, nên không phụ thuộc Internet và luôn cho kết quả ổn định.

```bash
pip install -r requirements-dev.txt
python -m pytest                                                   # Chạy toàn bộ 170 test (~3–5 phút)
python -m pytest tests/test_reader.py                              # Chỉ chạy một file
python -m pytest --cov --cov-report=term-missing --cov-report=html # Kèm đo độ phủ câu lệnh + nhánh
```

Báo cáo độ phủ HTML nằm ở `reports/coverage/index.html`.

| File test | Kiểm thử | Số test |
|---|---|---|
| `test_reader.py` | Đọc Excel, tên cột Việt/Anh, dòng trống, số 3.0 → "3", sheet DATA, thay biến `${...}` | 12 |
| `test_writer.py` | Ghi/đọc lại Excel, tô màu dòng, tên sheet hợp lệ và không trùng | 6 |
| `test_keywords.py` | Từng từ khóa với trường hợp đúng và sai, thông báo lỗi tiếng Việt | 29 |
| `test_runner.py` | Pass/fail, dừng khi lỗi + chụp ảnh + bỏ qua bước sau, độc lập giữa các test case, data-driven, ghi nhận lỗi JS | 13 |
| `test_reporter.py` | Báo cáo HTML (nhúng ảnh, chống chèn mã HTML), báo cáo kiểm tra nhanh, xuất Excel | 5 |
| `test_smoke.py` | Link hỏng, ảnh hỏng, thiếu alt, lỗi JavaScript, trang 404, không kết nối được | 12 |
| `test_generator.py` | Đoán giá trị hợp lệ, số test case theo kỹ thuật, quét trang, tự ghi nhận kết quả, phát hiện XSS, đăng nhập trước khi quét, quét nhiều trang, nút bấm & phát hiện lỗi JS, selector cho link chỉ có ảnh, đánh dấu selector theo vị trí | 66 |
| `test_recorder.py` | Ghi thao tác thật (gõ, bấm, chọn, thanh công cụ), phát lại kịch bản đã ghi | 10 |
| `test_history.py` | Lưu/đọc lịch sử, bỏ qua file hỏng, so sánh hồi quy (lỗi mới, đã sửa, vẫn lỗi) | 5 |
| `test_browsers.py` | Chạy kịch bản, kiểm tra nhanh, ghi thao tác trên cả Chromium, Firefox, WebKit; báo lỗi dễ hiểu khi chưa cài trình duyệt | 12 |

Kết quả đo độ phủ (170 test, `branch = true` trong `.coveragerc`):

- **Độ phủ câu lệnh** (statement coverage): tỉ lệ dòng lệnh đã được chạy qua.
- **Độ phủ nhánh** (branch coverage): tỉ lệ hướng rẽ của `if/else`, vòng lặp đã được đi qua. Ví dụ mỗi `if` có 2 nhánh: đúng và sai.
- Cột **Tổng hợp** là con số coverage.py in ra, tính chung cả câu lệnh và nhánh: (câu lệnh đã chạy + nhánh đã đi) / (tổng câu lệnh + tổng nhánh).

| Module | Câu lệnh | Chưa chạy | Độ phủ câu lệnh | Nhánh | Nhánh chưa đi | Độ phủ nhánh | Tổng hợp |
|---|---:|---:|---:|---:|---:|---:|---:|
| `dom.py` | 10 | 0 | 100% | 4 | 0 | 100% | 100% |
| `history.py` | 35 | 0 | 100% | 4 | 0 | 100% | 100% |
| `reporter.py` | 28 | 0 | 100% | 2 | 0 | 100% | 100% |
| `writer.py` | 52 | 0 | 100% | 18 | 0 | 100% | 100% |
| `excel_report.py` | 74 | 0 | 100% | 24 | 2 | 91,7% | 98,0% |
| `reader.py` | 108 | 2 | 98,1% | 38 | 2 | 94,7% | 97,3% |
| `keywords.py` | 133 | 4 | 97,0% | 14 | 0 | 100% | 97,3% |
| `runner.py` | 148 | 4 | 97,3% | 22 | 2 | 90,9% | 96,5% |
| `generator.py` | 564 | 24 | 95,7% | 196 | 16 | 91,8% | 94,7% |
| `smoke.py` | 194 | 13 | 93,3% | 38 | 8 | 78,9% | 90,9% |
| `recorder.py` | 85 | 9 | 89,4% | 34 | 3 | 91,2% | 89,9% |
| **Tổng** | **1431** | **56** | **96,1%** | **394** | **33** | **91,6%** | **95,1%** |

Phần chưa phủ chủ yếu là các nhánh xử lý ngoại lệ hiếm gặp: server không hỗ trợ HEAD, chụp ảnh lỗi thất bại,
người dùng đóng trình duyệt giữa chừng khi ghi thao tác...

Độ phủ trên **chỉ đo mã Python**. Đoạn JavaScript nạp vào trang (sinh selector, quét trang, so sánh DOM) không được
coverage.py đo. Phần này được kiểm thử gián tiếp qua các test chạy trên trình duyệt thật với website thử nghiệm.

> 💡 Trong quá trình viết unit test đã phát hiện một lỗi thật của công cụ: chức năng kiểm tra nhanh kiểm tra cả
> link neo `#...` trỏ về chính trang đang kiểm tra (thừa). Lỗi đã được sửa và có test để tránh tái phát.

## Kiến trúc và luồng xử lý

```
 File Excel ──► reader.py ──► TestSuite ──► runner.py ──► SuiteResult ──► reporter.py ──► report.html
  (sheet,        (đọc sheet,     (danh sách     (mở trình duyệt,  (kết quả,       (Jinja2 +
   DATA)          thay ${..})     test case)     tra KEYWORDS)     thời gian,      ảnh base64)
                                                     │             ảnh lỗi)
                                                     ▼
                                               keywords.py
                                         (open, click, assert_...)
```

- **Độc lập giữa các test case**: mỗi test case dùng một `browser context` mới (giống cửa sổ ẩn danh),
  không dùng chung cookie hay localStorage.
- **Báo cáo một file**: ảnh chụp được nhúng base64 vào HTML nên gửi file cho người khác vẫn xem đủ ảnh.
