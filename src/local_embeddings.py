"""Local / offline embedding backends (Phase D)."""
from __future__ import annotations

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)


def _has_openai_key() -> bool:
    try:
        from src.config import settings
        key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    except Exception:
        key = os.getenv("OPENAI_API_KEY", "")
    return bool(key) and key != "dummy_key_to_prevent_crash_on_import"


def embedding_backend_name() -> str:
    prefer = (os.environ.get("EMBEDDING_BACKEND", "") or "").strip().lower()
    if prefer in ("openai", "ollama", "local", "sentence-transformers"):
        return prefer
    if _has_openai_key():
        return "openai"
    if os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST"):
        return "ollama"
    return "local"


@lru_cache(maxsize=1)
def get_embeddings_auto():
    backend = embedding_backend_name()
    logger.info("Embedding backend: %s", backend)
    if backend == "openai" and _has_openai_key():
        from langchain_openai import OpenAIEmbeddings
        from src.config import settings
        key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        return OpenAIEmbeddings(api_key=key, timeout=30, max_retries=2)
    if backend in ("ollama", "local"):
        try:
            return _ollama_embeddings()
        except Exception as e:
            logger.warning("Ollama embeddings unavailable (%s)", e)
            if backend == "ollama":
                raise
        try:
            return _sentence_transformer_embeddings()
        except Exception as e:
            raise RuntimeError(
                "Không có backend embedding. Đặt OPENAI_API_KEY, hoặc Ollama, hoặc sentence-transformers."
            ) from e
    if backend in ("sentence-transformers", "local"):
        return _sentence_transformer_embeddings()
    if _has_openai_key():
        from langchain_openai import OpenAIEmbeddings
        from src.config import settings
        return OpenAIEmbeddings(api_key=settings.openai_api_key or os.getenv("OPENAI_API_KEY"))
    return _ollama_embeddings()


def _ollama_embeddings():
    from langchain_community.embeddings import OllamaEmbeddings
    base = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
    model = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    return OllamaEmbeddings(base_url=base, model=model)


def _sentence_transformer_embeddings():
    from langchain_community.embeddings import HuggingFaceEmbeddings
    model = os.environ.get("LOCAL_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    return HuggingFaceEmbeddings(model_name=model)
