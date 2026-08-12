"""Ingest standards into FAISS or pgvector (Phase C)."""
from __future__ import annotations

import os
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import settings


def load_standard_docs():
    root = Path("data/standards")
    if not root.is_dir():
        raise FileNotFoundError(f"Không thấy thư mục {root}")
    loader = DirectoryLoader(str(root), glob="**/*.txt", loader_cls=TextLoader, loader_kwargs={"encoding": "utf-8"})
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    return splitter.split_documents(docs)


def main():
    docs = load_standard_docs()
    print(f"Loaded {len(docs)} chunks from data/standards")
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "dummy_key_to_prevent_crash_on_import":
        print("LỖI: Chưa cấu hình OPENAI_API_KEY trong .env.")
        return
    from src.vectorstore import build_or_load_vectorstore, use_pgvector
    build_or_load_vectorstore(docs)
    backend = "pgvector" if use_pgvector() else "FAISS"
    print(f"Nạp thành công! Backend vector: {backend}")


if __name__ == "__main__":
    main()
