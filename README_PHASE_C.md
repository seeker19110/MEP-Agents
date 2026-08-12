# Phase C — Infra (Postgres / pgvector / S3 / JWT / YOLO MEPF)

## Modules

| Module | Role |
|---|---|
| `src/auth_jwt.py` | JWT login `/api/v1/auth/login`, dual auth with API key |
| `src/storage.py` | Local or S3-compatible object storage |
| `src/vectorstore.py` | FAISS (default) or pgvector when `USE_PGVECTOR=true` |
| `src/checkpointer_factory.py` | LangGraph Postgres checkpointer when `DATABASE_URL` set |
| `src/yolo_mepf.py` | Fine-tune scaffold + weight resolve |
| `src/vision_tools.py` | Loads `YOLO_WEIGHTS` |

## Enable

```bash
uv sync --extra phase-c
# .env: DATABASE_URL, JWT_SECRET, JWT_BOOTSTRAP_PASSWORD, optional S3_*, YOLO_WEIGHTS
docker compose up -d postgres
uv run python -m src.ingest
uv run python -m src.yolo_mepf scaffold
uv run pytest tests/test_phase_c.py -q
```

## Auth

```bash
curl -s -X POST http://localhost:8083/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"change-me"}'
```
