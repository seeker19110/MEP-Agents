# Đặc tả bổ sung — Tầng pipeline: upload → sửa → xuất bản vẽ → bóc khối lượng → dự toán

Tài liệu này là **tầng trên** của [`DAC_TA_TOOL_AI.md`](DAC_TA_TOOL_AI.md). Cái đó nói về
*công cụ* (đọc file gì, bằng thư viện nào); cái này nói về *đường đi của một bộ hồ sơ* qua
hệ thống, và về những bảo đảm phải giữ dọc đường đó.

Nó ra đời từ một đề xuất kiến trúc 18 mục cho pipeline
`upload → audit → sửa → QC → xuất bản vẽ → bóc khối lượng → dự toán`. Mục 1 dưới đây đối
chiếu từng ý với mã hiện có — **có ý đã làm rồi, có ý chỉ làm một nửa, có ý chưa có gì** —
rồi các mục sau đặc tả phần còn thiếu, theo đúng nguyên tắc sẵn có của repo chứ không nhập
khẩu một kiến trúc mới đè lên.

**Ngày viết:** 2026-08-13. **Đối chiếu trên:** 61 module `src/`.

Một điều chỉnh về phạm vi cần nói ngay: kiến trúc gốc lấy ví dụ theo **kết cấu/kiến trúc**
(phòng, cửa, tường, bê tông, cốt thép). Hệ thống này là **MEPF** — đối tượng là tuyến ống,
ống gió, máng cáp, tủ điện, đầu phun. Nguyên tắc chuyển nguyên vẹn; ví dụ thì phải dịch
sang đúng ngành, nếu không sẽ đặc tả cho một sản phẩm khác.

---

## 1. Đối chiếu: cái gì đã có, cái gì chưa

| Ý trong kiến trúc đề xuất | Trạng thái | Địa chỉ trong code |
|---|---|---|
| Giữ file gốc bất biến, revision xếp chồng | 🟡 **một nửa** | `cad_revision.py` — theo **từng file**, giữ tối đa **3** bản (`max_cad_revisions`). Không có khái niệm "bản gốc bất biến" ở mức dự án; bản gốc có thể bị đẩy ra khỏi cửa sổ 3 bản. |
| Phân tích file trước khi gọi AI (units/layer/block/entity) | ✅ **đã có** | `audit_cad_drawing_errors` (`tools.py:900`) + `cad_units.py` (suy đoán đơn vị **có kèm `confidence`**) |
| AI audit phát hiện sai lệch | 🟡 **một nửa** | Audit hiện là **luật hình học trong một bản vẽ**. Không có đối chiếu **chéo bản vẽ ↔ bảng thống kê** — loại lỗi giá trị nhất. |
| Ba mức: auto-fix / hỏi người / để kỹ sư quyết | 🟡 **thô** | Có hai cực: `audit_cad_drawing_errors` (chỉ liệt kê) ↔ `optimize_cad_drawing` (tự xóa/sửa). Không có ngưỡng độ tin cậy, không có ID cho từng lỗi. |
| Người duyệt trước khi áp dụng | 🟡 **thô** | `hil.py` có cổng chờ duyệt, nhưng là **một cờ toàn cục** mở bằng chuỗi "DUYỆT". Không duyệt được **từng lỗi một**. |
| LLM không sửa DWG trực tiếp, chỉ sinh lệnh có cấu trúc | ❌ **chưa** | LLM gọi thẳng `edit_cad`/`optimize_cad_drawing`. Không có đối tượng "operation" tuần tự hóa được để lưu, phát lại, kiểm toán. |
| Sửa xong parse lại và kiểm tra lại | ❌ **chưa** | Tool sửa trả về "thành công" theo kết quả ghi file. Không có vòng đọc lại để xác nhận **ý định** đã đạt. |
| Xuất bản vẽ cuối (DWG/PDF/plot) | 🟡 **một nửa** | Xuất được `.dxf`; chưa xuất `.dwg`, chưa plot PDF theo layout/CTB — xem `DAC_TA_TOOL_AI.md` mục 3.3 và 3.4. |
| Bóc khối lượng từ bản vẽ **đã QC** | ❌ **chưa** | `auto_quantity_takeoff` chạy trên bất kỳ file nào được đưa vào, kể cả bản chưa audit. Không có ràng buộc thứ tự. |
| Engine tính, LLM không tính | ✅ **đã có** | Nguyên tắc gốc của repo; toàn bộ `*_tools.py` |
| Mỗi dòng khối lượng có bằng chứng truy ngược | ❌ **chưa** | Xem mục 2 — **đây là lỗ hổng lớn nhất còn lại.** |
| Đơn giá lưu kèm nguồn + thời điểm | 🟡 **một nửa** | `unit_prices.meta.json` + `unit_price_freshness_note()` có ngày hiệu lực và nguồn; **chưa** phân theo vùng (`TECH_DEBT.md` mục 11) |
| So sánh khối lượng giữa hai lần | ✅ **đã có** | `boq_diff.py` |
| Phân tầng model theo công đoạn | 🟡 **một nửa** | `AI_MODEL_SETUP.md` mô tả chọn model theo vai trò; `config.py` chỉ có **một** `model_name` chung |
| Knowledge graph của dự án | ❌ **chưa** | `networkx` có trong repo nhưng chỉ dùng ở `cad_geometry.py` cho hình học, không phải graph dự án |
| Postgres + object storage + queue | 🟡 **đã viết, chưa chạy thật** | `checkpointer_factory.py`, `storage.py`, `celery_app.py` — lý do treo ghi ở `TECH_DEBT.md` mục 1 |
| Autodesk Platform Services | ❌ **chưa** | Xem mục 7 — cần cân nhắc, không phải chọn mặc định |

