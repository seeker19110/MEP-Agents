# Bảng Theo dõi Nợ Kỹ thuật (Technical Debt) & Lộ trình Nâng cấp

Tài liệu này ghi nhận các giới hạn kỹ thuật hiện tại của dự án MEP-Agents và định hướng nâng cấp trong các Phase tiếp theo để tiến tới chuẩn Enterprise SaaS.

Trạng thái tổng thể và số liệu hiện hành nằm ở [`docs/TIEN_DO_DU_AN.md`](docs/TIEN_DO_DU_AN.md).

## Tổng quan mức ưu tiên

| # | Mục | Mức độ | Trạng thái |
|---|-----|--------|------------|
| 7 | Bảo mật API (path traversal + không xác thực) | 🔴 Khẩn cấp | ✅ Đã trả (path traversal + API key + CORS) |
| 1 | Database & lưu trữ (Postgres/pgvector/S3) | 🟠 Cao | Chưa làm — cần hạ tầng thật, xem lý do bên dưới |
| 3 | Hạ tầng triển khai (Docker) | 🟠 Cao | ✅ Đã viết đủ 4 service — **chưa chạy thử được** (không có Docker daemon ở môi trường viết code) |
| 4 | Real-time (WebSocket) | 🟡 Trung bình | Đã làm 1 phần |
| 8 | Plugin/Web hardcode địa chỉ server | 🟡 Trung bình | ✅ Đã trả (Revit/AutoCAD/Web đều hết hardcode) |
| 5 | Computer Vision (YOLO cho bản vẽ rác) | 🟡 Trung bình | Đã làm 1 phần — cần dữ liệu gán nhãn thật |
| 9 | Kiểm thử thật với Revit/AutoCAD + E2E | 🟡 Trung bình | ✅ E2E (hạ tầng thật) + test UI Playwright đều đã chạy đạt; Revit/AutoCAD vẫn chưa |
| 11 | Bảng đơn giá cũ mà không ai cảnh báo | 🟠 Cao | ✅ Đã trả — xem mục 11 |
| 12 | Vòng lặp import giữa `tools.py` và `qs_tools.py` | 🟢 Thấp | ✅ Đã trả — xem mục 12 |
| 2 | Local LLM / Air-gapped (cần GPU lớn) | 🟢 Thấp | Chưa làm — cần phần cứng thật |
| 6 | Billing / đăng nhập | 🟢 Thấp (tùy mô hình kinh doanh) | Chưa làm — cần tài khoản cổng thanh toán thật |
| 10 | Rủi ro của kiến trúc "patch lúc import" | 🟠 Cao | ✅ Đã trả — không còn chỗ nào gán đè hàm/tool; xem mục 10 |

**Không trả được trong lượt này** (mục 1, 2, 6, và phần "chạy thử thật" của mục 3/9): đều
cần tài nguyên không có sẵn trong môi trường viết code hiện tại — dịch vụ Postgres/S3 thật
để migrate vào, GPU 16-24GB VRAM vật lý, tài khoản Stripe/VNPay thật, hoặc Docker
daemon/Revit/AutoCAD cài sẵn để chạy thử. Viết code đoán trước cho những việc này (VD tự
bịa schema Postgres chưa ai duyệt, tự đăng ký Stripe giả) rủi ro cao hơn lợi ích — để lại
đúng như backlog, chờ người có tài nguyên đó cầm tay làm cùng.

---

## 7. Bảo mật API ✅ Đã trả

Phát hiện khi rà soát (chưa từng ghi nhận trước bản cập nhật tài liệu trước), nay đã sửa:

