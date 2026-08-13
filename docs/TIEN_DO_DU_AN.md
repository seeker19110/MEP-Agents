# Tiến độ Dự án MEP-Agents

Bản ghi nhận trạng thái thực tế của dự án tại mốc rà soát gần nhất. Mục đích: người mới
vào (hoặc chính mình sau vài tháng) đọc một file này là biết dự án đang ở đâu, cái gì đã
chạy được thật, cái gì mới chỉ viết xong mà chưa kiểm chứng.

**Cập nhật lần cuối:** 2026-08-13 — sau đợt rà soát toàn dự án (PR #32).

## 1. Số liệu hiện trạng

| Chỉ số | Giá trị | Ghi chú |
|---|---:|---|
| Mã nguồn Python (`src/`) | ~12.660 dòng | 58 module |
| Test | **563 đạt / 0 lỗi** | 53 file trong `tests/` |
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

Bốn Phase đều nối vào hệ thống bằng **patch lúc import** (`src/agents_phase_*_patch.py`,
`src/*_bind.py`) thay vì sửa thẳng `agents.py`/`tools.py`. Ưu điểm: mỗi Phase tách bạch,
dễ gỡ. Nhược điểm đã thành sự thật một lần — xem mục 4.

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
- **Ghi nợ, chưa làm:** phần patch bọc node của graph (HIL, hàng đợi, fan-out song song)
  không dùng được kiểu registry này — cần tái cấu trúc `agents.py`/`graph.py` thành các
  bước có điểm nối sẵn. Việc lớn, để riêng một PR. Xem `TECH_DEBT.md` mục 10.

## 5. Việc còn nợ

Chi tiết đầy đủ ở [`TECH_DEBT.md`](../TECH_DEBT.md). Tóm tắt mức ưu tiên:

| Việc | Mức | Vướng ở đâu |
|---|---|---|
| Chạy thử `docker compose up --build` thật | 🟠 Cao | Cần máy có Docker daemon |
| Migrate Postgres/pgvector/S3 với hạ tầng thật | 🟠 Cao | Cần instance thật + người duyệt schema |
| Test E2E toàn luồng + test UI cho `web/` | 🟡 Vừa | Chưa có kịch bản; cần Redis/Celery thật |
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

1. **Chạy thử Docker Compose thật** — rẻ nhất trong nhóm còn nợ, và gỡ được nút thắt cho
   cả mục E2E lẫn triển khai. Chỉ cần một máy có Docker.
2. **Một kịch bản E2E tối thiểu** — upload `.dxf` thật → worker thật → tải Excel về. Đủ
   để bắt lớp lỗi mà unit test có mock không bao giờ thấy.
3. **Rà lại các patch lúc import còn lại** theo bài học ở mục 4, tìm chỗ nào còn gọi
   ngược qua tên module đã bị thay.