Bốn ý ❌ ở giữa bảng (operation có cấu trúc, vòng kiểm tra lại, bằng chứng truy ngược,
đối chiếu chéo) **liên quan với nhau** và cùng phục vụ một câu hỏi duy nhất mà hệ thống
hiện chưa trả lời được:

> *"Vì sao khối lượng này là 127,4 m³?"*

Bốn mục dưới đây là đặc tả cho đúng bốn ý đó, xếp theo thứ tự phụ thuộc.

---

## 2. Bằng chứng truy ngược của khối lượng — `src/takeoff_evidence.py`

**Vì sao đứng đầu:** đây là ranh giới giữa "một công cụ ước lượng" và "một hồ sơ dùng được
để đấu thầu". Nó cũng là hệ quả trực tiếp của nguyên tắc 2 của dự án, đẩy thêm một bước:
không chỉ *nói ra chỗ thiếu*, mà *chứng minh được chỗ đủ*.

Hiện `auto_quantity_takeoff` trả về tổng chiều dài theo layer. Con số đó không mang theo
thông tin nào về việc nó tới từ đâu — không handle thực thể, không tên layout, không file
XREF. Người kiểm toán muốn kiểm chỉ còn cách bóc lại từ đầu.

**Đặc tả.** Mỗi dòng khối lượng phải mang theo một bản ghi bằng chứng:

```python
{
  "hang_muc": "Ống gió tôn tráng kẽm 400x200",
  "khoi_luong": 127.4, "don_vi": "m",
  "nguon": {
     "file": "HVAC-L03.dxf", "sha256": "…", "revision": "rev_004",
     "layout": "TANG 3", "layer": "M-DUCT-SUPPLY",
     "handles": ["2F3A", "2F3B", …],       # handle DXF của từng thực thể
     "xref": "GRID-L03.dwg",
     "he_so_hao_hut": 1.05,
     "phuong_phap": "polyline_length"
  },
  "canh_bao": ["Phụ kiện ống là ước tính hình học, chưa đếm theo thực tế"]
}
```

Ràng buộc:

- **Handle DXF là khóa neo.** `ezdxf` giữ handle bền qua các lần lưu, nên click vào một
  dòng BOQ là highlight được đúng thực thể trên bản vẽ — tính năng có giá trị nhất trong
  toàn bộ đề xuất, và nó khả thi ngay với hạ tầng hiện có, không cần APS.
- **Hash file + revision đi kèm.** Sau này bản vẽ đổi thì hệ thống biết bảng khối lượng
  thuộc về bản vẽ nào. Không có cái này thì `boq_diff.py` chỉ so được hai con số mà không
  biết vì sao lệch.
