"""Vector store for standards RAG (Phase C) — FAISS (default) or pgvector."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _settings():
    from src.config import settings
    return settings


def use_pgvector() -> bool:
    s = _settings()
    flag = getattr(s, "use_pgvector", False) or os.environ.get("USE_PGVECTOR", "").lower() in ("1", "true", "yes")
    url = (getattr(s, "database_url", None) or os.environ.get("DATABASE_URL", "") or "").strip()
    return bool(flag and url)


def get_embeddings():
    from langchain_openai import OpenAIEmbeddings
    s = _settings()
    api_key = s.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "dummy_key_to_prevent_crash_on_import":
        raise RuntimeError("Cần OPENAI_API_KEY để tạo embeddings.")
    return OpenAIEmbeddings(api_key=api_key)


def build_or_load_vectorstore(documents: list | None = None, *, collection: str = "mep_standards"):
    if use_pgvector():
        return _pgvector(documents, collection=collection)
    return _faiss(documents)


def _faiss(documents: list | None):
    from langchain_community.vectorstores import FAISS
    index_path = os.environ.get("FAISS_INDEX_PATH", "faiss_index")
    embeddings = get_embeddings()
    if documents:
        vs = FAISS.from_documents(documents, embeddings)
        vs.save_local(index_path)
        logger.info("FAISS index saved → %s", index_path)
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


def similarity_search(query: str, k: int = 4) -> list[Any]:
    vs = build_or_load_vectorstore(None)
    return vs.similarity_search(query, k=k)
