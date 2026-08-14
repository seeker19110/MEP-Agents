# Đặc tả bổ sung — Tầng công cụ của AI (AI → TOOLS)

Tài liệu này soi **một lát cắt duy nhất** của hệ thống: tám nhóm công cụ mà AI dựa vào để
chạm được vào dữ liệu thật.

```
AI
 ↓
TOOLS
 ├── DXF parser
 ├── DWG converter
 ├── AutoCAD
 ├── OCR
 ├── PDF parser
 ├── Excel
 ├── Calculator
 └── Database
```

Nó **không** thay [`DAC_TA_HE_THONG.md`](DAC_TA_HE_THONG.md) (đặc tả mã đang chạy) mà nối
tiếp: mục 1 đối chiếu tám nhóm trên với mã hiện có, mục 2 là các lỗ hổng **đã kiểm chứng
bằng cách đọc code**, mục 3 trở đi là đặc tả cho phần còn thiếu.

**Ngày viết:** 2026-08-13. **Cơ sở đối chiếu:** 61 module `src/`, `tools.py` ở mốc 90 tool.

Ba nguyên tắc của dự án chi phối toàn bộ tài liệu này, nhắc lại vì mục 2 chủ yếu là các
chỗ vi phạm chúng:

1. **LLM không sinh số kỹ thuật** — công cụ phải trả về số, không để AI ước lượng.
2. **Không bỏ sót âm thầm** — thiếu dữ liệu phải kêu lên trong *kết quả trả về*, không
   phải trong log.
3. **Mọi đường dẫn qua `resolve_safe_path`** — không có ngoại lệ cho tool mới.

---

## 1. Hiện trạng tám nhóm

| Nhóm | Mã hiện có | Mức phủ | Kết luận |
|---|---|---|---|
| **DXF parser** | `cad_loader.py`, `cad_geometry.py`, `cad_cache.py`, `cad_*_ops.py` (14 module) | ~90% | Chín. Đọc, sửa, XREF, revision, cache theo mtime. Không có việc lớn phải làm. |
| **DWG converter** | `cad_loader.py::convert_dwg_to_dxf` (ODA File Converter) | ~40% | **Một chiều**. Đọc được `.dwg`, nhưng không ghi ra `.dwg` — sản phẩm giao khách luôn là `.dxf`. |
| **AutoCAD** | `autocad/autoboq.py` + `AUTOBOQ.lsp` (plugin đẩy lên API) | ~25% | Chỉ có chiều **AutoCAD → hệ thống**. AI không điều khiển được phiên AutoCAD đang mở. `pywin32` khai trong `pyproject.toml` nhưng `src/` không dùng dòng nào. |
| **OCR** | `ocr_tools.py` — `ocr_image`, `ocr_pdf_pages`, `ocr_title_block` | ~70% | Có engine cắm được (`register_ocr_engine`), đánh dấu chữ không chắc, cảnh báo bắt buộc. Chưa chạy thử với Tesseract thật. |
| **PDF parser** | `tools.py::read_pdf` (pypdf) | ~30% | Đã phát hiện được bản scan, chọn được khoảng trang, cắt có khai báo. Vẫn chưa: rút bảng, hình học vector, OCR. |
| **Excel** | `tools.py::read_excel`/`write_excel`, `qs_tools.py`, `panel_schedule.py`, `boq_diff.py` | ~55% | Đường **ghi BOQ** tốt (xlsxwriter, định dạng VN). Đường **đọc** đã nêu tên sheet chưa đọc và phân trang được; chưa có ghi nhiều sheet, chưa có revision. |
| **Calculator** | `tools.py::calculate` (AST an toàn), `execute_python_code` (sandbox) | ~50% | An toàn nhưng **không biết đơn vị**. Mọi phép quy đổi CFM↔m³/h, HP↔kW hiện do LLM tự làm trong đầu — vi phạm nguyên tắc 1. |
| **Database** | `unit_prices.csv`, `equipment_catalog.json`, Postgres (chỉ cho checkpoint + pgvector) | ~30% | Không có tool truy vấn nào cho agent. Dữ liệu tra cứu nằm ở file phẳng, nạp nguyên bảng vào RAM. |