- **Bằng chứng ghi ra file riêng** (`<tên>.evidence.json` cạnh file Excel), không nhồi vào
  chuỗi trả về của tool. Chuỗi trả về giữ nguyên khuôn hiện tại + một dòng trỏ tới file
  bằng chứng. Đây là điều kiện để không phá 600+ test đang có.
- **Cột "Nguồn" trong Excel BOQ** ghi gọn (`HVAC-L03 / TANG 3 / M-DUCT-SUPPLY / 42 đối
  tượng`); chi tiết handle nằm ở JSON. Người đọc Excel không cần thấy 42 mã hex.
- Tool đọc: `@tool trace_boq_item(evidence_path, hang_muc)` → trả về đúng danh sách nguồn,
  để agent trả lời được câu hỏi kiểm toán mà không phải bóc lại.

**Không làm:** không tính "confidence %" cho khối lượng hình học. Hình học là xác định —
gắn một con số 97% vào nó là tạo ra vẻ khoa học giả. Độ tin cậy chỉ có nghĩa ở chỗ có suy
đoán thật: nhận dạng ký hiệu (YOLO), OCR, suy đoán đơn vị (`cad_units.py` đã làm đúng
cách này).

---

## 3. Lệnh CAD có cấu trúc — `src/cad_operations.py`

Nguyên tắc "LLM không sửa DWG trực tiếp, LLM sinh lệnh, engine thực thi" **thực chất repo
đã theo**: LLM chỉ gọi tool, tool là Python xác định. Cái còn thiếu không phải ranh giới
đó, mà là **dấu vết**: lệnh không được lưu lại dưới dạng dữ liệu, nên không phát lại được,
không kiểm toán được, không hoàn tác chọn lọc được.

```python
@dataclass(frozen=True)
class CadOperation:
    op: str                    # "SET_LAYER" | "CHANGE_DUCT_SIZE" | "PURGE_DUPLICATE" …
    target: dict               # {"layer": "M-DUCT-*", "size": "400x200"}
    params: dict
    scope: dict                # {"file": "HVAC-L03.dxf", "layouts": ["TANG 3"]}
    confidence: float
    nguon: str                 # "rule:duplicate_text" | "llm" | "user"
```

- Mọi tool sửa CAD **ghi log operation** vào `<bản vẽ>.oplog.jsonl` trước khi ghi file.
  Revision hiện chỉ lưu *ảnh chụp trạng thái*; oplog lưu *ý định*. Có cả hai mới trả lời
  được "revision 004 đã đổi cái gì, do ai yêu cầu, theo lệnh nào".
- **Chạy khô** (`dry_run=True`) trả về danh sách thực thể sẽ bị đụng tới mà không ghi gì.
  Đây là điều kiện để có nút "xem trước khi áp dụng" ở giao diện.
- **Danh mục `op` là đóng.** Thêm loại lệnh mới = thêm code Python, không phải là để LLM
  tự nghĩ ra tên lệnh. Đây chính là ranh giới ngăn `execute_python_code` quay lại bằng
  đường vòng.
- `nguon` bắt buộc: phân biệt được sửa do luật xác định, do LLM đề xuất, hay do người dùng
  yêu cầu — thông tin quyết định khi có tranh chấp.

---

## 4. Ba mức độ tin cậy và duyệt theo từng lỗi

Hiện hệ thống có hai cực: liệt kê tất cả, hoặc sửa tất cả. Đề xuất chia ba mức là đúng, và
áp được lên `audit_cad_drawing_errors` mà không viết lại nó.

| Mức | Ngưỡng | Ví dụ trong MEPF | Xử lý |
|---|---|---|---|
| **Tự sửa** | ≥ 0.95 | Text/MTEXT trùng lặp, thực thể trùng khít, layer không tồn tại trong bảng chuẩn, style kích thước lệch | `apply_safe_fixes` sửa, ghi oplog, báo lại đã sửa gì |
| **Hỏi người** | 0.70–0.95 | Block chèn lệch tỷ lệ (0.98 — lỗi vẽ hay là thiết bị khác cỡ?), tuyến ống hở 2 mm | Sinh `ISSUE` chờ duyệt **từng cái** |
| **Chỉ đánh dấu** | < 0.70 | Đơn vị bản vẽ nghi sai, ký hiệu không khớp thư viện block | Không đề xuất sửa; nêu rõ vì sao không chắc |

