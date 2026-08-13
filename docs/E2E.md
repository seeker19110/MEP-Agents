# Kiểm thử End-to-End

Toàn bộ test còn lại của dự án là unit/integration ở mức module: mock Celery/Redis, không
bao giờ ghi ra file Excel thật. Lớp lỗi mà chúng không bắt được **đã xảy ra thật** — nội
dung XREF bị loại khỏi khối lượng trong im lặng (PR #32), chỉ lộ ra khi chạy trọn đường từ
bản vẽ tới con số.

Có hai tầng, phân biệt rõ cái gì thật cái gì giả.

## Tầng 1 — chạy trong CI, không cần hạ tầng

```bash
uv run pytest tests/test_e2e_takeoff.py -q
```

| Thành phần | Thật hay giả |
|---|---|
| File `.dxf` đầu vào | THẬT — dựng bằng ezdxf, có hình học và XREF thật |
| Bóc khối lượng | THẬT — hình học, không mock |
| File Excel đầu ra | THẬT — ghi ra đĩa rồi đọc lại |
| Endpoint FastAPI | THẬT — qua `TestClient` |
| Broker Celery + Redis | **GIẢ** — chạy đồng bộ trong tiến trình |

Bao được "bản vẽ → khối lượng → Excel → tải về". **Không** bao được "worker rời thật sự
nhặt task qua Redis" — đó là việc của tầng 2.

Kiểm chứng sức bắt lỗi: tạm làm hỏng luồng gộp XREF trong `src/cad_loader.py` thì 3/4 test
của tầng này chuyển đỏ.

## Tầng 2 — hạ tầng thật, không giả lập gì

```bash
uv run python scripts/e2e_smoke.py
```

Gửi file lên API thật qua mạng, chờ worker rời nhặt task qua Redis, tải Excel về và kiểm
nội dung. Mã thoát 0 = đạt, 1 = hỏng (in rõ bước nào).

### Cách A — Docker Compose (giống môi trường triển khai nhất)

```bash
cp .env.example .env          # điền API key LLM nếu cần
docker compose up --build -d
uv run python scripts/e2e_smoke.py
```

### Cách B — dựng tay, không cần Docker

Đây là cách đã dùng để kiểm chứng kịch bản này lần đầu:

```bash
redis-server --port 6379 --daemonize yes

C_FORCE_ROOT=1 uv run celery -A src.celery_app worker -l info --concurrency 2 &
uv run uvicorn src.api:app --host 127.0.0.1 --port 8083 &

E2E_BASE_URL=http://127.0.0.1:8083 uv run python scripts/e2e_smoke.py
```

`C_FORCE_ROOT` chỉ cần khi chạy bằng root (VD trong container dev). Nhớ tắt các tiến trình
nền sau khi xong.

### Biến môi trường

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `E2E_BASE_URL` | `http://localhost:8083` | Địa chỉ API |
| `MEP_AGENTS_API_KEY` | (trống) | Có đặt thì kịch bản gửi kèm khóa |
| `E2E_TIMEOUT` | `180` | Số giây chờ worker tối đa |

### Kiểm luôn đường xác thực

```bash
MEP_AGENTS_API_KEY=doi-gia-tri-nay uv run uvicorn src.api:app --port 8083 &

# Thiếu khóa phải bị chặn (401)
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8083/api/v1/takeoff -F "file=@bat_ky.dxf"

# Có khóa thì chạy trọn đường
MEP_AGENTS_API_KEY=doi-gia-tri-nay uv run python scripts/e2e_smoke.py
```

## Kết quả đã kiểm chứng

Chạy lần đầu bằng **cách B** (Redis thật, worker Celery chạy tiến trình riêng, FastAPI
thật) — **đạt**: tải lên → worker nhặt task qua Redis → Excel 5.582 byte → tải về, tổng
chiều dài khớp đúng hình học đã dựng. Bật `MEP_AGENTS_API_KEY` cũng đạt, và thiếu khóa thì
bị chặn 401 đúng như thiết kế.

**Chưa kiểm chứng:** chạy qua `docker compose up --build` (cách A) — môi trường viết code
không có Docker daemon. Rất có thể còn lỗi riêng của lớp container (quyền thư mục volume,
biến môi trường thiếu, healthcheck sai) mà cách B không lộ ra. Xem `TECH_DEBT.md` mục 3.

## Đọc kết quả khi hỏng

| Triệu chứng | Nơi cần nhìn |
|---|---|
| `không kết nối được ...` | API chưa chạy, hoặc sai `E2E_BASE_URL` |
| HTTP 401 khi tải lên | Thiếu `MEP_AGENTS_API_KEY`, hoặc sai giá trị |
| Quá thời gian, trạng thái kẹt ở `Processing` | Worker không nhặt được task — xem log worker và `CELERY_BROKER_URL`. Trong container, "localhost" là chính container đó |
| Tải về không phải Excel | Worker chạy xong nhưng không sinh file — xem log worker, kiểm quyền ghi thư mục `data/boq` |
| Excel có nhưng thiếu số | Lỗi ở khâu bóc khối lượng, không phải hạ tầng — chạy tầng 1 để khoanh vùng |