- **Path traversal / arbitrary file write tại `/api/v1/takeoff`** (`src/api.py`): trước
  đây `upload_and_takeoff` ghi file bằng `os.path.join(UPLOAD_DIR, file.filename)` —
  filename client tự đặt trong multipart form có thể chứa `../` để ghi ra ngoài
  `UPLOAD_DIR`. Đã thêm `_safe_upload_filename()`: lấy `os.path.basename`, lọc ký tự lạ,
  ép đuôi file về `.dwg`/`.dxf`. Có test `test_takeoff_upload_sanitizes_path_traversal_filename`
  và `test_takeoff_upload_rejects_non_cad_extension` (`tests/test_api.py`).
- **Không có xác thực trên bất kỳ endpoint nào:** đã thêm dependency `require_api_key`
  (kiểm tra header `X-API-Key`, hoặc query `?api_key=` cho endpoint tải file/WebSocket vì
  điều hướng trình duyệt trực tiếp không set được header) — áp dụng cho mọi endpoint có
  tác dụng phụ (upload, phân tích, tải file, task status, WebSocket). Bật bằng biến môi
  trường `MEP_AGENTS_API_KEY` — **không đặt thì vẫn mở như cũ** (mặc định phù hợp dev cục
  bộ, giữ đúng triết lý "graceful fallback" đã dùng ở chỗ khác trong dự án). Plugin
  Revit/AutoCAD và Web App đều đã cập nhật để gửi kèm key khi có cấu hình.
  **LƯU Ý:** đây KHÔNG phải xác thực người dùng thật (JWT/OAuth đa người dùng) — chỉ là 1
  khóa chung chặn truy cập nặc danh. Xác thực đa người dùng thật vẫn là việc của mục 6.
- **`CORSMiddleware` từng cấu hình `allow_origins=["*"]` cùng `allow_credentials=True`:**
  tổ hợp bị trình duyệt tự chặn theo spec, dễ đánh lừa người đọc code. Đã đổi sang đọc
  danh sách origin từ biến môi trường `CORS_ALLOWED_ORIGINS` (phân tách bằng dấu phẩy),
  mặc định chỉ cho phép origin dev cục bộ (`http://localhost:5173`) thay vì mở toàn bộ.

## 1. Cơ sở dữ liệu (Database) & Lưu trữ 🟠 Chưa làm

- **Tình trạng hiện tại:** Đang sử dụng Redis làm Message Broker và Cache tạm thời. Các file Excel khối lượng (BOQ) được lưu thẳng vào thư mục `uploads/` trên ổ cứng. Hệ thống Vector Search cho tiêu chuẩn MEPF (FAISS) cũng lưu file index `.faiss` trên disk cục bộ.
- **Vấn đề (Nợ kỹ thuật):** Không thể quản lý dữ liệu người dùng đa luồng (Multi-tenant) một cách an toàn. Mất dữ liệu khi chuyển server hoặc restart nếu không backup ổ cứng. FAISS local khó đồng bộ khi Scale nhiều worker.
- **Hướng giải quyết (Phase 5):**
  - Tích hợp **PostgreSQL** để lưu thông tin tài khoản, lịch sử dự án.
  - Sử dụng **pgvector** (extension của PostgreSQL) thay thế FAISS để quản lý CSDL Vector tập trung.
  - Sử dụng AWS S3 (hoặc MinIO) để lưu file CAD/Excel thay vì lưu vào disk cục bộ.
- **Vì sao chưa trả được lượt này:** đây là việc migrate dữ liệu thật sang hạ tầng thật
  (Postgres/S3 cụ thể của ai đó) — viết code migration/schema mà không có instance thật để
  chạy thử và không ai duyệt thiết kế schema là đoán mò, rủi ro cao hơn để trống.

## 2. Giới hạn Phần cứng & Tự chủ AI (Offline Mode) 🟢 Chưa làm