Hai nhóm chín (DXF parser, và một phần Excel-ghi) chiếm phần lớn công sức đã bỏ ra. Sáu
nhóm còn lại là nơi cần đặc tả.

---

## 2. Lỗ hổng đã kiểm chứng

Mỗi mục dưới đây trỏ tới dòng code thật. Ba mục đầu là **vi phạm nguyên tắc "không bỏ sót
âm thầm"** — nghĩa là hệ thống có thể trả về một kết quả *trông hoàn chỉnh* trong khi đã bỏ
mất dữ liệu — và **đã được sửa**; mô tả giữ nguyên để biết vì sao luật hiện tại là như vậy.

### 2.1 🔴 PDF bản scan trả về rỗng, không một lời cảnh báo ✅ Đã sửa

`src/tools.py:333-343` — `read_pdf` gọi `PdfReader` rồi nối `page.extract_text()`. Với một
bản vẽ scan hoặc hồ sơ thầu photo (rất phổ biến trong hồ sơ MEPF Việt Nam), `extract_text()`
trả về chuỗi rỗng cho **mọi trang**. Tool trả về:

```
Nội dung PDF (48 trang): ...
```

48 trang, không chữ nào, và định dạng vẫn đúng. LLM đọc chuỗi này hoàn toàn có thể kết
luận "file không có nội dung" rồi đi tiếp. Đây là kiểu sai lệch tốn kém nhất mà dự án đã
tự cấm.

### 2.2 🔴 `read_pdf` cắt ở 5000 ký tự và luôn dán `...` ✅ Đã sửa

Cùng chỗ: `return f"Nội dung PDF ({len(reader.pages)} trang):\n{text[:5000]}..."`. Hai lỗi
chồng nhau — dấu `...` được dán **kể cả khi không cắt** (nên không phân biệt được), và khi
cắt thật thì không nói mất bao nhiêu. Một bảng thống kê vật tư ở trang 30 biến mất không
dấu vết.

### 2.3 🔴 `read_excel` đọc đúng **một** sheet, không nói là còn sheet khác ✅ Đã sửa

`src/tools.py:269-277` — `pd.read_excel(path)` mặc định `sheet_name=0`. File BOQ của nhà
thầu thường có `TONG HOP`, `DIEN`, `NUOC`, `PCCC`, `DHKK` trên năm sheet. Tool đọc sheet
đầu rồi trả về như thể đó là toàn bộ file. Kèm theo `df.to_string()` không giới hạn dòng:
một sheet 8000 dòng nhồi thẳng vào context.

### 2.4 🟠 Không có đường ghi ra `.dwg`

`cad_loader.py:60-92` gọi ODA với tham số cố định `"ACAD2018", "DXF"`. Chiều ngược lại
không tồn tại, dù ODA File Converter làm được. Hệ quả nghiệp vụ: agent sửa bản vẽ xong,
khách nhận `.dxf`, mở bằng AutoCAD thì mất một phần thuộc tính riêng của DWG và khác quy
trình lưu trữ của họ. Ngoài ra cờ audit đang bật (`"1"`) nhưng **báo cáo audit bị vứt đi**
— `subprocess.run` bắt `stdout` rồi không đọc.

### 2.5 🟠 `calculate` không biết đơn vị

`src/tools.py:248-256` phân tích AST rồi tính số học thuần. Không có bảng đơn vị. Khi
catalog ghi *2000 CFM* còn tool ống gió nhận m³/h, khâu quy đổi rơi vào LLM. Nguyên tắc 1
của dự án nói rõ LLM không được sinh số kỹ thuật — một hệ số 1.699 nhớ nhầm thành 1.7 thì
không ai thấy, nhưng nó đi thẳng vào tiết diện ống.

### 2.6 🟠 Không có tool truy vấn dữ liệu

