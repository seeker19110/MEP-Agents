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
        # Lần chạy đầu tiên chưa có thư mục là chuyện bình thường: tạo sẵn và báo cho
        # người dùng bỏ tài liệu vào, thay vì ném lỗi giữa chừng.
        root.mkdir(parents=True, exist_ok=True)
        print(f"Đã tạo thư mục {root} — hãy chép tài liệu tiêu chuẩn (.txt) vào rồi chạy lại.")
        return []
    loader = DirectoryLoader(str(root), glob="**/*.txt", loader_cls=TextLoader, loader_kwargs={"encoding": "utf-8"})
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    return splitter.split_documents(docs)


def main():
    docs = load_standard_docs()
    if not docs:
        print("Không có tài liệu nào trong data/standards — bỏ qua bước nạp vector.")
        return
    print(f"Loaded {len(docs)} chunks from data/standards")
    # Không còn chặn cứng ở OPENAI_API_KEY: từ Phase D dự án hỗ trợ embedding qua Ollama
    # hoặc sentence-transformers chạy cục bộ, nhưng chỗ này vẫn thoát sớm nên chạy offline
    # là không nạp được index — hybrid mất hẳn nhánh vector mà không ai biết vì sao.
    from src.local_embeddings import embedding_backend_name

    backend_name = embedding_backend_name()
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    has_key = bool(api_key) and api_key != "dummy_key_to_prevent_crash_on_import"
    if backend_name == "openai" and not has_key:
        print("LỖI: Chưa cấu hình OPENAI_API_KEY trong .env.")
        print("     Hoặc đặt EMBEDDING_BACKEND=ollama|local để nạp mà không cần API key.")
        return
    print(f"Nguồn embedding: {backend_name}")
    from src.vectorstore import build_or_load_vectorstore, use_pgvector, ensure_pgvector_hnsw_index
    build_or_load_vectorstore(docs)
    backend = "pgvector" if use_pgvector() else "FAISS"
    print(f"Nạp thành công! Backend vector: {backend}")
    if use_pgvector():
        print("HNSW:", ensure_pgvector_hnsw_index())


if __name__ == "__main__":
    main()