- **Tình trạng hiện tại:** Cấu hình máy chủ phát triển (Core i7, 32GB RAM, RTX A1000 6GB VRAM) gánh rất tốt các tác vụ thuật toán CAD (ezdxf) và luồng API. Tuy nhiên phần AI Core (LangGraph) đang phụ thuộc vào Cloud API (Groq/Gemini).
- **Vấn đề (Nợ kỹ thuật):** Nếu khách hàng khối MEP yêu cầu "Air-gapped" (bảo mật 100%, không Internet), việc chạy Local LLM (VD: Llama-3 8B) tốn khoảng 6-8GB VRAM, vượt quá khả năng của GPU hiện tại.
- **Hướng giải quyết:** Bổ sung cấu hình Server vật lý với GPU **16GB - 24GB VRAM** (RTX 4080/4090) cho các gói cài đặt nội bộ (On-premise).
- **Vì sao chưa trả được:** cần mua/thuê phần cứng GPU thật — không phải việc sửa code.

## 3. Hạ tầng Triển khai (Deployment) 🟠 Đã viết, chưa chạy thử được

- **Đã làm:** thêm `docker-compose.yml` đóng gói đủ 5 service: `redis`, `api` (FastAPI,
  `uvicorn src.api:app`), `worker` (Celery), `streamlit` (`app.py`, UI gốc), `web` (React
  build tĩnh qua `web/Dockerfile` + Nginx). Sửa 2 chỗ hardcode `redis://localhost:6379`
  (`src/celery_app.py`, `src/qs_tools.py`) — trong container, "localhost" là chính
  container đó, không phải service `redis`, nên nếu không sửa thì Worker sẽ không bao giờ
  kết nối được Redis khi chạy qua Compose (âm thầm không nhận task nào, rất khó debug).
  Nay đọc qua biến môi trường `CELERY_BROKER_URL`/`REDIS_HOST`, Compose đặt sẵn, không đặt
  thì vẫn rơi về `localhost` như cũ cho dev cục bộ (không đổi hành vi khi chạy trực tiếp
  bằng `uv run`).
- **CHƯA làm — quan trọng, không tự nhận là xong:** `docker-compose.yml` mới được viết và
  kiểm tra CÚ PHÁP bằng `docker compose config` (parse thành công, resolve đủ 5 service),
  nhưng **CHƯA từng chạy thật bằng `docker compose up --build`** — môi trường viết code
  này không có Docker daemon (`docker info` báo không kết nối được `docker.sock`). Trước
  khi coi mục này là hoàn thành, cần người có Docker daemon thật:
  1. `cp .env.example .env` (điền API key LLM thật) và `cp web/.env.example web/.env`.
  2. `docker compose up --build`.
  3. Xác nhận cả 5 container lên khỏe (`docker compose ps`), Web App (`:5173`) gọi được
     `/api/v1/takeoff` (`:8083`), Worker thực sự nhận và xử lý task (xem log `docker
     compose logs worker`), tải BOQ Excel về thành công.
  Rất có khả năng phát sinh lỗi runtime chưa lường trước (permission thư mục volume,
  thiếu biến môi trường bắt buộc, healthcheck sai lệnh...) chỉ lộ ra khi chạy container
  thật.

## 4. Giao tiếp Thời gian thực (Real-time Communication) 🟡

- **Đã làm (một phần):** Web App (`web/src/App.jsx`) không còn `setInterval` polling HTTP mỗi
  1.5s — nay mở 1 kết nối **WebSocket** tới `/ws/task/{task_id}` (`src/api.py` →
  `ws_task_status`), server chỉ đẩy dữ liệu khi trạng thái thay đổi và tự đóng kết nối khi
  xong. Celery task (`parse_cad_to_db_task`) cũng phát thêm state `PROGRESS` với log chi
  tiết hơn thay vì chỉ có PENDING tĩnh trong lúc chờ.