Ràng buộc:

- **Mỗi lỗi có ID bền** (`ISSUE-<hash nội dung>`) để duyệt/bỏ qua từng cái, và để chạy
  audit lần hai không đẻ trùng.
- **Sai đơn vị bản vẽ luôn nằm ở mức thấp nhất, bất kể điểm số.** Đây là lỗi mà sửa nhầm
  làm sai toàn bộ khối lượng hàng nghìn lần; `audit_cad_drawing_errors` đã xếp nó là lỗi
  số 1 vì lý do đó. Không được để một ngưỡng số vượt mặt quy tắc này — chốt bằng test.
- **`hil.py` phải mở rộng từ cờ toàn cục sang duyệt theo ID.** Cơ chế "DUYỆT" hiện tại
  duyệt *cả lượt*: người dùng gõ một chữ là chấp nhận mọi thứ đang chờ, kể cả cái họ chưa
  đọc. Giữ tương thích (không ID = duyệt tất cả, như cũ) nhưng thêm dạng
  `DUYỆT ISSUE-1023, ISSUE-1041`.
- **Ngưỡng nằm trong cấu hình, danh mục lỗi nằm trong code.** Chỉnh ngưỡng là việc vận
  hành; thêm loại lỗi là việc lập trình.

---

## 5. Vòng kiểm tra sau khi sửa

Hiện tool sửa CAD báo thành công dựa trên việc **ghi file không lỗi**. Đó là kiểm tra thao
tác, không phải kiểm tra kết quả.

```
Operation → thực thi → parse lại bản vẽ → đối chiếu ý định → PASS/FAIL
                                              │
                                        FAIL → khôi phục revision + báo rõ chỗ lệch
```

- `verify_operation(op, file_path)` đọc lại bản vẽ (qua `cad_cache`, đã tự invalidate theo
  mtime) và khẳng định hậu điều kiện của chính `op` đó: đổi 24 đối tượng thì đếm lại đúng
  24, đặt layer thì không còn đối tượng nào ở layer cũ trong phạm vi.
- **FAIL thì tự lùi về revision trước**, không để lại bản vẽ ở trạng thái nửa vời. Cơ chế
  lùi đã có (`restore_cad_revision`), chỉ chưa ai gọi tự động.
- **Sửa hàng loạt phải chạy theo giao dịch:** một thực thể lỗi thì lùi cả lô, không sửa
  được 18/24 rồi báo "xong một phần".
- Kết quả verify vào oplog, thành nhật ký kiểm toán liên tục.

---

## 6. Đối chiếu chéo bản vẽ ↔ bảng thống kê — `src/cross_check.py`

Ví dụ trong đề xuất ("bản vẽ có 3 cửa sổ W02, schedule ghi 2") dịch sang MEPF thì đúng ở
những chỗ tốn tiền nhất:

- Mặt bằng có **14** đầu phun trên trục A, bảng thống kê PCCC ghi **12**.
- Sơ đồ nguyên lý điện khai MCCB **250 A**, bảng tủ điện ghi **225 A**.
- Bản vẽ ghi ống **DN100**, bảng vật tư ghi **DN80** cho cùng tuyến.
- Tổng chiều dài máng cáp trên mặt bằng lệch với bảng khối lượng của nhà thầu.

Đây là **loại lỗi mà AI có lợi thế thật** — cần đọc hiểu văn bản ở hai nguồn khác định
dạng rồi khớp ý nghĩa, không phải một luật hình học viết được bằng `if`. Và nó cần đúng
những công cụ đang thiếu ở tài liệu tool: OCR (`DAC_TA_TOOL_AI.md` 3.1), bảng trong PDF
(3.2), Excel nhiều sheet (3.5). Đó là lý do mục này xếp sau các mục đó.