`lookup_unit_price` (`qs_tools.py:213`) nạp **toàn bộ** bảng giá rồi lặp Python + fuzzy;
`lookup_equipment_catalog` (`tools.py:1558`) `json.load` cả catalog rồi so khớp bằng
`kw in str(eq).lower()` — tức là so khớp cả trên tên khóa JSON, nên `"type"` hay `"kw"`
gõ vào cũng khớp mọi bản ghi. Không có đường đặt câu hỏi có điều kiện ("bơm có lưu lượng
≥ 50 m³/h **và** cột áp 30–40 m").

### 2.7 🟡 Ghi Excel không có revision, trong khi ghi CAD thì có

`write_excel` (`tools.py:279-297`) ghi đè thẳng. Bản vẽ được `cad_revision.py` giữ 3 bản
trước khi ghi đè; bảng khối lượng — thứ mang con số tiền — thì không. Bất đối xứng này
không có lý do kỹ thuật.

### 2.8 🟡 Không có đường vào AutoCAD đang chạy

Có những việc `ezdxf` không làm được vì bản chất: giải các đối tượng proxy do ứng dụng
dựng hình (Civil 3D, MEP) sinh ra, xuất PDF theo đúng layout/CTB của khách, chạy lệnh
`AUDIT`/`OVERKILL` của chính AutoCAD. Hiện không có tool nào chạm tới.

---

## 3. Đặc tả bổ sung

Bốn ràng buộc chung, áp cho **mọi** tool mô tả dưới đây (kế thừa mục 5.2 của đặc tả hệ
thống, không được nới):

- **Hợp đồng trả về:** chuỗi tiếng Việt tự giải thích được. Lỗi là *kết quả*, không phải
  exception — kèm hướng khắc phục cụ thể.
- **Đường dẫn:** `resolve_safe_path` trước mọi thao tác file, không ngoại lệ.
- **Trần độ dài, và phải khai báo:** mỗi tool tự đặt trần đầu ra. Khi cắt, dòng cuối
  **bắt buộc** ghi rõ dạng `[Đã cắt: hiển thị 120/3480 dòng. Dùng tham số `offset` để đọc
  tiếp.]` — nghĩa là cắt phải kèm **đường đọc tiếp**, không chỉ kèm lời xin lỗi.
- **Đăng ký tường minh:** thêm tool = sửa `TOOLS_BY_ROLE` + `tools` trong `src/tools.py`.
  Không gán đè module khác (xem `TECH_DEBT.md` mục 10).

### 3.1 OCR — `src/ocr_tools.py` ✅ Đã làm *(chưa chạy thử với engine thật)*

**Vì sao trước tiên:** lỗ hổng 2.1 nay đã *phát hiện* được bản scan, nhưng vẫn chưa *đọc* được nó — OCR là mảnh còn thiếu, và là điều kiện cần của PDF parser (3.2) lẫn
việc đọc raster nhúng trong DXF.

**Chọn engine.** Ba lựa chọn được cân nhắc:

| Engine | Ưu | Nhược | Kết luận |
|---|---|---|---|
| Tesseract + `pytesseract` | Nhẹ, có gói `vie` chính thức, chạy offline | Kém trên chữ xoay/nghiêng, kém trên chữ trong bản vẽ | **Mặc định** |
| PaddleOCR | Mạnh trên bố cục lộn xộn, có nhận diện bảng | Nặng (~500MB), kéo theo paddle | **Tùy chọn** `--extra ocr-heavy` |
| API đám mây | Chính xác nhất | Đẩy bản vẽ khách ra ngoài | **Loại** — khách MEPF thường ràng buộc bảo mật (xem `TECH_DEBT.md` mục 2) |

Đi theo đúng nguyên tắc "graceful fallback": không có engine nào → tool trả về hướng dẫn
cài đặt, **không** ném lỗi, không sập. Mẫu ngôn từ lấy nguyên từ `ODA_INSTALL_HINT`.

```python
@tool
def ocr_image(file_path: str, lang: str = "vie+eng", psm: int = 6) -> str:
    """Đọc chữ từ ảnh (PNG/JPG/TIFF) hoặc trang PDF đã render, bằng OCR cục bộ."""

@tool
def ocr_pdf_pages(file_path: str, pages: str = "1-5", dpi: int = 300) -> str:
    """OCR các trang PDF bản scan. `pages` dạng '1-5' hoặc '2,7,9'."""

@tool
def ocr_title_block(file_path: str, region: str = "auto") -> str:
    """Đọc khung tên bản vẽ (tên dự án, số hiệu, tỷ lệ, ngày, người duyệt).
    `region='auto'` lấy 1/4 dưới-phải — vị trí khung tên theo TCVN 7285."""
```

**Ràng buộc bắt buộc:**

- **Trả về độ tin cậy, không chỉ chữ.** Mỗi khối text kèm confidence trung bình. Dưới
  ngưỡng `OCR_MIN_CONFIDENCE` (mặc định 60) thì đánh dấu `[?]` ngay trong chuỗi trả về, để
  LLM không coi chữ đoán mò là dữ kiện chắc chắn.
- **Không bao giờ để OCR sinh ra số đi vào BOQ.** Kết quả OCR là *gợi ý cần người xác
  nhận*. Chuỗi trả về phải mở đầu bằng dòng cảnh báo cố định, và tài liệu tool phải nói rõ
  agent không được nối thẳng số OCR vào `calc_boq_cost`. Đây là hệ quả trực tiếp của
  nguyên tắc 1: OCR *là* một mô hình đoán.
- `dpi` mặc định 300, trần 600 — cao hơn không tăng độ chính xác mà tăng RAM tuyến tính.
- ~~Bộ nhớ đệm dùng lại `cad_cache`~~ — **không làm**: `cad_cache.readfile_cached` trả về
  một `ezdxf` document, API của nó gắn chặt với DXF chứ không phải một cache khóa-giá trị
  dùng chung. Ép OCR vào đó là bẻ cong một module đang chạy tốt để tiết kiệm vài dòng.
  Chưa có cache cho OCR; thêm khi đo được là cần.

**Phụ thuộc:** `pytesseract`, `pdf2image`, gói hệ thống `tesseract-ocr`,
`tesseract-ocr-vie`, `poppler-utils`. Vào `[project.optional-dependencies].ocr`, không vào
nhóm chính — cài đặt máy chủ tối thiểu vẫn phải chạy được.

**Test:** OCR trên ảnh chữ do chính test sinh ra bằng Pillow (không cần cố định ảnh mẫu
trong repo); đường thiếu engine trả về hướng dẫn chứ không ném; đường ảnh nằm ngoài
workspace bị chặn; chữ mờ có gắn `[?]`.

### 3.2 PDF parser — nâng cấp `read_pdf`, thêm `src/pdf_tools.py`

Vá 2.1 và 2.2, rồi mở thêm một khả năng mới đáng giá.

```python
@tool
def read_pdf(file_path: str, pages: str = "", max_chars: int = 8000) -> str:
    """Đọc text PDF. `pages` rỗng = toàn bộ. Tự phát hiện bản scan và chỉ sang OCR."""

@tool
def extract_pdf_tables(file_path: str, pages: str = "1") -> str:
    """Rút bảng trong PDF (bảng thống kê vật tư, bảng tải) ra dạng CSV."""

@tool
def extract_pdf_vector_geometry(file_path: str, page: int = 1, scale_hint: str = "") -> str:
    """Rút đường/đa tuyến vector của một trang PDF xuất từ CAD/Revit.
    Dùng khi khách chỉ gửi PDF mà không gửi DWG."""
```

**`read_pdf` phải sửa ba điểm:**

1. Đếm ký tự rút được / số trang. Nếu **≥ 80% số trang** cho ra dưới 20 ký tự → kết luận
   là bản scan, trả về đúng câu: *"PDF này là bản scan (không có lớp text). Dùng
   `ocr_pdf_pages` để đọc."* Không còn khả năng trả về "48 trang" rỗng.
2. Cắt phải khai báo số ký tự đã bỏ và cách đọc tiếp, theo mẫu ở đầu mục 3.
3. Ghi nhãn số trang trong chuỗi trả về (`--- Trang 12 ---`) để agent trích dẫn được.

**`extract_pdf_vector_geometry` — vì sao đáng làm:** PDF xuất từ Revit/AutoCAD giữ nguyên
đường nét dưới dạng vector. Có tỷ lệ (đọc từ khung tên bằng `ocr_title_block`, hoặc do
người dùng đưa qua `scale_hint`) thì đo được chiều dài tuyến ống thật. Đây là đường bóc
khối lượng **duy nhất** khi khách chỉ có PDF — tình huống rất thường gặp ở giai đoạn đấu
thầu. Kết quả bắt buộc mang cảnh báo: *"Khối lượng đo từ PDF, độ chính xác phụ thuộc tỷ lệ
khai báo — cần đối chiếu bản vẽ gốc trước khi chốt hồ sơ."*

**Phụ thuộc:** `pdfplumber` (bảng + vector; dùng chung `pdfminer.six`). `pypdf` giữ lại cho
đường text nhanh.

### 3.3 DWG converter — mở rộng `src/cad_loader.py`

```python
def convert_dxf_to_dwg(dxf_path, version="ACAD2018", timeout=180) -> str: ...
def convert_batch(paths_or_dir, target="DXF", version="ACAD2018") -> list[str]: ...
def audit_report(path) -> str: ...          # đọc log audit ODA thay vì vứt đi
```

- `@tool export_cad_as_dwg(file_path, version)` cho vai trò `cad` — chốt lại chiều giao
  sản phẩm còn thiếu (2.4).
- `version` thành tham số, không hardcode: khách còn dùng AutoCAD 2010 thì `ACAD2018`
  không mở được. Danh sách hợp lệ kiểm ở Python, sai thì báo ngay kèm các giá trị chấp
  nhận được.
- **Chuyển theo lô.** ODA nhận cả thư mục; hiện mỗi lần gọi khởi động lại tiến trình cho
  đúng một file. Một hồ sơ 60 bản vẽ = 60 lần khởi động. `convert_batch` gom một lượt.
- **Đọc báo cáo audit.** Cờ audit đang bật sẵn; chỉ cần đọc `stdout` và đưa cảnh báo lên
  cho người dùng ("3 thực thể lỗi đã được sửa khi chuyển đổi") — nguyên tắc 2 đúng nghĩa.
- **Fallback thứ hai:** thiếu ODA thì thử `dwg2dxf` của LibreDWG nếu có. Vẫn không có thì
  giữ nguyên `ODA_INSTALL_HINT`.

### 3.4 AutoCAD — `src/autocad_bridge.py` *(chỉ Windows)*

Cầu nối COM tới phiên AutoCAD đang mở, làm những việc `ezdxf` không làm được (2.8).

```python
@tool
def autocad_run_command(commands: str, file_path: str = "") -> str:
    """Chạy lệnh AutoCAD (AUDIT, OVERKILL, PURGE) trên bản vẽ đang mở."""

@tool
def autocad_plot_pdf(file_path: str, layout: str = "", ctb: str = "") -> str:
    """Xuất PDF theo đúng layout/CTB của khách."""

@tool
def autocad_explode_proxy(file_path: str) -> str:
    """Giải đối tượng proxy (Civil 3D/AutoCAD MEP) mà ezdxf chỉ thấy là khối mờ."""
```

**Ràng buộc, và chỗ này quan trọng hơn bản thân tính năng:**

- **Danh sách lệnh cho phép, không phải danh sách cấm.** `autocad_run_command` chỉ nhận
  lệnh nằm trong `AUTOCAD_ALLOWED_COMMANDS` (mặc định: `AUDIT`, `PURGE`, `OVERKILL`,
  `RECOVER`, `-PLOT`). Cho AI gõ lệnh tùy ý vào một AutoCAD có quyền ghi đĩa là mở
  `execute_python_code` không sandbox bằng đường vòng. Danh sách trắng là ranh giới không
  được nới bằng cấu hình từ request.
- **Không phải Windows → tool tự vắng mặt**, kèm log một dòng. Không đăng ký một tool luôn
  báo lỗi vào schema của mọi request.
- **Snapshot trước khi chạy lệnh có sửa bản vẽ** (`cad_revision.snapshot_cad`) — giống
  ràng buộc đang áp cho `edit_cad`.
- Timeout cứng cho mọi lệnh COM; AutoCAD hiện hộp thoại chờ là treo vô hạn.

### 3.5 Excel — `src/excel_tools.py`

```python
@tool
def list_excel_sheets(file_path: str) -> str:
    """Liệt kê sheet + kích thước + 3 dòng đầu mỗi sheet."""

@tool
def read_excel(file_path: str, sheet: str = "", max_rows: int = 200,
               offset: int = 0, columns: str = "") -> str:
    """Đọc một sheet. `sheet` rỗng = sheet đầu VÀ cảnh báo nếu file còn sheet khác."""

@tool
def write_excel_multisheet(file_path: str, json_data: str, mode: str = "overwrite") -> str:
    """Ghi nhiều sheet. mode: overwrite (có snapshot) | append | update_sheet."""

@tool
def query_excel(file_path: str, sheet: str, expression: str) -> str:
    """Lọc/tổng hợp bằng biểu thức polars an toàn, không kéo cả bảng vào context."""
```

- Vá 2.3: sheet mặc định vẫn là sheet đầu (giữ tương thích), **nhưng** chuỗi trả về mang
  dòng *"File còn 4 sheet chưa đọc: DIEN, NUOC, PCCC, DHKK."* Bỏ sót thì được, bỏ sót âm
  thầm thì không.
- Phân trang thật (`max_rows`/`offset`) thay cho `to_string()` không trần.
- `query_excel` để đọc file 50k dòng mà không nổ context — đây mới là đường đúng cho các
  bảng lớn; đọc nguyên bảng chỉ hợp với file nhỏ.
- Vá 2.7: `mode="overwrite"` chụp snapshot trước khi ghi đè, dùng lại đúng cơ chế
  `cad_revision.py` chứ không viết cơ chế thứ hai.
- Ô công thức: đọc **giá trị đã tính** (`data_only=True`), và nếu file chưa từng được Excel
  mở (cache công thức rỗng) thì nói ra, thay vì trả `None` lẫn vào số liệu.

### 3.6 Calculator — `src/unit_tools.py`

Vá 2.5, ngăn LLM tự quy đổi.

```python
@tool
def convert_unit(value: float, from_unit: str, to_unit: str) -> str:
    """Quy đổi đơn vị kỹ thuật: CFM↔m3/h, HP↔kW, psi↔bar, BTU/h↔kW, inch↔mm..."""

@tool
def calculate_with_units(expression: str) -> str:
    """Tính có đơn vị: '2000 CFM * 1.2 kg/m3' → kết quả kèm đơn vị dẫn xuất."""
```

- Nền: `pint`, nạp thêm định nghĩa riêng của ngành (RT lạnh = 3.517 kW, TR, cột áp mH₂O).
- **Đơn vị không khớp thì báo lỗi, không tự ép.** Cộng `kW` với `m3/h` phải là lỗi nói rõ
  — đây chính là loại nhầm lẫn mà công cụ cần bắt hộ.
- `calculate` cũ giữ nguyên cho số học thuần; docstring của nó bổ sung một câu chỉ sang
  `calculate_with_units` khi biểu thức có đơn vị. Không đổi hành vi tool đang có test.
- Vào `_COMMON_TOOLS` — mọi bộ phận đều cần quy đổi.

### 3.7 Database — `src/db_tools.py`

Vá 2.6. Phạm vi cố ý hẹp: **chỉ đọc**, và không đụng tới việc migrate hạ tầng đang treo ở
`TECH_DEBT.md` mục 1.

```python
@tool
def query_unit_prices(keyword: str = "", ma_hieu: str = "",
                      don_vi: str = "", limit: int = 20) -> str:
    """Tra bảng đơn giá có điều kiện. Kèm ngày hiệu lực của bảng giá."""

@tool
def query_equipment(equipment_type: str, filters: str = "", limit: int = 10) -> str:
    """Tra catalog có điều kiện số: 'luu_luong>=50 and cot_ap<=40'."""

@tool
def query_project_history(keyword: str, limit: int = 10) -> str:
    """Tra các dự án đã làm để tham chiếu định mức thực tế."""
```

- **Chỉ đọc, và điều kiện là dữ liệu chứ không phải chuỗi SQL.** `filters` được phân tích
  bằng AST giới hạn (dùng lại `_safe_eval_node` của `tools.py`) rồi dịch sang biểu thức
  polars. Không có đường nào để LLM đưa SQL thô xuống backend — kể cả khi backend còn là
  CSV, vì nó sẽ không còn là CSV mãi.
- **Backend cắm được, mặc định là file phẳng.** Cùng khuôn với `standards_backend.py`:
  `register_db_backend(tên, hàm, ưu tiên)`. Có Postgres thì đăng ký backend Postgres, mã
  tool không đổi một dòng. Đây là cách để việc này **không** bị chặn bởi mục nợ hạ tầng.
- `query_unit_prices` bắt buộc nối `unit_price_freshness_note()` vào kết quả — bảng giá quá
  hạn phải nói ra ngay tại chỗ tra, không đợi tới lúc xuất báo cáo.
- Sửa luôn lỗi so khớp của `lookup_equipment_catalog` (2.6): so khớp trên **giá trị** các
  trường đã khai, không trên `str(dict)`.

---

## 4. Thứ tự làm và lý do

Xếp theo *rủi ro nghiệp vụ đang tồn tại*, không theo độ khó.

| # | Hạng mục | Vì sao ở vị trí này | Mục |
|---|---|---|---|
| 1 | ✅ **Đã làm** — vá `read_pdf` + `read_excel` (phát hiện bản scan, cắt có khai báo + đường đọc tiếp, nêu đích danh sheet chưa đọc) | Đang **trả về kết quả sai lệch âm thầm**. Không thêm phụ thuộc. Canh bằng `tests/test_read_silent_truncation.py` (12 test). | 2.1–2.3 |
| 2 | ✅ **Đã làm** — OCR (`src/ocr_tools.py`, 20 test) | Mở khóa nhóm hồ sơ scan — trước đó là vùng mù hoàn toàn. **Chưa chạy thử với Tesseract thật**, xem `TECH_DEBT.md` mục 13. | 3.1 |
| 3 | Đơn vị (`unit_tools`) | LLM đang tự quy đổi số kỹ thuật, trái nguyên tắc 1 | 3.6 |
| 4 | Excel đầy đủ + snapshot | Bảng khối lượng mang con số tiền mà chưa có revision | 3.5 |
| 5 | PDF bảng + hình học vector | Mở đường bóc khối lượng khi khách chỉ có PDF | 3.2 |
| 6 | DWG hai chiều + batch + audit | Chốt chiều giao sản phẩm; cần máy có ODA để chạy thử | 3.3 |
| 7 | Database backend cắm được | Nền cho mục nợ hạ tầng, chưa chặn ai lúc này | 3.7 |
| 8 | Cầu AutoCAD | Giá trị cao nhưng chỉ Windows + cần AutoCAD có bản quyền để kiểm chứng | 3.4 |

**Hạng mục 1 nên đi riêng một PR** và làm trước hết: nó sửa sai lệch đang có, không thêm
phụ thuộc nào, và không phụ thuộc bất kỳ hạng mục nào khác.

---

## 5. Điều kiện nghiệm thu

Một hạng mục chỉ được coi là xong khi đủ **cả năm**:

1. `uv run pytest -q` xanh **toàn bộ**, không riêng test mới. Lỗi ghép module không bao giờ
   lộ ra khi chạy riêng — bài học ở `TECH_DEBT.md` mục 10.
2. Tool mới có mặt trong `tools` **và** trong đúng `TOOLS_BY_ROLE`; có test canh
   (`test_hardening.py::test_known_roles_all_have_explicit_toolsets`).
3. Mọi tool chạm file có test đường **path traversal bị chặn**.
4. Mọi phụ thuộc ngoài (tesseract, ODA, AutoCAD, Postgres) có test đường **thiếu phụ
   thuộc** → trả hướng dẫn cài, không ném exception, không sập.
5. Mọi đường **cắt ngắn / bỏ sót dữ liệu** có test khẳng định cảnh báo nằm trong *chuỗi
   trả về*, không phải trong log.

Chưa chạy thử được (thiếu ODA, thiếu AutoCAD, thiếu GPU) thì **ghi rõ là chưa chạy** trong
`TECH_DEBT.md` — đúng văn hóa sẵn có của repo, không tự nhận đã xong.

---

## 6. Đọc tiếp

- [`DAC_TA_HE_THONG.md`](DAC_TA_HE_THONG.md) — đặc tả mã đang chạy; mục 5 là hợp đồng tool
- [`../TECH_DEBT.md`](../TECH_DEBT.md) — mục 1 (database/lưu trữ), 5 (thị giác máy tính),
  10 (vì sao cấm patch lúc import)
- [`RA_SOAT_LO_HONG.md`](RA_SOAT_LO_HONG.md) — đợt rà soát bảo mật trước
- [`E2E.md`](E2E.md) — cách chạy kiểm thử đầu-cuối
