# Hướng dẫn cho AI Assistant làm việc trên MEP-Agents

## Vai trò (persona)

Trước khi bắt tay vào việc, chọn một vai trò phù hợp và bám theo nó:

| Vai trò | Dùng khi |
|---|---|
| **Developer** | Viết code, sửa lỗi, thêm tính năng |
| **Code Reviewer** | Rà soát thay đổi, kiểm tra chất lượng |
| **Rebaser** | Dọn lịch sử git, rebase |
| **Merger** | Hợp nhất code giữa các nhánh |
| **Multiplan Manager** | Điều phối nhiều việc song song, lập kế hoạch |

Nếu thư mục `.promptx/personas/` tồn tại, đọc file mô tả vai trò tương ứng trong đó.
Repo này **hiện không có** thư mục đó — cứ theo bảng trên và các nguyên tắc bên dưới.

## Bối cảnh dự án

Hệ thống Multi-Agent mô phỏng một văn phòng tư vấn thiết kế MEPF: Supervisor điều phối 7
bộ phận chuyên môn (Mechanical, Electrical, Plumbing, Firefighting, QS, CAD, BIM),
Reviewer kiểm duyệt đầu ra.

- **Ngôn ngữ/Framework:** Python ≥ 3.11, LangGraph + LangChain, Streamlit (UI), FastAPI
  (API), Celery + Redis (task nền), React/Vite (`web/`)
- **Quản lý phụ thuộc:** `uv` (khoá trong `uv.lock`, nhóm phụ nằm ở `[project.optional-dependencies]`)
- **Test:** `pytest` — hiện **600 test**, tất cả phải xanh. Có thêm E2E, xem [`docs/E2E.md`](docs/E2E.md)
- **Kiến trúc:** [`docs/DAC_TA_HE_THONG.md`](docs/DAC_TA_HE_THONG.md) là đặc tả đầy đủ —
  đọc trước khi sửa gì đáng kể. [`progress.md`](progress.md) mục 3 cho trạng
  thái hiện tại, [`TECH_DEBT.md`](TECH_DEBT.md) cho cái gì còn nợ và **vì sao chưa trả**,
  [`docs/RA_SOAT_LO_HONG.md`](docs/RA_SOAT_LO_HONG.md) cho lỗ hổng đã biết

### Nguyên tắc riêng của dự án này

1. **Không để LLM đoán số.** Mọi công thức kỹ thuật nằm trong code Python xác định
   (`src/hvac_tools.py`, `elec_tools.py`, `plumb_tools.py`, `ff_tools.py`, `qs_tools.py`,
   `bim_tools.py`). AI chỉ chọn tool và diễn giải kết quả.
2. **Không bỏ sót âm thầm.** Thiếu dữ liệu, thiếu đơn giá, thiếu file xref → phải nêu rõ
   trong kết quả trả về. Một con số khối lượng thiếu mà người dùng tưởng là đủ nguy hiểm
   hơn nhiều so với một cảnh báo lộ liễu.
3. **Mọi thao tác file đi qua `resolve_safe_path`** (`src/workspace.py`). Đường dẫn do LLM
   đưa vào không bao giờ được dùng thẳng.
4. **Graceful fallback.** Thiếu API key, thiếu Redis, thiếu Postgres → rơi về đường cục bộ
   kèm log cảnh báo, không sập.
5. **Sửa CAD phải lưu revision trước khi ghi đè** (`src/cad_revision.py`).
6. **Logic xác thực nằm trong `src/api.py`, không gắn từ ngoài vào.** FastAPI chốt
   `Depends(...)` vào route ngay lúc định nghĩa route — gán đè `api.require_api_key` từ
   module khác **không đổi được route nào**. Việc này đã từng làm API mở toang suốt nhiều
   PR. Test xác thực phải gửi request thật qua `TestClient`, không gọi hàm.
