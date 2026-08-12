# Bảng Theo dõi Nợ Kỹ thuật (Technical Debt) & Lộ trình Nâng cấp

Tài liệu này ghi nhận các giới hạn kỹ thuật hiện tại của dự án MEP-Agents và định hướng nâng cấp trong các Phase tiếp theo để tiến tới chuẩn Enterprise SaaS.

## 1. Cơ sở dữ liệu (Database) & Lưu trữ
- **Tình trạng hiện tại:** Đang sử dụng Redis làm Message Broker và Cache tạm thời. Các file Excel khối lượng (BOQ) được lưu thẳng vào thư mục `uploads/` trên ổ cứng. Hệ thống Vector Search cho tiêu chuẩn MEPF (FAISS) cũng lưu file index `.faiss` trên disk cục bộ.
- **Vấn đề (Nợ kỹ thuật):** Không thể quản lý dữ liệu người dùng đa luồng (Multi-tenant) một cách an toàn. Mất dữ liệu khi chuyển server hoặc restart nếu không backup ổ cứng. FAISS local khó đồng bộ khi Scale nhiều worker.
- **Hướng giải quyết (Phase 5):** 
  - Tích hợp **PostgreSQL** để lưu thông tin tài khoản, lịch sử dự án.
  - Sử dụng **pgvector** (extension của PostgreSQL) thay thế FAISS để quản lý CSDL Vector tập trung.
  - Sử dụng AWS S3 (hoặc MinIO) để lưu file CAD/Excel thay vì lưu vào disk cục bộ.

## 2. Giới hạn Phần cứng & Tự chủ AI (Offline Mode)
- **Tình trạng hiện tại:** Cấu hình máy chủ phát triển (Core i7, 32GB RAM, RTX A1000 6GB VRAM) gánh rất tốt các tác vụ thuật toán CAD (ezdxf) và luồng API. Tuy nhiên phần AI Core (LangGraph) đang phụ thuộc vào Cloud API (Groq/Gemini).
- **Vấn đề (Nợ kỹ thuật):** Nếu khách hàng khối MEP yêu cầu "Air-gapped" (bảo mật 100%, không Internet), việc chạy Local LLM (VD: Llama-3 8B) tốn khoảng 6-8GB VRAM, vượt quá khả năng của GPU hiện tại.
- **Hướng giải quyết:** Bổ sung cấu hình Server vật lý với GPU **16GB - 24GB VRAM** (RTX 4080/4090) cho các gói cài đặt nội bộ (On-premise).

## 3. Hạ tầng Triển khai (Deployment)
- **Tình trạng hiện tại:** Hệ thống đang chạy trực tiếp trên môi trường Windows (thông qua `uv`, `celery worker`, `redis-server`).
- **Vấn đề (Nợ kỹ thuật):** Rủi ro "It works on my machine" (Chạy được trên máy dev nhưng lỗi trên server production). Khó tự động mở rộng (Auto-scaling).
- **Hướng giải quyết:** Viết `Dockerfile` và `docker-compose.yml` để đóng gói toàn bộ Frontend (React), Backend (FastAPI), Worker (Celery) và Broker (Redis). Sẵn sàng deploy lên AWS/GCP hoặc Kubernetes.

## 4. Giao tiếp Thời gian thực (Real-time Communication)
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

## 5. Thị giác Máy tính (Computer Vision)
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

## 6. Mô hình Kinh doanh (SaaS Billing)
- **Tình trạng hiện tại:** Miễn phí và chưa có cơ chế đăng nhập.
- **Vấn đề (Nợ kỹ thuật):** Chưa thể thu hồi vốn và sinh lời.
- **Hướng giải quyết (Phase 5):** Tích hợp cổng thanh toán (Stripe / VNPay). Thu phí theo số lượng bản vẽ upload hoặc gói đăng ký (Subscription).
