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

## Cấu hình tìm kiếm lai

Hybrid **mặc định đã bật** (`hybrid_search: bool = True` trong `src/config.py`), tắt bằng
`HYBRID_SEARCH=false`. Nó gộp hai nhánh bằng RRF:

| Nhánh | Cần gì | Thiếu thì |
|---|---|---|
| Từ khóa | thư mục `STANDARDS_DIR` (mặc định `data/standards`) có file `.txt` | nhánh này không ra kết quả |
| Vector | nguồn embedding + index đã nạp | tự rơi về nhánh từ khóa |

Nhánh vector cần hai thứ — nguồn embedding và một index đã nạp:

```env
# 1. Nguồn embedding: openai | ollama | local
#    Bỏ trống = tự dò: có OPENAI_API_KEY → openai; có OLLAMA_BASE_URL → ollama; còn lại → local
EMBEDDING_BACKEND=local
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
LOCAL_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2

# 2. Nơi lưu index: FAISS (mặc định) hoặc pgvector
FAISS_INDEX_PATH=faiss_index
# USE_PGVECTOR=true
# DATABASE_URL=postgresql://...

# Tìm kiếm lai (mặc định bật)
HYBRID_SEARCH=true
```

Rồi nạp tiêu chuẩn vào index:

```bash
uv run python -m src.ingest      # in ra "Nguồn embedding: ..." để biết đang dùng đường nào
```

Chạy hoàn toàn offline (`EMBEDDING_BACKEND=local` hoặc `ollama`) **không cần**
`OPENAI_API_KEY`. Trước đây `src/ingest.py` chặn cứng ở biến này nên offline không nạp
được index và hybrid mất hẳn nhánh vector mà không có dấu hiệu gì — nay chỉ chặn khi
nguồn embedding đang thực sự là `openai`.

## Điểm mở rộng tra cứu tiêu chuẩn

Đường tra cứu đăng ký qua `src/standards_backend.py` theo mức ưu tiên, thay vì tráo đối
tượng tool `search_standards`:

| Backend | Ưu tiên | Đăng ký ở |
|---|---:|---|
| `hybrid` | 20 | `src/agents_phase_d_patch.py` |
| `vectorstore` | 10 | `src/vector_search_bind.py` |
| (dự phòng) tra từ khóa offline | — | `src/tools.py::_legacy_faiss_search` |

Backend nào lỗi hoặc không có kết quả thì tự nhường xuống đường tiếp theo, nên tra cứu
tiêu chuẩn luôn trả về câu trả lời dùng được.

## Test

```bash
uv run pytest tests/test_phase_d.py -q
```

## Lưu ý khi sửa Phase này

Phase D vá đè lên module khác lúc import. Đã có một lỗi thật sinh ra từ kiểu nối này (đệ
quy vô hạn khi đọc XREF, xem [`docs/TIEN_DO_DU_AN.md`](docs/TIEN_DO_DU_AN.md) mục 4). Sau
mỗi thay đổi, **chạy đủ bộ test** (`uv run pytest -q`) chứ không chỉ `test_phase_d.py` —
lỗi do ghép module không bao giờ lộ ra khi chạy riêng test của Phase.
