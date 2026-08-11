# X-Agents (Multi-Agent System)

Dự án này là một hệ thống Multi-Agent chuẩn Enterprise được tối ưu hóa dựa trên các nguyên tắc của [12-Factor Agents](https://github.com/humanlayer/12-factor-agents). Nó đóng vai trò là một **Template** cốt lõi cho mọi dự án team-work AI sau này.

Hệ thống được thiết kế bằng **LangGraph** (Python) với các đặc điểm:
- 🧠 **Supervisor Routing**: Có một nhạc trưởng điều phối các tác nhân con.
- 💾 **Persistence (MemorySaver)**: Ghi nhớ hội thoại theo `thread_id`.
- 🛡️ **Reviewer Guardrail & Retry Loop**: Tác nhân kiểm duyệt đánh giá kết quả. Nếu lỗi, nó sẽ tự động bắt Tác nhân con (Worker) làm lại.
- 📦 **Structured State**: Giao tiếp qua lại giữa các AI thông qua biến `context` (Dictionary) thay vì chỉ dùng text.
- ⚙️ **Configuration**: Quản lý cấu hình tập trung bằng `pydantic-settings` qua file `.env`.

## Cấu trúc thư mục

- `.env.example`: File mẫu cấu hình môi trường.
- `main.py`: File chạy test luồng đồ thị.
- `src/config.py`: Đọc cấu hình từ `.env`.
- `src/state.py`: Định nghĩa lược đồ dữ liệu chung cho đồ thị (`AgentState`).
- `src/agents.py`: Chứa logic mô phỏng của toàn bộ các tác nhân (Supervisor, RAG, Tool, Reviewer).
- `src/graph.py`: Cấu hình vòng lặp tự sửa lỗi và kết nối các node LangGraph.
- `agentic.md`: Lộ trình phát triển hệ thống Agentic Vibe Coding.

## Cài đặt và Chạy

Dự án sử dụng `uv` để quản lý môi trường.

```bash
# 1. Copy file cấu hình và điền API keys
cp .env.example .env

# 2. Chạy dự án
uv run main.py
```

## Giám sát bằng LangSmith (Observability)

Khi nhiều Agent phối hợp với nhau, việc debug sẽ rất khó khăn nếu không có công cụ giám sát. Hệ thống này đã tích hợp sẵn luồng cho **LangSmith**.

1. Đăng ký tài khoản tại [smith.langchain.com](https://smith.langchain.com/)
2. Tạo API Key và điền vào file `.env`:
```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__xxxxxx
LANGCHAIN_PROJECT=x_agents_project
```
Khi chạy dự án, toàn bộ "suy nghĩ", thời gian thực thi, và lỗi của từng tác nhân sẽ được vẽ biểu đồ trực quan trên web LangSmith.

## Deploy

Xem hướng dẫn deploy chi tiết (Docker, docker-compose kèm Ollama, systemd VPS, hoặc
Streamlit Community Cloud) tại [`docs/DEPLOY.md`](docs/DEPLOY.md).