- **Còn hạn chế (chưa "thật sự" real-time end-to-end):** bản thân server vẫn PHẢI polling
  Celery result backend (Redis) theo chu kỳ 1s bên trong `ws_task_status` — Celery/Redis
  không có cơ chế push sẵn ra ngoài mà không cấu hình thêm Redis Pub/Sub hoặc event
  exchange riêng. Cải thiện đúng nghĩa cần task tự publish sự kiện lên 1 channel Redis
  Pub/Sub khi đổi state, và endpoint WebSocket subscribe channel đó thay vì tự polling.
  Plugin AutoCAD/Revit **vẫn chưa** nhận cập nhật real-time (vẫn là gửi 1 lần rồi chờ HTTP
  response) — đây là phần chưa làm của mục này.

## 5. Thị giác Máy tính (Computer Vision) 🟡

- **Đã làm (một phần):** `src/vision_tools.py` → `detect_cad_symbols_yolo` giờ được **nạp
  vào agent thật** (`src/tools.py` → `tools` + tool set của vai trò `qs`/`cad`/`bim`) —
  trước đây hàm này tồn tại và có test riêng nhưng KHÔNG nằm trong bất kỳ danh sách tool
  nào của agent, nên AI không bao giờ gọi được. Nay dùng được như một tool dự phòng khi
  `auto_quantity_takeoff`/`optimize_cad_drawing` bỏ sót do bản vẽ "rác" (Block bị nổ, Line
  rời rạc): agent tự `render_cad_image` rồi gọi `detect_cad_symbols_yolo` trên ảnh đó.
- **Vẫn CHƯA làm (giới hạn thật, không tự nhận đã xong):** model đang dùng là
  `yolo11n.pt` — pretrained trên **COCO** (đồ vật đời thường), **KHÔNG** được huấn luyện
  riêng để nhận ký hiệu/thiết bị MEPF (van, đầu phun, tủ điện...). Vì vậy kết quả hiện chỉ
  mang tính tham khảo bổ sung, KHÔNG thay thế được kết quả bóc khối lượng bằng hình học.
  Muốn dùng làm nguồn chính cho BOQ, vẫn cần: (1) thu thập + gán nhãn bộ ảnh ký hiệu MEPF
  thật, (2) fine-tune YOLOv11 trên bộ dữ liệu đó, (3) đánh giá độ chính xác trước khi tin
  dùng cho hồ sơ thầu. Đây là phần việc lớn cần dữ liệu thực tế, chưa thể tự động hóa
  trong 1 lượt nâng cấp code.

## 6. Mô hình Kinh doanh (SaaS Billing) 🟢 Chưa làm

- **Tình trạng hiện tại:** Miễn phí và chưa có cơ chế đăng nhập.
- **Vấn đề (Nợ kỹ thuật):** Chưa thể thu hồi vốn và sinh lời.
- **Hướng giải quyết (Phase 5):** Tích hợp cổng thanh toán (Stripe / VNPay). Thu phí theo số lượng bản vẽ upload hoặc gói đăng ký (Subscription). Nên làm cùng lúc với xác thực người dùng thật (JWT/OAuth) — mục 7 chỉ mới có 1 API key CHUNG, chưa có khái niệm "user" riêng để gắn billing vào.
- **Vì sao chưa trả được:** cần tài khoản Stripe/VNPay thật để tích hợp và kiểm thử — không thể tự đăng ký thay người dùng, và code chưa test được với sandbox chưa cấu hình vẫn là code chưa kiểm chứng.

## 8. Địa chỉ server bị hardcode ✅ Đã trả

- Plugin Revit (`config.json`/`MEP_AGENTS_API_BASE`) và AutoCAD
  (`MEP_AGENTS_HOME`/`MEP_AGENTS_API_BASE`) đã hết hardcode từ trước (xem
  `README_WINDOWS.md` mục 5).
