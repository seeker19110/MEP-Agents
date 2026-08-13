# Phase D — Tìm kiếm lai, song song hóa, embedding cục bộ (hợp nhất qua PR #31)

## Thành phần

1. **Tìm kiếm tiêu chuẩn lai** (`src/hybrid_search.py`) — gộp kết quả vector và kết quả
   khớp từ khóa bằng RRF (Reciprocal Rank Fusion). Có regex bắt riêng mã hiệu tiêu chuẩn
   (`TCVN`, `QCVN`, `TCXD`, `NFPA`, `ASHRAE`, `IEC`, `BS EN`) — dạng truy vấn mà tìm kiếm
   thuần vector hay trượt vì mã số không mang ngữ nghĩa.
2. **Embedding tự chọn nguồn** (`src/local_embeddings.py`) — OpenAI, Ollama, hoặc
   sentence-transformers chạy cục bộ. Cho phép chạy RAG khi không có API key.
3. **Chạy song song M/E/P/F** (`src/supervisor_parallel.py`, `src/graph_parallel.py`) —
   dùng `Send` của LangGraph fan-out khi một yêu cầu đụng từ 2 bộ phận trở lên. Dựng
   `Send` thất bại thì tự rơi về chạy tuần tự, không làm hỏng luồng.
4. **Cache tool theo vai trò** (`src/tools_lazy.py`) — khỏi dựng lại danh sách tool mỗi
   lượt gọi LLM.

## Cách nối vào hệ thống

`src/agents_phase_d_patch.py` → `apply_phase_d()` vá lúc import: đổi nguồn embedding của
`vectorstore`, bọc `search_standards` bằng bản lai, gắn supervisor song song. Mỗi bước bọc
trong `try/except` riêng — một phần hỏng thì chỉ phần đó bị bỏ qua kèm cảnh báo log, hệ
thống vẫn chạy bằng đường cũ.

## Cấu hình

```env
# Nguồn embedding: openai | ollama | local. Bỏ trống = tự dò theo API key sẵn có.
EMBEDDING_BACKEND=
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
LOCAL_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Tìm kiếm lai (mặc định bật)
HYBRID_SEARCH=true
```

## Test

```bash
uv run pytest tests/test_phase_d.py -q
```

## Lưu ý khi sửa Phase này

Phase D vá đè lên module khác lúc import. Đã có một lỗi thật sinh ra từ kiểu nối này (đệ
quy vô hạn khi đọc XREF, xem [`docs/TIEN_DO_DU_AN.md`](docs/TIEN_DO_DU_AN.md) mục 4). Sau
mỗi thay đổi, **chạy đủ bộ test** (`uv run pytest -q`) chứ không chỉ `test_phase_d.py` —
lỗi do ghép module không bao giờ lộ ra khi chạy riêng test của Phase.
