# Hướng dẫn Khởi chạy MEP-Agents trên Windows

Dưới đây là các bước chuẩn để khởi động toàn bộ hệ thống MEP-Agents trên môi trường Windows (Local) từ con số 0. Hệ thống này bao gồm 3 thành phần chính: Web UI (React/Vite), Backend (FastAPI), và Hàng đợi nền (Celery + Redis).

## 1. Yêu cầu hệ thống (Prerequisites)
Đảm bảo máy tính Windows của bạn đã cài đặt các công cụ sau:
- **Python 3.10+** (Khuyên dùng `uv` để quản lý môi trường).
- **Node.js 18+** (để chạy npm/Vite).
- **Redis Server cho Windows** (Có thể tải bản build của Memurai hoặc Redis cho Windows bản port, hoặc dùng WSL2).

## 2. Chuẩn bị môi trường Python

Mở Terminal (PowerShell hoặc Command Prompt) tại thư mục gốc của dự án (`MEP-Agents/`):

```powershell
# Tạo và kích hoạt môi trường ảo (Nếu dùng uv)
uv venv
.venv\Scripts\activate

# Cài đặt toàn bộ thư viện cần thiết
uv pip install -r requirements.txt
# Hoặc nếu dùng file lock: uv sync
```

## 3. Khởi động các Dịch vụ (Mở 3 Terminal khác nhau)

Hệ thống yêu cầu bạn chạy đồng thời 3 cửa sổ Terminal (hoặc dùng tmux/Windows Terminal với các tab khác nhau). Đảm bảo tất cả đều đang ở thư mục gốc `MEP-Agents/` và đã kích hoạt `.venv\Scripts\activate`.

### ⚡ Terminal 1: Chạy Redis Server
Celery cần Redis làm Message Broker để quản lý hàng đợi. Nếu bạn đã cài Redis qua msi/exe:
```powershell
redis-server
```
*(Nếu Redis chạy ngầm thành service trên Windows thì bỏ qua bước này)*

### 🚀 Terminal 2: Chạy Worker AI (Celery)
Luồng này chịu trách nhiệm bóc khối lượng, đọc file CAD cực nặng mà không làm đơ Web. Do chạy trên Windows, ta phải thêm cờ `--pool=solo` (Windows không hỗ trợ fork mặc định của Celery).

```powershell
uv run celery -A src.celery_app worker -l info --pool=solo
```

### 🌐 Terminal 3: Chạy Web Backend (FastAPI)
Đây là cổng giao tiếp API (Port 8083).

```powershell
uv run uvicorn src.api:app --host 0.0.0.0 --port 8083 --reload
```

### 💻 Terminal 4: Chạy Web Frontend (React/Vite)
Giao diện người dùng. Sếp nhớ phải cd vào thư mục `web/` chứa mã nguồn frontend.

```powershell
cd web
npm install
npm run dev
```

---

## 4. Kiểm tra hệ thống (Sanity Check)
Sau khi tất cả 4 Terminal đã chạy không báo lỗi:
1. Mở trình duyệt vào trang: `http://localhost:5173` (Giao diện Web).
2. Vào tab Upload, kéo thả 1 file CAD bất kỳ.
3. Nhìn sang **Terminal 2 (Celery)**: Bạn sẽ thấy log `Task src.celery_app.parse_cad_to_db_task... received` báo hiệu luồng bóc khối lượng AI đang xử lý ngầm.
4. Mở AutoCAD, chạy lệnh LISP `AUTOBOQ`. AutoCAD sẽ gọi sang FastAPI (Terminal 3) và bạn sẽ thấy khối lượng được xuất thẳng ra file Excel trong thư mục `data/boq/`.