Ràng buộc quan trọng nhất: **so khớp là việc của code, chỉ có "hiểu ý" mới là việc của
LLM.** LLM ánh xạ *"đầu phun tự động ⌀15"* trong bảng với layer `F-SPRINKLER-HEAD` trên bản
vẽ; **đếm** thì tool đếm. Đưa cả khâu đếm cho LLM là quay lại đúng cái mà nguyên tắc 1 cấm.

Kết quả sinh ra `ISSUE` theo đúng khuôn mục 4, và **không tự sửa** — lệch giữa hai hồ sơ
gần như luôn cần kỹ sư quyết định bên nào đúng.

### 6.1 Về "knowledge graph của dự án"

Ý này đúng hướng nhưng nên tới **sau**, và nên tới ở dạng nhỏ nhất dùng được: một bảng
quan hệ `(đối tượng, xuất hiện ở, được khai báo bởi, số lượng)` là đủ để chạy các phép đối
chiếu ở trên. Dựng một graph đầy đủ của dự án trước khi có thứ để hỏi nó là làm ngược. Khi
đã có bằng chứng truy ngược (mục 2) và đối chiếu chéo (mục 6), graph gần như hình thành từ
chính dữ liệu đó.

---

## 7. Về Autodesk Platform Services

APS giải đúng ba việc mà repo đang thiếu: Model Derivative (đọc `.rvt` mà không cần
Revit), Viewer (xem bản vẽ trên web), Design Automation (chạy AutoCAD trên cloud, không cần
máy Windows có bản quyền — chính là rào cản của `DAC_TA_TOOL_AI.md` mục 3.4).

Nhưng nó **xung đột trực tiếp với một ràng buộc đã ghi trong repo**: `TECH_DEBT.md` mục 2
nói khách MEPF có thể yêu cầu air-gapped, không Internet. APS bắt buộc đẩy bản vẽ lên cloud
Autodesk. Đây không phải chuyện kỹ thuật mà là chuyện hợp đồng với khách — không quyết
được trong một tài liệu đặc tả.

Vì vậy đề xuất:

- **Không đặt APS làm nền.** Đặt nó **sau một giao diện backend**, cùng khuôn với
  `standards_backend.py` và `db_tools` (mục 3.7 tài liệu tool): `register_cad_backend`.
  Mặc định là backend cục bộ (ezdxf + ODA); ai có tài khoản APS thì đăng ký thêm.
- **Viewer là mục dùng APS đáng nhất và ít ràng buộc nhất** — có thể chạy trên bản vẽ đã
  chuyển đổi, không cần đưa toàn bộ hồ sơ gốc lên.
- **`.rvt` là chỗ APS gần như không thay thế được.** Hiện repo đọc IFC (`ifcopenshell`)
  chứ không đọc `.rvt`; đường đi thực tế hơn là bảo khách xuất IFC.
- Bất kỳ đường nào đẩy file ra ngoài **phải nói rõ với người dùng trước khi gửi**, và phải
  tắt được bằng một biến cấu hình duy nhất.

---

## 8. Về phân tầng model theo công đoạn

Nguyên tắc "không dùng một model cho cả pipeline" là đúng và repo **đã đi được nửa đường**:
`AI_MODEL_SETUP.md` mô tả chọn model theo vai trò, nhưng `config.py` chỉ có một
`model_name`. Việc còn thiếu là cấu hình **theo vai trò** thật sự:
`MODEL_FOR_QS`, `MODEL_FOR_CAD`, `MODEL_FOR_REVIEWER`… với `model_name` là giá trị mặc
định khi không khai.

Hai lưu ý trước khi tối ưu chỗ này:

- **Không chốt tên model cụ thể vào tài liệu đặc tả.** Danh sách model đổi nhanh hơn tài
  liệu; chốt tên vào đây là bảo đảm tài liệu sẽ sai. Đặc tả nên nói *yêu cầu năng lực*
  (gọi tool nhiều bước, cửa sổ ngữ cảnh dài, chi phí thấp cho tác vụ phân loại), việc chọn
  model để trong `.env` và `AI_MODEL_SETUP.md`.
- Câu kết luận của chính đề xuất là câu đáng giữ nhất: **model mạnh hơn không bù được dữ
  liệu hình học chưa chuẩn hóa.** Điều đó nói rằng thứ tự ưu tiên đúng là mục 2–6 trước,
  tinh chỉnh model sau.

