# Bảng Theo dõi Nợ Kỹ thuật (Technical Debt) & Lộ trình Nâng cấp

Tài liệu này ghi nhận các giới hạn kỹ thuật hiện tại của dự án MEP-Agents và định hướng nâng cấp trong các Phase tiếp theo để tiến tới chuẩn Enterprise SaaS.

## Tổng quan mức ưu tiên

| # | Mục | Mức độ | Trạng thái |
|---|-----|--------|------------|
| 7 | Bảo mật API (path traversal + không xác thực) | 🔴 Khẩn cấp | Chưa làm |
| 1 | Database & lưu trữ (Postgres/pgvector/S3) | 🟠 Cao | Chưa làm |
| 3 | Hạ tầng triển khai (Docker) | 🟠 Cao | Chưa làm |
| 4 | Real-time (WebSocket) | 🟡 Trung bình | Đã làm 1 phần |
| 8 | Plugin/Web hardcode địa chỉ server | 🟡 Trung bình | Đã làm 1 phần (Revit/AutoCAD xong, Web chưa) |
| 5 | Computer Vision (YOLO cho bản vẽ rác) | 🟡 Trung bình | Đã làm 1 phần |
| 9 | Kiểm thử thật với Revit/AutoCAD + E2E | 🟡 Trung bình | Chưa làm |
| 2 | Local LLM / Air-gapped (cần GPU lớn) | 🟢 Thấp | Chưa làm |
| 6 | Billing / đăng nhập | 🟢 Thấp (tùy mô hình kinh doanh) | Chưa làm |

---

## 7. Bảo mật API (phát hiện khi rà soát, chưa từng ghi nhận trước đây) 🔴

- **Path traversal / arbitrary file write tại `/api/v1/takeoff`:** `src/api.py` →
  `upload_and_takeoff` ghi file trực tiếp bằng
  `os.path.join(UPLOAD_DIR, file.filename)` — **không hề gọi `resolve_safe_path`**
  như các tool CAD khác trong `src/tools.py`. Client tự đặt tên file trong
  multipart upload; một filename kiểu `../../../etc/cron.d/x` hoặc chứa `/` sẽ khiến
  `os.path.join` ghi ra NGOÀI `UPLOAD_DIR`. Đây là lỗ hổng ghi file tùy ý trên
  endpoint không cần xác thực.
  **Việc cần làm:** validate/sanitize `file.filename` (chỉ lấy `os.path.basename`,
  chặn ký tự `..`/`/`, giới hạn đuôi file `.dwg`/`.dxf`) trước khi ghép đường dẫn,
  giống cách `download_revit_boq` đã làm đúng (`os.path.basename` + kiểm tra
  `startswith(UPLOAD_DIR)`).
- **Không có xác thực/phân quyền trên BẤT KỲ endpoint FastAPI nào:** `/api/v1/takeoff`,
  `/api/v1/revit/analyze`, `/api/v1/autocad/analyze`, download, WebSocket — ai có thể
  gọi tới server đều dùng được toàn bộ, kể cả upload/ghi file và tiêu tốn tài
  nguyên Celery worker. Chấp nhận được cho môi trường dev/nội bộ, nhưng KHÔNG an
  toàn nếu public ra Internet. Cần API key hoặc JWT tối thiểu trước khi deploy
  ngoài mạng nội bộ — có thể làm cùng lúc với hạng mục 6 (đăng nhập/billing).
- **`CORSMiddleware` cấu hình `allow_origins=["*"]` cùng `allow_credentials=True`:**
  đây là tổ hợp mà trình duyệt hiện đại tự chặn theo spec CORS (không cho credential
  đi kèm origin wildcard), nên hiện tại about phần `allow_credentials=True` gần như
  vô nghĩa — nhưng lại dễ đánh lừa người đọc code là "đã bật kiểm soát credential"
  trong khi thực chất origin đang mở hoàn toàn. Cần xác định danh sách origin thật
  (domain Web App) khi triển khai production thay vì để `*`.

## 1. Cơ sở dữ liệu (Database) & Lưu trữ 🟠

- **Tình trạng hiện tại:** Đang sử dụng Redis làm Message Broker và Cache tạm thời. Các file Excel khối lượng (BOQ) được lưu thẳng vào thư mục `uploads/` trên ổ cứng. Hệ thống Vector Search cho tiêu chuẩn MEPF (FAISS) cũng lưu file index `.faiss` trên disk cục bộ.
- **Vấn đề (Nợ kỹ thuật):** Không thể quản lý dữ liệu người dùng đa luồng (Multi-tenant) một cách an toàn. Mất dữ liệu khi chuyển server hoặc restart nếu không backup ổ cứng. FAISS local khó đồng bộ khi Scale nhiều worker.
- **Hướng giải quyết (Phase 5):**
  - Tích hợp **PostgreSQL** để lưu thông tin tài khoản, lịch sử dự án.
  - Sử dụng **pgvector** (extension của PostgreSQL) thay thế FAISS để quản lý CSDL Vector tập trung.
  - Sử dụng AWS S3 (hoặc MinIO) để lưu file CAD/Excel thay vì lưu vào disk cục bộ.