- **LLM chạy cục bộ** (`src/agents.py::_build_llm`) từng hardcode `http://localhost:11434`
  cho Ollama và `http://localhost:8000` cho vLLM — sót lại từ đợt trả nợ trước, chỉ lộ ra
  khi thật sự dựng cấu hình lai (LLM cục bộ ở máy riêng / service riêng trong Compose).
  Đáng chú ý là **hai nửa của cùng một cấu hình đi hai đường khác nhau**: phía embedding
  (`src/local_embeddings.py`) vẫn luôn đọc `OLLAMA_BASE_URL`, nên embedding trỏ đúng máy
  còn LLM thì gọi vào chính container của nó rồi báo lỗi kết nối. Nay `resolve_local_base_url()`
  đọc `OLLAMA_BASE_URL`/`OLLAMA_HOST`/`VLLM_BASE_URL`, dùng chung biến với embedding và tự
  chuẩn hóa đuôi `/v1`; không đặt thì vẫn về `localhost` như cũ. `base_url` cũng được đưa
  vào khóa `lru_cache` của `_build_llm` — đổi địa chỉ trong `.env` phải tạo client mới.
- **Web App** (`web/src/App.jsx`) trước đây hardcode `http://localhost:8083` — nay đọc qua
  biến môi trường Vite `VITE_API_BASE`/`VITE_WS_BASE`/`VITE_API_KEY` (`web/.env.example`),
  không đặt thì vẫn rơi về `localhost:8083` như cũ cho dev. Lưu ý: biến `VITE_*` là
  build-time (Vite bake vào bundle JS lúc `npm run build`), đổi giá trị sau khi đã build
  đòi build lại, không đọc được lúc container đang chạy.

## 9. Kiểm thử thật & End-to-End 🟡 Chưa làm

- **Plugin Revit/AutoCAD chưa từng chạy trong phần mềm thật:** toàn bộ thay đổi ở
  `revit/` và `autocad/` (kể cả các bản nâng cấp gần đây, bao gồm API key vừa thêm) mới
  chỉ được kiểm tra bằng `ast.parse`/đọc code, KHÔNG chạy được trong Revit (IronPython +
  pyRevit) hay AutoCAD (COM) thật vì môi trường phát triển hiện tại không có 2 phần mềm đó
  cài sẵn. Rủi ro: lỗi runtime đặc thù IronPython 2.7 (VD cú pháp Python 2, hoặc API
  `pyrevit.forms` không đúng như kỳ vọng) sẽ không bị bắt cho tới khi người dùng thật chạy
  thử.
- **`docker-compose.yml` mới (mục 3) cũng thuộc nhóm này** — viết xong nhưng chưa chạy
  thật, xem chi tiết ở mục 3.
- **✅ ĐÃ CÓ test end-to-end** (bổ sung 2026-08-13): hai tầng, xem [`docs/E2E.md`](docs/E2E.md).
  Tầng 1 (`tests/test_e2e_takeoff.py`, chạy trong CI) đi trọn đường bản vẽ → khối lượng →
  Excel thật → tải về, chỉ thay broker bằng gọi đồng bộ. Tầng 2 (`scripts/e2e_smoke.py`)
  không giả lập gì: **đã chạy đạt** với Redis thật, worker Celery ở tiến trình riêng và
  FastAPI thật — tải lên → worker nhặt task qua Redis → Excel 5.582 byte → tải về, tổng
  chiều dài khớp hình học. Đường xác thực `MEP_AGENTS_API_KEY` cũng đã kiểm (thiếu khóa →
  401, có khóa → đạt). **Vẫn chưa chạy qua `docker compose up --build`** — xem mục 3.
  ✅ **Đã có test UI cho `web/`** (bổ sung cùng ngày): 7 kịch bản Playwright chạy trên
  Chromium thật, gồm trọn đường thả bản vẽ → phân tích → WebSocket → tải Excel. Xem
  [`docs/E2E.md`](docs/E2E.md) tầng 3.
- **Bối cảnh cũ:** test hiện tại (`tests/*.py`, 551 test) đều là
  unit/integration test ở mức module Python, mock Celery/Redis. Chưa có kịch bản test
  chạy thật: upload file CAD thật → Celery worker thật (Redis thật) → nhận kết quả Excel
  thật → tải về. Cũng chưa có test UI (Playwright/Cypress) cho `web/`.

