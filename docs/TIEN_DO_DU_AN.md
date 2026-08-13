# Tiến độ Dự án MEP-Agents

Bản ghi nhận trạng thái thực tế của dự án tại mốc rà soát gần nhất. Mục đích: người mới
vào (hoặc chính mình sau vài tháng) đọc một file này là biết dự án đang ở đâu, cái gì đã
chạy được thật, cái gì mới chỉ viết xong mà chưa kiểm chứng.

**Cập nhật lần cuối:** 2026-08-13 — sau đợt rà soát toàn dự án (PR #32).

## 1. Số liệu hiện trạng

| Chỉ số | Giá trị | Ghi chú |
|---|---:|---|
| Mã nguồn Python (`src/`) | ~12.660 dòng | 58 module |
| Test Python | **600 đạt / 0 lỗi** | 57 file trong `tests/` |
| Test giao diện | **7 đạt / 0 lỗi** | Playwright, Chromium thật (`web/tests-ui/`) |
| Số PR đã hợp nhất | 32 | tính tới `c44e3b3` |
| Phase đã hợp nhất | A, B, C, D | xem mục 2 |

Cách kiểm chứng lại số liệu:

```bash
uv run pytest -q
uv run python -m py_compile app.py main.py src/*.py
```

## 2. Các Phase đã hợp nhất

| Phase | Nội dung | Tài liệu | Trạng thái |
|---|---|---|---|
| **A** | 5 skill CAD/QS gộp pipeline (`batch_edit_pipes`, `batch_replace_text`, `update_title_block`, `prepare_drawing`, `full_boq`) | [`README_PHASE_A.md`](../README_PHASE_A.md) | ✅ Có test, chạy được offline |
| **B** | Checklist QS chấm điểm 0–100, `compare_boq`, chốt chặn Human-in-the-loop, hàng đợi đa ý định | [`README_PHASE_B.md`](../README_PHASE_B.md) | ✅ Có test |
| **C** | Postgres/pgvector, S3, JWT, scaffold YOLO MEPF | [`README_PHASE_C.md`](../README_PHASE_C.md) | ⚠️ Code + test đủ, **chưa chạy với hạ tầng thật** |
| **D** | Tìm kiếm lai (vector + từ khóa RRF), embedding cục bộ, LangGraph `Send` chạy song song M/E/P/F, cache tool theo vai trò | [`README_PHASE_D.md`](../README_PHASE_D.md) | ✅ Có test |

Bốn Phase **từng** nối vào hệ thống bằng patch lúc import (gán đè hàm/tool của module
khác). Kiểu nối đó đã sinh ra lỗi thật (xem mục 4) và nay đã được thay hết bằng ba điểm
nối tường minh: registry tool (`src/tools.py`), backend tra cứu
(`src/standards_backend.py`), middleware điều phối (`src/supervisor_pipeline.py`).

## 3. Đợt rà soát 2026-08-13 (PR #32)

Chạy đủ bộ test trên `main` ra **13 test đỏ**. Không phải test hỏng vặt: 3 lỗi thật lọt
vào khi patch Phase C/D ghi đè code cũ, cộng 1 nhóm test lạc hậu.

| Lỗi | Mức độ | Hệ quả nếu không sửa |
|---|---|---|
| Đệ quy vô hạn khi đọc XREF (`src/cad_cache.py`) | 🔴 Nặng | **Mọi XREF thất bại im lặng** — nội dung xref bị loại khỏi khối lượng, chỉ để lại một dòng note khó hiểu. Đúng kịch bản "bóc thiếu mà không cảnh báo" mà `cad_loader.py` ghi rõ là phải tránh |
| `detect_cad_symbols_yolo` mất `resolve_safe_path` (`src/vision_tools.py`) | 🟠 Cao | Tool đọc được file ngoài workspace của phiên; `predict` ném lỗi thì tool vỡ thay vì báo |
| `ingest` ném `FileNotFoundError` lần chạy đầu (`src/ingest.py`) | 🟡 Vừa | Người dùng mới chạy `python -m src.ingest` là gặp traceback |
| `JWT_BOOTSTRAP_USER` qua env bị nuốt (`src/auth_jwt.py`) | 🟡 Vừa | Đổi user bootstrap bằng biến môi trường im lặng vô tác dụng |
| `uv.lock` lệch `pyproject.toml` từ Phase C | 🟡 Vừa | `uv sync --extra phase-c` không tái lập được đúng môi trường |

**Thay đổi hành vi cần biết:** sau khi sửa lỗi XREF, khối lượng bóc từ bản vẽ **có xref sẽ
tăng** so với trước. Đó là con số đúng — trước đây phần xref bị bỏ qua hoàn toàn.

## 4. Bài học rút ra: rủi ro của kiểu "patch lúc import"

Lỗi XREF nói trên là hệ quả trực tiếp của kiến trúc patch: `cad_loader_perf_patch` gán tạm
`ezdxf.readfile = readfile_cached`, còn `readfile_cached` lại gọi ngược `ezdxf.readfile` ở
nhánh cache-miss → tự gọi chính mình. Từng module đứng riêng đều đúng; chỉ sai khi ghép.

Hệ quả cho cách làm việc về sau:

1. **Luôn chạy đủ bộ test, không chỉ test của Phase mình làm.** Cả 13 lỗi đều lộ ra ở lần
   chạy `pytest` toàn bộ; chạy riêng `tests/test_phase_d.py` thì xanh hết.
2. Module bị patch nên giữ tham chiếu hàm gốc **ngay lúc import**, không gọi lại qua tên
   module (tên đó có thể đã bị người khác thay).
3. Khi một Phase đổi hành vi có chủ đích, sửa luôn test cũ trong cùng PR — đừng để test
   đỏ tồn tại như "nhiễu nền", vì lỗi thật sẽ lẫn vào đó (đúng như đã xảy ra ở đây).

## 4b. Đợt xử lý tiếp theo (cùng ngày)

Làm theo đúng 3 việc đề ở mục 6 mà môi trường hiện tại cho phép:

- **Rà hết tầng patch còn lại** — không có ca đệ quy thứ hai. Nhưng lộ ra một lỗi khác
  cùng gốc: `cad_loader_perf_patch` gán đè biến toàn cục `ezdxf.readfile` quanh mỗi lần
  gộp xref. Phase D chạy song song bằng thread nên hai lời gọi chồng nhau khôi phục nhầm
  của nhau → `ezdxf.readfile` kẹt vĩnh viễn ở bản cache, mọi chỗ đọc DXF sau đó dùng chung
  một doc có thể bị sửa đổi. Đã sửa bằng cách truyền hàm đọc qua tham số.
- **Gộp 8 skill Phase A/B vào registry chính** `src/tools.py`. Tầng patch giữ lại làm mạng
  lưới an toàn. Bộ tool từng vai trò không đổi (đã đối chiếu số lượng trước/sau).
- **Chạy thử Docker / E2E**: vẫn chưa làm được — môi trường này không có Docker daemon.

## 4c. Đợt xử lý thứ ba

- **Thêm điểm mở rộng `src/standards_backend.py`** — Phase C/D thôi tráo đối tượng tool
  `search_standards`, chuyển sang đăng ký backend theo mức ưu tiên. Tool giữ nguyên danh
  tính suốt vòng đời tiến trình.
- **Nguồn embedding vào thẳng `vectorstore.get_embeddings`** — sửa kèm một lỗi thật:
  `python -m src.ingest` không import `graph` nên patch Phase D không chạy, cộng với việc
  `ingest` chặn cứng ở `OPENAI_API_KEY` → **chạy offline không nạp được index**, hybrid
  mất hẳn nhánh vector mà không có dấu hiệu gì.
- **Xóa hàm chết** `get_tools_for_role_cached()`.
- **Sửa hardcode địa chỉ LLM cục bộ** — `src/agents.py` hardcode `localhost:11434`
  (Ollama) và `localhost:8000` (vLLM), trong khi phía embedding lại đọc `OLLAMA_BASE_URL`.
  Hai nửa của cùng một cấu hình đi hai đường: embedding trỏ đúng máy, LLM gọi vào chính
  container của nó. Chỉ lộ ra khi thật sự dựng cấu hình lai. Nay đọc env, dùng chung biến
  với embedding, tự chuẩn hóa đuôi `/v1`.
- **Ghi nợ, chưa làm:** phần patch bọc node của graph (HIL, hàng đợi, fan-out song song)
  không dùng được kiểu registry này — cần tái cấu trúc `agents.py`/`graph.py` thành các
  bước có điểm nối sẵn. Việc lớn, để riêng một PR. Xem `TECH_DEBT.md` mục 10.

## 4d. Kịch bản E2E (đợt thứ tư)

Thêm hai tầng kiểm thử E2E, xem [`E2E.md`](E2E.md):

- **Tầng 1** `tests/test_e2e_takeoff.py` — chạy trong CI, đi trọn đường bản vẽ `.dxf` thật
  → bóc khối lượng thật → Excel thật → tải về qua FastAPI, chỉ thay broker bằng gọi đồng
  bộ. Đã kiểm chứng sức bắt lỗi: làm hỏng luồng gộp XREF thì 3/4 test chuyển đỏ.
- **Tầng 2** `scripts/e2e_smoke.py` — không giả lập gì. **Đã chạy đạt** với Redis thật,
  worker Celery ở tiến trình riêng, FastAPI thật: tải lên → worker nhặt task qua Redis →
  Excel 5.582 byte → tải về, tổng chiều dài khớp hình học đã dựng. Đường xác thực
  `MEP_AGENTS_API_KEY` cũng đã kiểm (thiếu khóa → 401, có khóa → đạt).

Đây là lần đầu dự án có bằng chứng luồng phân tán chạy thật đầu-cuối. **Vẫn chưa** chạy
qua `docker compose up --build` — môi trường viết code không có Docker daemon, và lớp
container còn có thể sinh lỗi riêng (quyền volume, biến môi trường, healthcheck).

## 4e. Gỡ nốt phần patch bọc node (đợt thứ năm)

Đây là phần cuối của mục 10 `TECH_DEBT.md`, trước đó cố ý để lại vì nó nằm giữa luồng
điều phối.

- **`src/supervisor_pipeline.py`** — điểm nối kiểu middleware. Phase B (chốt chặn HIL +
  hàng đợi) và Phase D (fan-out song song) đăng ký lớp theo mức ưu tiên thay vì gán đè
  `agents.supervisor_node`. Hàm điều phối nay giữ nguyên danh tính suốt vòng đời tiến
  trình, nên `src/graph.py` không còn phải đọc lại nó sau các dòng import patch.
- **`DELIVERABLE_TOOLS`** khai báo thẳng trong `src/agents.py`.
- **Kiểm chứng tương đương:** chạy cùng 10 tình huống định tuyến đại diện trên bản trước
  và sau, kết quả **giống hệt từng trường**. E2E hạ tầng thật chạy lại cũng đạt.

Sau đợt này **không còn chỗ nào gán đè hàm hay tráo đối tượng của module khác.** Hai
patch còn lại (`agents_perf_patch`, `qs_perf_patch`) là bọc thuần túy quanh một hàm, không
dính lớp lỗi đã gặp — để lại có chủ đích.

## 4f. Triển khai theo khuyến nghị (đợt thứ sáu)

- **Test giao diện `web/`** — 7 kịch bản Playwright trên Chromium thật, gồm **trọn đường
  qua trình duyệt**: thả bản vẽ → bấm phân tích → WebSocket đẩy trạng thái → tải Excel về.
  Đây là mảng trước đó không có lớp kiểm thử nào. Test bắt ngay một lỗi giao diện thật:
  vùng kéo-thả mời "hoặc click để chọn file" nhưng **không có `<input type="file">`** — cú
  bấm rơi vào hư không. Đã sửa, và lời mời nay là nút thật (bàn phím dùng được).
- **Cảnh báo bảng đơn giá cũ** — rủi ro nghiệp vụ lớn nhất còn lại: con số tiền đi vào hồ
  sơ thầu dựa trên `data/unit_prices.csv` mà không ai biết bảng giá cũ chưa. Nay có
  `data/unit_prices.meta.json` khai báo ngày hiệu lực, quá ngưỡng thì chính báo cáo dự
  toán mang theo cảnh báo. Xem `TECH_DEBT.md` mục 11.
- **Chưa làm được:** chạy Docker Compose (không có Docker daemon) và dựng Ollama thật
  (chưa cài). Hai việc này vẫn cần máy khác.

## 4g. Tái cấu trúc module: cắt vòng import (đợt thứ bảy)

`tools.py` và `qs_tools.py` import ngược nhau ở mức module, khiến `import src.qs_tools`
trực tiếp bị vỡ và buộc cả hai file phải dồn import xuống giữa/cuối file kèm `# noqa: E402`.

- Tách hàm dùng chung sang **`src/mepf_spec.py`** — module nền, không import module nào
  của dự án. Vòng lặp đứt hẳn.
- Toàn bộ import của hai file về đầu file; **không còn `# noqa: E402`** nào.
- `src/api.py` nạp thẳng từ `src.qs_tools` thay vì đi vòng qua `src.tools`.
- Mã nguồn **giảm ròng ~14 dòng** trong ba file, dù thêm một module mới.
- `tests/test_no_import_cycles.py` nạp từng module lõi trong **tiến trình sạch** để vòng
  lặp quay lại là đỏ ngay; đã thử tái lập vòng cũ để xác nhận test bắt được.

## 5. Việc còn nợ

Chi tiết đầy đủ ở [`TECH_DEBT.md`](../TECH_DEBT.md). Tóm tắt mức ưu tiên:

| Việc | Mức | Vướng ở đâu |
|---|---|---|
| Chạy thử `docker compose up --build` thật | 🟠 Cao | Cần máy có Docker daemon |
| Migrate Postgres/pgvector/S3 với hạ tầng thật | 🟠 Cao | Cần instance thật + người duyệt schema |
| Kiểm thử plugin trong Revit/AutoCAD thật | 🟡 Vừa | Cần máy Windows có 2 phần mềm đó |
| Fine-tune YOLO trên ký hiệu MEPF | 🟡 Vừa | Cần bộ ảnh gán nhãn thật |
| Real-time đúng nghĩa (Redis Pub/Sub) | 🟡 Vừa | Server vẫn polling Celery backend 1s |
| Local LLM / air-gapped | 🟢 Thấp | Cần GPU 16–24GB VRAM |
| Billing + xác thực đa người dùng | 🟢 Thấp | Cần tài khoản cổng thanh toán thật |

Điểm chung của nhóm còn nợ: **không phải việc sửa code**, mà là việc cần hạ tầng, phần
cứng, dữ liệu thật hoặc quyết định kinh doanh. Viết code đoán trước cho chúng rủi ro cao
hơn lợi ích.

## 6. Đề xuất việc tiếp theo

Xếp theo tỉ lệ lợi ích / công sức, cao xuống thấp:

1. **Chạy thử Docker Compose thật** — việc còn lại rẻ nhất. Kịch bản E2E đã sẵn sàng:
   `docker compose up --build -d` rồi `uv run python scripts/e2e_smoke.py` là biết ngay
   lớp container có vấn đề gì.
2. **Dựng thử cấu hình lai với Ollama thật** — phần sửa địa chỉ server mới chỉ được kiểm ở
   mức "dựng đúng địa chỉ", chưa hề gọi tới server thật.
3. **Đối chiếu `data/unit_prices.csv` với công bố giá thật của Sở Xây dựng**, và phân theo
   vùng. Cơ chế cảnh báo đã có, nhưng số liệu vẫn là giá tham khảo nội bộ.