## 2. Giới hạn Phần cứng & Tự chủ AI (Offline Mode) 🟢

- **Tình trạng hiện tại:** Cấu hình máy chủ phát triển (Core i7, 32GB RAM, RTX A1000 6GB VRAM) gánh rất tốt các tác vụ thuật toán CAD (ezdxf) và luồng API. Tuy nhiên phần AI Core (LangGraph) đang phụ thuộc vào Cloud API (Groq/Gemini).
- **Vấn đề (Nợ kỹ thuật):** Nếu khách hàng khối MEP yêu cầu "Air-gapped" (bảo mật 100%, không Internet), việc chạy Local LLM (VD: Llama-3 8B) tốn khoảng 6-8GB VRAM, vượt quá khả năng của GPU hiện tại.
- **Hướng giải quyết:** Bổ sung cấu hình Server vật lý với GPU **16GB - 24GB VRAM** (RTX 4080/4090) cho các gói cài đặt nội bộ (On-premise).

## 3. Hạ tầng Triển khai (Deployment) 🟠

- **Tình trạng hiện tại:** Hệ thống đang chạy trực tiếp trên môi trường Windows (thông qua `uv`, `celery worker`, `redis-server`).
- **Vấn đề (Nợ kỹ thuật):** Rủi ro "It works on my machine" (Chạy được trên máy dev nhưng lỗi trên server production). Khó tự động mở rộng (Auto-scaling).
- **Hướng giải quyết:** Viết `Dockerfile` và `docker-compose.yml` để đóng gói toàn bộ Frontend (React), Backend (FastAPI), Worker (Celery) và Broker (Redis). Sẵn sàng deploy lên AWS/GCP hoặc Kubernetes.
- Ghi chú: repo đã có `Dockerfile` ở gốc dự án, nhưng chỉ đóng gói **Streamlit app**
  (`CMD ["uv", "run", "streamlit", "run", "app.py", ...]`, expose port 8501) — KHÔNG bao
  gồm FastAPI (`src/api.py`), Celery worker, Redis, hay Web App React (`web/`). Vẫn cần
  viết `docker-compose.yml` (hoặc thêm Dockerfile riêng cho từng service) để đóng gói đủ
  4 thành phần như mô tả ở trên; chưa nên coi mục này là "đã có Docker" chỉ vì có 1 file
  Dockerfile.

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

## 6. Mô hình Kinh doanh (SaaS Billing) 🟢

- **Tình trạng hiện tại:** Miễn phí và chưa có cơ chế đăng nhập.
- **Vấn đề (Nợ kỹ thuật):** Chưa thể thu hồi vốn và sinh lời.
- **Hướng giải quyết (Phase 5):** Tích hợp cổng thanh toán (Stripe / VNPay). Thu phí theo số lượng bản vẽ upload hoặc gói đăng ký (Subscription). Nên làm cùng lúc với xác thực API ở mục 7 — hiện chưa có khái niệm "user" nào ở tầng API để gắn billing vào.

## 8. Địa chỉ server bị hardcode trong Web App 🟡

- **Đã làm:** plugin Revit (`config.json`/`MEP_AGENTS_API_BASE`) và AutoCAD
  (`MEP_AGENTS_HOME`/`MEP_AGENTS_API_BASE`) đã hết hardcode, đọc cấu hình qua biến môi
  trường (xem `README_WINDOWS.md` mục 5).
- **Chưa làm:** `web/src/App.jsx` vẫn hardcode `API_URL = 'http://localhost:8083/api/v1'`
  và `WS_URL = 'ws://localhost:8083/ws'` ngay trong code — cùng dạng vấn đề vừa sửa ở 2
  plugin kia nhưng CHƯA áp dụng cho Web App. Khi build production (`npm run build`) trỏ
  tới domain khác, phải đổi tay 2 hằng số này rồi build lại. Nên đọc qua biến môi trường
  Vite (`import.meta.env.VITE_API_BASE`, file `.env`/`.env.production`) thay vì hardcode.

## 9. Kiểm thử thật & End-to-End 🟡

- **Plugin Revit/AutoCAD chưa từng chạy trong phần mềm thật:** toàn bộ thay đổi ở
  `revit/` và `autocad/` (kể cả bản nâng cấp gần đây) mới chỉ được kiểm tra bằng
  `ast.parse`/đọc code, KHÔNG chạy được trong Revit (IronPython + pyRevit) hay AutoCAD
  (COM) thật vì môi trường phát triển hiện tại không có 2 phần mềm đó cài sẵn. Rủi ro:
  lỗi runtime đặc thù IronPython 2.7 (VD cú pháp `except Exception, e:` kiểu Python 2,
  hoặc API `pyrevit.forms` không đúng như kỳ vọng) sẽ không bị bắt cho tới khi người
  dùng thật chạy thử.
- **Chưa có test end-to-end toàn luồng:** test hiện tại (`tests/*.py`, 392 test) đều là
  unit/integration test ở mức module Python, mock Celery/Redis. Chưa có kịch bản test
  chạy thật: upload file CAD thật → Celery worker thật (Redis thật) → nhận kết quả Excel
  thật → tải về. Cũng chưa có test UI (Playwright/Cypress) cho `web/`.