---

## 9. Chỗ đề xuất nên điều chỉnh

Ba điểm không nên bê nguyên:

1. **"Bóc khối lượng chỉ từ bản vẽ đã QC"** — đúng về nguyên tắc, nhưng cấm cứng sẽ chặn
   một tình huống chiếm phần lớn công việc thật: khách cần *ước lượng nhanh* trên bản vẽ
   thô trong giai đoạn đấu thầu. Cách đúng theo văn hóa repo là **không cấm, mà nói rõ**:
   bóc trên bản chưa audit thì kết quả mang nhãn `[CHƯA QC]` ngay trong Excel và trong bản
   ghi bằng chứng. Cấm thì người dùng đi đường vòng; dán nhãn thì họ biết mình đang cầm
   cái gì.
2. **"Confidence 96%" cho một sai lệch kích thước** — với sai lệch phát hiện bằng cách đối
   chiếu hai con số, độ tin cậy là 100% hoặc là lỗi đọc dữ liệu. Con số phần trăm nên dành
   cho khâu *nhận dạng* (OCR, YOLO, khớp tên hạng mục), không dán lên khâu *so sánh*.
   Điểm tin cậy dán bừa sẽ dạy người dùng bỏ qua nó.
3. **Tự sửa "title block" và "plot setting" ở mức tự động** — hai thứ này thuộc quy chuẩn
   trình bày riêng của từng công ty. Nên xếp vào mức "hỏi người" cho tới khi có bản khai
   chuẩn trình bày của chính khách hàng đó.

---

## 10. Thứ tự làm

Nối tiếp bảng ưu tiên ở `DAC_TA_TOOL_AI.md` mục 4 (tầng công cụ), không thay nó:

| # | Hạng mục | Phụ thuộc | Mục |
|---|---|---|---|
| A | Bằng chứng truy ngược cho khối lượng | không — làm được ngay với `ezdxf` | 2 |
| B | Lệnh CAD có cấu trúc + oplog | không | 3 |
| C | Vòng kiểm tra sau khi sửa | B | 5 |
| D | Ba mức tin cậy + duyệt theo ID | B, C | 4 |
| E | Đối chiếu chéo bản vẽ ↔ bảng thống kê | OCR + PDF bảng + Excel đa sheet | 6 |
| F | Cấu hình model theo vai trò | không | 8 |
| G | Backend CAD cắm được (mở đường APS) | B | 7 |

**A và B nên đi trước tất cả**, vì bốn hạng mục còn lại đều ghi dữ liệu vào hai cấu trúc mà
chúng dựng lên. Làm ngược thứ tự này thì sẽ phải viết lại chúng.

Điều kiện nghiệm thu áp dụng nguyên mục 5 của [`DAC_TA_TOOL_AI.md`](DAC_TA_TOOL_AI.md),
thêm hai điều riêng cho tầng này:

6. **Mọi thao tác sửa bản vẽ có oplog và có đường lùi** — test khẳng định thất bại giữa
   chừng của một lô sửa không để lại bản vẽ ở trạng thái nửa vời.
7. **Mọi dòng khối lượng truy ngược được về thực thể** — test lấy một dòng BOQ bất kỳ, lần
   theo bằng chứng, mở lại bản vẽ và tìm thấy đúng các handle đã ghi.

---

## 11. Đọc tiếp

- [`DAC_TA_TOOL_AI.md`](DAC_TA_TOOL_AI.md) — tầng công cụ: OCR, PDF, Excel, DWG, AutoCAD,
  đơn vị, truy vấn dữ liệu
- [`DAC_TA_HE_THONG.md`](DAC_TA_HE_THONG.md) — đặc tả mã đang chạy
- [`../TECH_DEBT.md`](../TECH_DEBT.md) — mục 1 (hạ tầng dữ liệu), 2 (ràng buộc air-gapped),
  5 (thị giác máy tính)
- [`AUDIT_BOC_KHOI_LUONG.md`](AUDIT_BOC_KHOI_LUONG.md) — rà soát đường bóc khối lượng hiện tại
