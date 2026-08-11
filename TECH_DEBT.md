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
- **Tình trạng hiện tại:** Web App đang dùng phương pháp thăm dò (Polling) tới endpoint `/api/v1/task/{task_id}` để lấy trạng thái Celery. Plugin AutoCAD/Revit chỉ gửi file lên và thông báo "Đang xử lý ngầm".
- **Vấn đề (Nợ kỹ thuật):** Polling tốn tài nguyên mạng và tạo độ trễ. AutoCAD/Revit không nhận được kết quả chi tiết trực tiếp ngay khi AI phân tích xong.
- **Hướng giải quyết:** Bổ sung **WebSocket** vào FastAPI để đẩy log trực tiếp (Push) từ Celery về cho Web App và cả Terminal của CAD/Revit theo thời gian thực (Real-time).

## 5. Thị giác Máy tính (Computer Vision)
- **Tình trạng hiện tại:** Đã cài đặt xong môi trường PyTorch CUDA 12.1.
- **Vấn đề (Nợ kỹ thuật):** Khả năng bóc khối lượng hiện tại phụ thuộc 100% vào việc bản vẽ được vẽ đúng chuẩn (Dùng Block, Polyline nguyên vẹn). Nếu gặp bản vẽ "rác" (Nổ block, vẽ bằng Line rời rạc), AI hình học sẽ bỏ sót.
- **Hướng giải quyết:** Huấn luyện (Train) một mô hình YOLOv11 chuyên dụng để quét ảnh bản vẽ (tạo ra từ tool `render_cad_image`) và nhận diện các thiết bị MEP thông qua hình dáng, bù đắp cho lỗ hổng dữ liệu CAD bị mất.

## 6. Mô hình Kinh doanh (SaaS Billing)
- **Tình trạng hiện tại:** Miễn phí và chưa có cơ chế đăng nhập.
- **Vấn đề (Nợ kỹ thuật):** Chưa thể thu hồi vốn và sinh lời.
- **Hướng giải quyết (Phase 5):** Tích hợp cổng thanh toán (Stripe / VNPay). Thu phí theo số lượng bản vẽ upload hoặc gói đăng ký (Subscription).
