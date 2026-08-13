"""Nạp dữ liệu Tiêu chuẩn (RAG ingestion) vào FAISS (src/ingest.py).

Không gọi API embedding thật (tốn phí/cần mạng) — chỉ kiểm tra các nhánh xử lý sớm:
tạo thư mục dữ liệu, không có tài liệu, và thiếu API key.
"""
import os

import pytest

from src import ingest


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def test_creates_data_dir_when_missing(capsys):
    assert not os.path.exists("data/standards")
    ingest.main()
    assert os.path.isdir("data/standards")
    out = capsys.readouterr().out
    assert "Đã tạo thư mục" in out


def test_returns_early_when_no_documents_found(capsys):
    os.makedirs("data/standards")
    ingest.main()
    out = capsys.readouterr().out
    assert "Không có tài liệu nào" in out


def test_stops_with_message_when_openai_backend_has_no_key(monkeypatch, capsys):
    """Chỉ dừng khi nguồn embedding ĐANG LÀ openai mà thiếu key. Các nguồn khác
    (ollama/local) không cần key nên không được chặn ở đây."""
    os.makedirs("data/standards")
    with open("data/standards/note.txt", "w", encoding="utf-8") as f:
        f.write("Tiêu chuẩn thiết kế điện: TCVN 7447.")

    monkeypatch.setenv("EMBEDDING_BACKEND", "openai")
    monkeypatch.setattr(ingest.settings, "openai_api_key", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    ingest.main()
    out = capsys.readouterr().out
    assert "Chưa cấu hình OPENAI_API_KEY" in out
    assert not os.path.exists("faiss_index")


def test_local_backend_ingests_without_openai_key(monkeypatch, capsys):
    """Hồi quy: `ingest` từng chặn cứng ở OPENAI_API_KEY, nên chạy hoàn toàn offline là
    không nạp được index — hybrid mất hẳn nhánh vector mà không có dấu hiệu gì."""
    os.makedirs("data/standards")
    with open("data/standards/note.txt", "w", encoding="utf-8") as f:
        f.write("Tiêu chuẩn thiết kế điện: TCVN 7447.")

    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    monkeypatch.setattr(ingest.settings, "openai_api_key", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    built = {}

    def fake_build(docs):
        built["n"] = len(docs)
        return object()

    import src.vectorstore as vs
    monkeypatch.setattr(vs, "build_or_load_vectorstore", fake_build)
    monkeypatch.setattr(vs, "use_pgvector", lambda: False)

    ingest.main()

    out = capsys.readouterr().out
    assert "Chưa cấu hình OPENAI_API_KEY" not in out
    assert "Nguồn embedding: local" in out
    assert built.get("n", 0) > 0, "không nạp tài liệu nào vào vectorstore"