## 10. Rủi ro của kiến trúc "patch lúc import" 🟠 Mới ghi nhận (2026-08-13)

- **Tình trạng hiện tại:** cả 4 Phase (A/B/C/D) đều nối vào hệ thống bằng cách vá đè lên
  module khác lúc import (`src/agents_phase_*_patch.py`, `src/*_bind.py`,
  `src/cad_loader_perf_patch.py`). Lý do ban đầu hợp lý: giữ `agents.py`/`tools.py` khỏi
  phình to, mỗi Phase tách bạch và gỡ ra được.
- **Vấn đề (đã thành sự thật, không còn là giả định):** PR #32 phát hiện `cad_cache` gọi
  ngược `ezdxf.readfile` trong khi `cad_loader_perf_patch` đã tạm gán chính tên đó thành
  `readfile_cached` → hàm tự gọi chính mình, đệ quy vô hạn. Hệ quả: **mọi XREF đều thất
  bại im lặng**, nội dung xref bị loại khỏi khối lượng. Từng module đứng riêng đều đúng;
  chỉ sai khi ghép — nên test riêng của từng Phase vẫn xanh, chỉ bộ test đầy đủ mới bắt được.
- **Cùng đợt đó còn 2 lỗi nữa sinh ra từ việc patch ghi đè bản cũ:**
  `detect_cad_symbols_yolo` mất bước `resolve_safe_path` khi Phase C viết lại, và
  `ingest.load_standard_docs` mất nhánh xử lý thư mục chưa tồn tại.
- **Đã làm (đợt 2, sau khi rà lại toàn bộ tầng patch):**
  1. ✅ Module bị patch giữ tham chiếu hàm gốc **ngay lúc import** — đã áp dụng cho
     `cad_cache`.
  2. ✅ **Rà hết các patch còn lại** (`agents_perf_patch`, `qs_perf_patch`,
     `vector_search_bind`, `tools_lazy`, `agents_phase_d_patch`) tìm cùng kiểu lỗi:
     **không có ca đệ quy thứ hai**. Các chỗ gọi qua `cad_loader.load_drawing`,
     `vectorstore.get_embeddings` là cố ý và patch ăn đúng.
  3. ✅ **Nhưng phát hiện một lỗi khác cùng gốc:** `cad_loader_perf_patch` gán đè biến
     toàn cục `ezdxf.readfile` suốt lời gọi gộp xref rồi khôi phục trong `finally`. Phase
     D chạy các bộ phận song song bằng thread, nên hai lời gọi chồng nhau sẽ khôi phục
     nhầm của nhau và làm `ezdxf.readfile` **kẹt vĩnh viễn ở bản cache** — mọi chỗ đọc DXF
     sau đó nhận về cùng một doc dùng chung, ai sửa doc là hỏng dữ liệu của người khác.
     Nay `resolve_xref_segments` nhận hàm đọc qua **tham số**, không đụng biến toàn cục.
     Có test khóa bất biến này (`tests/test_perf_global.py`).
  4. ✅ **Gộp 8 skill Phase A/B vào registry chính** (`src/tools.py`): `TOOLS_BY_ROLE` và
     danh sách `tools` nay chứa sẵn `replace_blocks_by_mapping`, `batch_edit_pipes`,
     `batch_replace_text`, `update_title_block`, `prepare_drawing`, `full_boq`,
     `qs_audit_checklist`, `compare_boq`. Tầng patch vẫn còn và vẫn chạy, nhưng chỉ còn là
     mạng lưới an toàn (các hàm append đều bỏ qua tool đã có). `src/graph.py` không phải
     ghép tay danh sách nữa. Bộ tool của mọi vai trò **không đổi** — đã đối chiếu số lượng
     trước/sau và kiểm tra không có tool trùng tên
     (`tests/test_registry_consolidation.py`).
