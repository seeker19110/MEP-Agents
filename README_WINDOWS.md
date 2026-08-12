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

## 5. Cấu hình Plugin AutoCAD / Revit (không còn hardcode)

Cả hai plugin trước đây trỏ cứng tới `localhost:8083` (AutoCAD) và tới đường dẫn cá nhân
`C:\Users\liend\MEP-Agents` (AutoCAD LISP), nên chỉ chạy đúng trên đúng 1 máy. Nay cấu hình
qua biến môi trường (System Properties → Environment Variables), không cần sửa code:

- **`MEP_AGENTS_HOME`** — đường dẫn thư mục gốc dự án, ví dụ
  `C:\Users\<ten-ban>\MEP-Agents`. Dùng bởi `autocad/AUTOBOQ.lsp` để tìm `autoboq.py`.
- **`MEP_AGENTS_API_BASE`** — địa chỉ server FastAPI, mặc định `http://localhost:8083`
  nếu không đặt. Dùng bởi cả `autocad/autoboq.py` và plugin Revit. Đặt biến này nếu server
  chạy trên máy khác/cloud (ví dụ `http://192.168.1.10:8083`).

Với plugin Revit, thay vì biến môi trường có thể sửa trực tiếp
`revit/MEPAgents.extension/MEPAgents.tab/AI Tools.panel/Auto BOQ.pushbutton/config.sample.json`
(đổi tên thành `config.json` trong cùng thư mục) để đặt `api_base` riêng cho máy đó.

## 6. Bảo mật API tối thiểu (tùy chọn — xem `TECH_DEBT.md` mục 7)

Mặc định server KHÔNG yêu cầu xác thực (phù hợp máy dev cục bộ). Nếu server chạy trên máy
khác trong mạng LAN hoặc public ra Internet, nên bật API key tối thiểu:

- **`MEP_AGENTS_API_KEY`** (đặt ở Terminal 3, nơi chạy `uvicorn`) — khi đặt, mọi request
  tới API phải kèm header `X-API-Key` khớp giá trị này (hoặc `?api_key=` trên query string
  cho link tải file/WebSocket). Đặt CÙNG giá trị này ở:
  - Plugin Revit: biến môi trường `MEP_AGENTS_API_KEY`, hoặc thêm `"api_key": "..."` vào `config.json`.
  - Plugin AutoCAD: biến môi trường `MEP_AGENTS_API_KEY`.
  - Web App: `web/.env` → `VITE_API_KEY=...` (đổi giá trị rồi phải `npm run build` lại nếu build production).
- **`CORS_ALLOWED_ORIGINS`** (đặt ở Terminal 3) — danh sách domain Web App được phép gọi
  API, phân tách bằng dấu phẩy. Không đặt thì mặc định chỉ cho phép
  `http://localhost:5173` (dev cục bộ). Đặt domain thật khi deploy, KHÔNG dùng `*`.

Lưu ý: đây chỉ là 1 khóa CHUNG chặn truy cập nặc danh, không phải xác thực người dùng thật
(JWT/OAuth đa người dùng) — xem `TECH_DEBT.md` mục 6.

## 7. Chạy bằng Docker Compose (thay thế bước 3, chưa kiểm chứng chạy thật)

Thay vì mở 4 Terminal riêng, có thể dùng `docker-compose.yml` ở gốc dự án để chạy cả 5
service (Redis, FastAPI, Celery worker, Streamlit, Web App) trong container:

```powershell
copy .env.example .env
copy web\.env.example web\.env
docker compose up --build
```

**CẢNH BÁO TRUNG THỰC:** file `docker-compose.yml` mới được viết và kiểm tra cú pháp bằng
`docker compose config`, CHƯA từng chạy thật `docker compose up` (môi trường viết code
không có Docker daemon). Có khả năng phát sinh lỗi khi chạy thật lần đầu (permission
volume, thiếu biến môi trường...) — nếu gặp lỗi, ưu tiên báo lại để cập nhật thay vì tự
suy luận sửa sai hướng.
