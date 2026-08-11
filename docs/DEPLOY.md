# Hướng dẫn Deploy MEP-Agents

Tài liệu này hướng dẫn deploy ứng dụng Streamlit (`app.py`) của dự án ra production, bằng
Docker (khuyến nghị) hoặc chạy nền trực tiếp trên VPS bằng `systemd`.

## 0. Chuẩn bị chung

- Đã clone repo và có file `.env` (copy từ `.env.example`, điền `LLM_PROVIDER`/`MODEL_NAME`
  và các `*_API_KEY` cần thiết). Xem `AI_MODEL_SETUP.md` để chọn model theo từng vai trò,
  hoặc mục 7 của tài liệu đó nếu muốn chạy **offline hoàn toàn** bằng Ollama.
- **Không commit `.env` lên Git** — chỉ truyền vào container/server qua biến môi trường
  hoặc secret manager của nền tảng deploy.

## 1. Deploy bằng Docker (khuyến nghị)

### 1.1. Build image

```bash
docker build -t mep-agents .
```

### 1.2. Chạy container

```bash
docker run -d \
  --name mep-agents \
  -p 8501:8501 \
  --env-file .env \
  -v mep-agents-outputs:/app/outputs \
  --restart unless-stopped \
  mep-agents
```

- `-v mep-agents-outputs:/app/outputs`: lưu trữ bền vững cho các file Excel/CAD được các
  Agent tạo ra theo từng session (`src/workspace.py`) — nếu bỏ qua, dữ liệu mất khi
  container bị xóa/tái tạo.
- Truy cập: `http://<ip-server>:8501`.

### 1.3. docker-compose (thay thế bước 1.2, dễ quản lý hơn)

Tạo `docker-compose.yml`:

```yaml
services:
  mep-agents:
    build: .
    ports:
      - "8501:8501"
    env_file:
      - .env
    volumes:
      - mep-agents-outputs:/app/outputs
    restart: unless-stopped

volumes:
  mep-agents-outputs:
```

```bash
docker compose up -d --build
```

### 1.4. Chạy kèm Ollama (offline hoàn toàn, LLM cục bộ)

Nếu chọn `LLM_PROVIDER=ollama` trong `.env`, chạy thêm service Ollama trong cùng
`docker-compose.yml` và trỏ base URL của `src/agents.py` (hiện đang hard-code
`http://localhost:11434/v1`) sang service đó:

```yaml
services:
  ollama:
    image: ollama/ollama
    volumes:
      - ollama-data:/root/.ollama
    ports:
      - "11434:11434"

  mep-agents:
    build: .
    ports:
      - "8501:8501"
    env_file:
      - .env
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434/v1  # xem lưu ý bên dưới
    volumes:
      - mep-agents-outputs:/app/outputs
    depends_on:
      - ollama
    restart: unless-stopped

volumes:
  mep-agents-outputs:
  ollama-data:
```

> **Lưu ý:** `src/agents.py` hiện đang hard-code `base_url="http://localhost:11434/v1"`
> cho provider `ollama` — khi chạy 2 container tách biệt, `localhost` bên trong container
> `mep-agents` KHÔNG trỏ tới container `ollama`. Có 2 cách xử lý: (a) chạy Ollama trực
> tiếp trên host và dùng `--network host` cho container `mep-agents` (chỉ Linux), hoặc
> (b) sửa `_build_llm` trong `src/agents.py` để đọc base URL từ biến môi trường
> (`OLLAMA_BASE_URL`) thay vì hard-code — khuyến nghị nếu bạn dùng Ollama dạng service
> riêng thường xuyên.

### 1.5. Reverse proxy + HTTPS (khi public ra internet)

Đặt Nginx hoặc Caddy phía trước container để có TLS. Ví dụ Caddy (`Caddyfile`):

```
mep-agents.example.com {
    reverse_proxy localhost:8501
}
```

Streamlit dùng WebSocket cho việc cập nhật UI real-time — đảm bảo reverse proxy forward
đúng header `Upgrade`/`Connection` (Caddy làm tự động; với Nginx cần cấu hình
`proxy_set_header Upgrade $http_upgrade;` và `proxy_set_header Connection "upgrade";`).

## 2. Deploy không dùng Docker (systemd trên VPS)

```bash
# Trên server
git clone https://github.com/seeker19110/MEP-Agents.git /opt/mep-agents
cd /opt/mep-agents
cp .env.example .env   # rồi điền cấu hình
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

Tạo service `/etc/systemd/system/mep-agents.service`:

```ini
[Unit]
Description=MEP-Agents Streamlit App
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/mep-agents
EnvironmentFile=/opt/mep-agents/.env
ExecStart=/root/.local/bin/uv run streamlit run app.py --server.port=8501 --server.address=0.0.0.0
Restart=always
RestartSec=5
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mep-agents
sudo systemctl status mep-agents
```

Xem log: `journalctl -u mep-agents -f`.

## 3. Deploy lên Streamlit Community Cloud (nhanh, miễn phí, phù hợp demo)

Nền tảng này build bằng `pip`/`requirements.txt`, không dùng `uv`/`pyproject.toml` trực
tiếp — cần sinh thêm file lock:

```bash
uv export --no-hashes --format requirements-txt > requirements.txt
git add requirements.txt && git commit -m "chore: thêm requirements.txt cho Streamlit Cloud"
```

Sau đó: vào [share.streamlit.io](https://share.streamlit.io) → **New app** → chọn repo,
branch, file chính `app.py` → mục **Secrets** dán nội dung `.env` theo cú pháp TOML
(`KEY = "value"`, mỗi dòng một biến) → Deploy.

> Streamlit Community Cloud không có ổ đĩa bền vững lâu dài giữa các lần redeploy — không
> phù hợp nếu cần lưu trữ lâu dài các file Excel/CAD được tạo ra; chỉ nên dùng cho demo.

## 4. Checklist trước khi deploy production

- [ ] `.env` không được commit vào Git, chỉ truyền qua secret/env của nền tảng deploy.
- [ ] Volume `outputs/` (hoặc thư mục workspace tương ứng) được mount bền vững nếu cần
  giữ lại các file Excel/CAD đã tạo qua các lần restart container.
- [ ] Đã chạy `uv run pytest -q` xanh trước khi build image production.
- [ ] Nếu public ra internet: có reverse proxy TLS + xác thực truy cập (Streamlit không
  có auth built-in) — cân nhắc Basic Auth ở tầng Nginx/Caddy hoặc Cloudflare Access.
- [ ] Nếu dùng `search_standards`/RAG với FAISS (`OPENAI_API_KEY` đã cấu hình), đã chạy
  `uv run python src/ingest.py` và mount/copy thư mục `faiss_index/` vào image hoặc volume
  — nếu không, hệ thống tự động rơi về tra cứu offline theo từ khóa (xem
  `AI_MODEL_SETUP.md` mục 7.3), vẫn hoạt động nhưng độ chính xác thấp hơn.