- **Đã làm (đợt 3):**
  5. ✅ **Phase C/D thôi tráo đối tượng tool.** Thêm `src/standards_backend.py` làm điểm
     mở rộng: backend đăng ký theo mức ưu tiên (`hybrid` 20 > `vectorstore` 10 > tra từ
     khóa offline), backend lỗi hoặc rỗng thì tự nhường xuống đường dưới. `search_standards`
     giữ nguyên danh tính suốt vòng đời tiến trình — không còn cảnh ai đã sao chép danh
     sách tool từ trước thì cầm nhầm bản cũ, và thêm chỗ chứa tool mới trong `tools.py`
     không còn buộc phải nhớ sửa hàm `_swap` ở hai module patch.
  6. ✅ **Nguồn embedding vào thẳng `vectorstore.get_embeddings`**, bỏ `_patch_embeddings`
     của Phase D. Việc này sửa một lỗi thật đi kèm: `python -m src.ingest` không import
     `src.graph` nên patch không chạy, `get_embeddings` kẹt ở đường OpenAI. Cộng với việc
     `ingest.main()` chặn cứng ở `OPENAI_API_KEY`, hệ quả là **chạy offline không nạp được
     index** — hybrid mất hẳn nhánh vector mà không có dấu hiệu gì. Nay chỉ chặn khi nguồn
     embedding thực sự là `openai`.
  7. ✅ Xóa `get_tools_for_role_cached()` trong `src/tools_lazy.py` (không ai gọi).
- **Đã làm (đợt 4 — hết phần bọc node):**
  8. ✅ **Thêm `src/supervisor_pipeline.py`** — điểm nối kiểu middleware cho node điều
     phối. Phase B (chốt chặn HIL + hàng đợi đa ý định) và Phase D (fan-out song song) nay
     **đăng ký lớp** thay vì gán đè `agents.supervisor_node`. Ba chỗ mong manh được gỡ:
     thứ tự các lớp nằm ở mức ưu tiên chứ không phụ thuộc thứ tự import; hàm
     `supervisor_node` giữ nguyên danh tính nên `from src.agents import supervisor_node`
     ở bất kỳ đâu cũng nhận đủ hành vi (`src/graph.py` không còn phải đọc lại
     `_agents_mod.supervisor_node` sau các dòng import patch); và đăng ký trùng tên thì
     thay thế chứ không chồng lớp. Một lớp ném lỗi chỉ bị bỏ qua kèm cảnh báo, không làm
     treo cả phiên làm việc.
  9. ✅ **`DELIVERABLE_TOOLS` khai báo thẳng trong `src/agents.py`**, không cộng bằng patch
     nữa. `agents_phase_a_patch` rút xuống còn lớp kiểm tra: thiếu skill thì log cảnh báo
     thay vì để hệ thống chạy thiếu trong im lặng.
  - Kiểm chứng tương đương: chạy cùng 10 tình huống định tuyến đại diện (đa ý định, đơn ý
    định, fan-out M/E/P/F, duyệt khi đang chờ, duyệt khi không chờ, sau Reviewer đạt/từ
    chối, còn hàng đợi, rỗng) trên bản trước và sau — **kết quả giống hệt từng trường**.
    E2E hạ tầng thật chạy lại cũng đạt.
- **Còn lại (chưa làm, có chủ đích):**
  - `agents_perf_patch` (cắt bớt message) và `qs_perf_patch` (cache đơn giá) vẫn là patch
    lúc import. Đây là bọc thuần túy quanh một hàm, không tráo đối tượng và không phụ
    thuộc thứ tự với nhau, nên không dính lớp lỗi đã gặp. Để lại có chủ đích: dựng thêm
    một tầng đăng ký cho hai chỗ này là thêm phức tạp mà không đổi được rủi ro.
  - Bắt buộc chạy `uv run pytest -q` **đủ bộ** trước khi hợp nhất mọi PR, không chỉ test
    của Phase đang làm.