7. **Vai trò có node trong graph phải có entry trong `TOOLS_BY_ROLE`.** Rơi vào nhánh mặc
   định là im lặng nhận đủ 90 tool — sai quyền và đắt, mà không có cảnh báo nào.

## Lệnh thường dùng

```bash
uv run pytest -q                                   # Chạy toàn bộ test
uv run pytest tests/test_phase_d.py -q             # Chạy test một Phase
uv run python -m py_compile app.py main.py src/*.py # Kiểm tra cú pháp
uv run streamlit run app.py                        # Giao diện web
uv run main.py                                     # CLI
uv run python -m src.ingest                        # Nạp tiêu chuẩn cho RAG
uv lock --check                                    # Kiểm tra uv.lock có lệch pyproject không
```

## Cấu trúc thư mục

```
./
├── pyproject.toml / uv.lock   # Phụ thuộc
├── app.py                     # Streamlit UI
├── main.py                    # CLI
├── src/                       # Toàn bộ mã nguồn (58 module)
│   ├── agents.py, graph.py, state.py       # Lõi LangGraph
│   ├── *_tools.py                          # Tool tính toán từng bộ phận
│   ├── cad_*.py                            # Đọc/sửa/tối ưu/chuẩn hóa bản vẽ
│   ├── supervisor_pipeline.py, standards_backend.py  # Điểm nối mở rộng (xem dưới)
│   ├── mepf_spec.py                        # Module nền — KHÔNG được import module khác
│   └── api.py, celery_app.py               # API + task nền
├── tests/                     # 55 file test
├── web/                       # React/Vite
├── revit/ · autocad/          # Plugin
└── docs/                      # Tài liệu
```

## ⚠️ Cảnh báo bắt buộc đọc trước khi sửa code

Các Phase A/B/C/D **từng** nối vào hệ thống bằng patch lúc import (gán đè hàm/tool của
module khác). Kiểu nối đó đã sinh ra lỗi thật — `cad_cache` tự gọi chính mình gây đệ quy
vô hạn, mọi XREF bị loại khỏi khối lượng (PR #32) — và nay đã được thay hết bằng **ba điểm
nối tường minh**. Muốn mở rộng, dùng đúng ba chỗ này, **đừng gán đè module khác**:

| Muốn thêm gì | Dùng |
|---|---|
| Tool mới cho một vai trò | `src/tools.py` — `TOOLS_BY_ROLE` + `tools` |
| Đường tra cứu tiêu chuẩn mới | `src/standards_backend.py` — `register_backend(tên, hàm, ưu tiên)` |
| Luật định tuyến mới | `src/supervisor_pipeline.py` — `register_middleware(tên, hàm, ưu tiên)` |

Hai quy tắc rút ra, vẫn còn giá trị:

- Nếu buộc phải bọc một hàm, **giữ tham chiếu hàm gốc ngay lúc import**, không gọi lại qua
  tên module — tên đó có thể đã bị người khác thay.
- **Luôn chạy đủ bộ test**, không chỉ test của Phase đang làm. Lỗi do ghép module không
  bao giờ lộ ra khi chạy riêng.

Chi tiết: [`TECH_DEBT.md`](TECH_DEBT.md) mục 10.

## Nguyên tắc chung

1. **Đọc trước khi sửa** — hiểu ngữ cảnh đủ rộng, đừng sửa mò.
2. **Xóa nhiều hơn thêm** — phức tạp tích tụ thành thảm họa.
3. **Theo pattern sẵn có** — đừng phát minh cách làm mới.
4. **Chạy build và test sau mỗi thay đổi.**
5. **Commit thường xuyên**, thông điệp rõ ràng.
6. **Không tự nhận là xong khi chưa kiểm chứng.** Nếu không chạy thử được (thiếu Docker,
   thiếu Revit, thiếu API key), ghi rõ là chưa chạy — đó là văn hóa của `TECH_DEBT.md`.
