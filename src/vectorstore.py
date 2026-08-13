"""Vector store for standards RAG — FAISS (default) or pgvector, with query-path optimisations.

1. Singleton cache — load FAISS / PG once per process
2. Query embedding LRU — repeated agent queries skip OpenAI round-trip
3. pgvector HNSW — ANN index after ingest
4. search_standards_docs() — used by vector_search_bind
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_STORE_LOCK = threading.Lock()
_CACHED_STORE: Any = None
_CACHED_KEY: str | None = None


def _settings():
    from src.config import settings
    return settings


def use_pgvector() -> bool:
    s = _settings()
    flag = getattr(s, "use_pgvector", False) or os.environ.get("USE_PGVECTOR", "").lower() in (
        "1", "true", "yes",
    )
    url = (getattr(s, "database_url", None) or os.environ.get("DATABASE_URL", "") or "").strip()
    return bool(flag and url)


def get_embeddings():
    """Nguồn embedding: OpenAI, Ollama, hoặc sentence-transformers cục bộ.

    Việc chọn nguồn nằm ở `src/local_embeddings.py` và trước đây chỉ được gắn vào bằng
    patch lúc import Phase D. Hệ quả: ai import thẳng `src.vectorstore` mà không qua
    `src.graph` — đúng trường hợp của `python -m src.ingest` — vẫn kẹt ở đường OpenAI và
    không nạp được index nếu thiếu API key. Nay gọi trực tiếp, không phụ thuộc patch.
    """
    try:
        from src.local_embeddings import get_embeddings_auto
        return get_embeddings_auto()
    except ImportError:  # pragma: no cover - chỉ khi thiếu module Phase D
        logger.debug("local_embeddings không sẵn có — dùng đường OpenAI")

    from langchain_openai import OpenAIEmbeddings
    s = _settings()
    api_key = s.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "dummy_key_to_prevent_crash_on_import":
        raise RuntimeError("Cần OPENAI_API_KEY để tạo embeddings.")
    return OpenAIEmbeddings(api_key=api_key, timeout=30, max_retries=2)


@lru_cache(maxsize=256)
def _cached_embed_query(query: str, model_hint: str) -> tuple[float, ...]:
    emb = get_embeddings()
    vec = emb.embed_query(query)
    return tuple(float(x) for x in vec)


def embed_query_cached(query: str) -> list[float]:
    q = (query or "").strip()
    model_hint = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    return list(_cached_embed_query(q, model_hint))


def _store_cache_key() -> str:
    if use_pgvector():
        s = _settings()
        url = (s.database_url or os.environ.get("DATABASE_URL", "")).strip()
        return f"pg:{hashlib.sha1(url.encode()).hexdigest()[:12]}"
    index_path = os.environ.get("FAISS_INDEX_PATH", "faiss_index")
    return f"faiss:{os.path.abspath(index_path)}"


def invalidate_store_cache() -> None:
    global _CACHED_STORE, _CACHED_KEY
    with _STORE_LOCK:
        _CACHED_STORE = None
        _CACHED_KEY = None
    _cached_embed_query.cache_clear()
    logger.info("Vector store + embedding query cache cleared")


def get_vectorstore(*, collection: str = "mep_standards"):
    global _CACHED_STORE, _CACHED_KEY
    key = _store_cache_key()
    with _STORE_LOCK:
        if _CACHED_STORE is not None and _CACHED_KEY == key:
            return _CACHED_STORE
        store = build_or_load_vectorstore(None, collection=collection)
        _CACHED_STORE = store
        _CACHED_KEY = key
        return store


def build_or_load_vectorstore(documents: list | None = None, *, collection: str = "mep_standards"):
    if use_pgvector():
        vs = _pgvector(documents, collection=collection)
        if documents:
            ensure_pgvector_hnsw_index(collection=collection)
            invalidate_store_cache()
        return vs
    vs = _faiss(documents)
    if documents:
        invalidate_store_cache()
    return vs


def _faiss(documents: list | None):
    from langchain_community.vectorstores import FAISS
    index_path = os.environ.get("FAISS_INDEX_PATH", "faiss_index")
    embeddings = get_embeddings()
    if documents:
        vs = FAISS.from_documents(documents, embeddings)
        try:
            vs.normalize_L2 = True  # type: ignore[attr-defined]
        except Exception:
            pass
        vs.save_local(index_path)
        logger.info("FAISS index saved → %s (%s chunks)", index_path, len(documents))
        return vs
    if os.path.isdir(index_path):
        return FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
    raise FileNotFoundError(f"Không có FAISS index tại {index_path}; chạy ingest trước.")


def _pgvector(documents: list | None, *, collection: str):
    s = _settings()
    connection = (s.database_url or os.environ.get("DATABASE_URL", "")).strip()
    embeddings = get_embeddings()
    try:
        from langchain_postgres import PGVector  # type: ignore
        if documents:
            vs = PGVector.from_documents(
                documents=documents,
                embedding=embeddings,
                connection=connection,
                collection_name=collection,
                pre_delete_collection=True,
            )
        else:
            vs = PGVector(embeddings=embeddings, collection_name=collection, connection=connection)
        logger.info("pgvector collection=%s ready", collection)
        return vs
    except ImportError:
        logger.warning("langchain_postgres missing — try langchain_community PGVector")
    from langchain_community.vectorstores import PGVector as CommunityPGVector
    if documents:
        return CommunityPGVector.from_documents(
            documents=documents,
            embedding=embeddings,
            connection_string=connection,
            collection_name=collection,
            pre_delete_collection=True,
        )
    return CommunityPGVector(
        embedding_function=embeddings,
        collection_name=collection,
        connection_string=connection,
    )


def ensure_pgvector_hnsw_index(*, collection: str = "mep_standards", dims: int = 1536) -> str:
    if not use_pgvector():
        return "skipped: not using pgvector"
    s = _settings()
    url = (s.database_url or os.environ.get("DATABASE_URL", "")).strip()
    try:
        import psycopg
    except ImportError:
        return "skipped: psycopg not installed (uv sync --extra phase-c)"

    candidates = [f"data_{collection}", "langchain_pg_embedding", collection]
    statements = []
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND (
                  table_name = %s OR table_name = %s OR table_name LIKE %s
                )
                """,
                (f"data_{collection}", "langchain_pg_embedding", f"%{collection}%"),
            )
            tables = [r[0] for r in cur.fetchall()] or candidates
            for table in tables:
                idx = f"idx_{table}_embedding_hnsw"
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s
                      AND (column_name='embedding' OR column_name='vector')
                    """,
                    (table,),
                )
                cols = [r[0] for r in cur.fetchall()]
                if not cols:
                    continue
                col = cols[0]
                try:
                    cur.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS {idx}
                        ON {table}
                        USING hnsw ({col} vector_cosine_ops)
                        WITH (m = 16, ef_construction = 64)
                        """
                    )
                    statements.append(f"ok:{table}.{col}")
                    logger.info("HNSW index ensured on %s(%s)", table, col)
                except Exception as e:
                    statements.append(f"fail:{table}:{e}")
                    logger.warning("HNSW index on %s failed: %s", table, e)
    return "; ".join(statements) or "no embedding table found"


def similarity_search(query: str, k: int = 4) -> list[Any]:
    return search_standards_docs(query, k=k)


def search_standards_docs(query: str, k: int = 3) -> list[Any]:
    vs = get_vectorstore()
    q = (query or "").strip()
    if not q:
        return []
    try:
        vec = embed_query_cached(q)
        if hasattr(vs, "similarity_search_by_vector"):
            return vs.similarity_search_by_vector(vec, k=k)
    except Exception as e:
        logger.debug("embed cache path failed (%s) — fallback similarity_search", e)
    return vs.similarity_search(q, k=k)


def search_standards_with_scores(query: str, k: int = 3) -> list[tuple[Any, float]]:
    vs = get_vectorstore()
    q = (query or "").strip()
    try:
        vec = embed_query_cached(q)
        if hasattr(vs, "similarity_search_with_score_by_vector"):
            return vs.similarity_search_with_score_by_vector(vec, k=k)
    except Exception:
        pass
    if hasattr(vs, "similarity_search_with_score"):
        return vs.similarity_search_with_score(q, k=k)
    docs = vs.similarity_search(q, k=k)
    return [(d, 0.0) for d in docs]
