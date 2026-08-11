FROM python:3.11-slim

# Cần cho ezdxf/matplotlib (render CAD -> ảnh) và các font TrueType chuẩn (Arial/Times)
# để chữ tiếng Việt trên bản vẽ CAD hiển thị đúng khi render qua matplotlib.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    fontconfig \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Cài dependency trước để tận dụng layer cache khi chỉ code thay đổi
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

RUN mkdir -p outputs

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD uv run python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