## 11. Bảng đơn giá cũ mà không ai cảnh báo ✅ Đã trả

- **Rủi ro (nghiệp vụ, không phải kỹ thuật):** đầu ra của bộ phận QS là **con số tiền đi
  vào hồ sơ thầu**. `data/unit_prices.csv` quyết định con số đó, nhưng trước đây không có
  cơ chế nào cho biết bảng giá cập nhật lần cuối bao giờ. Một bảng giá ba năm trước vẫn
  cho ra bảng dự toán trông hoàn chỉnh, đủ đầu mục, không một dấu hiệu nào — vi phạm đúng
  nguyên tắc số 2 của dự án ("không bỏ sót âm thầm"), ở chỗ tốn kém nhất.
- **Đã làm:** thêm `data/unit_prices.meta.json` khai báo `ngay_hieu_luc` + `nguon`, và
  `unit_price_freshness_note()` trong `src/qs_tools.py`. Quá `UNIT_PRICE_MAX_AGE_DAYS`
  (mặc định 180 ngày) thì **chính báo cáo dự toán** mang theo dòng cảnh báo — để trong log
  thì không ai đọc. Không khai báo ngày, hoặc ngày sai định dạng, cũng bị nói ra.
- **Vì sao không dùng thời gian sửa file:** `git clone` đặt lại mtime của mọi file thành
  thời điểm clone, nên bảng giá cũ sẽ trông như vừa cập nhật hôm nay — chính xác là kiểu
  sai lệch âm thầm cần tránh. Ngày hiệu lực phải do người cập nhật khai báo.
- **Còn lại:** đơn giá trong repo vẫn là **giá tham khảo nội bộ, chưa đối chiếu công bố
  giá của Sở Xây dựng**, và chưa phân theo vùng. Đây là việc của người có số liệu thật.

## 12. Vòng lặp import giữa `tools.py` và `qs_tools.py` ✅ Đã trả

- **Vấn đề:** `qs_tools` import `normalize_mepf_parameter_spec` từ `tools`, còn `tools`
  import ngược một loạt tool từ `qs_tools` — cả hai ở mức module. Hệ quả:
  - `import src.qs_tools` **trực tiếp** vỡ với `partially initialized module`; chỉ chạy
    được nhờ mọi đường vào hệ thống vô tình chạm `src.tools` trước.
  - Cả hai file phải dồn import xuống **giữa/cuối file** kèm `# noqa: E402` và một đoạn
    chú thích dài giải thích vì sao — người đọc sau dễ tưởng là tùy tiện, "dọn" lên đầu
    rồi làm vỡ.
  - `src/api.py` phải nạp `build_revit_boq_excel` **vòng qua** `src.tools` thay vì lấy
    thẳng từ nơi định nghĩa.
- **Đã làm:** tách hàm dùng chung sang **`src/mepf_spec.py`** — module nền thuần văn bản,
  chỉ phụ thuộc `re`, **không import module nào của dự án** (có test canh điều kiện này).
  Vòng lặp đứt hẳn, kéo theo:
  - Toàn bộ import của `tools.py` và `qs_tools.py` về đúng đầu file; **không còn một
    `# noqa: E402` nào** trong hai file.
  - `src/api.py` nạp thẳng từ `src.qs_tools`.
  - `tools.py` vẫn re-export `normalize_mepf_parameter_spec` nên mã sẵn có không phải sửa.
- **Kiểm chứng:** `tests/test_no_import_cycles.py` nạp **từng module lõi trong một tiến
  trình sạch** (`python -c "import src.X"`), nên vòng lặp quay lại là đỏ ngay — đã thử tái
  lập vòng cũ để xác nhận test bắt được. Ngoài ra E2E hạ tầng thật và 7 test giao diện đều
  chạy lại đạt, vì đổi thứ tự import là đúng loại thay đổi chỉ vỡ lúc chạy thật.
