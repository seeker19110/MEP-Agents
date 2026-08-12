"""Phase C: JWT, local storage, YOLO weights resolve, config fields."""
from __future__ import annotations

from pathlib import Path


def test_config_phase_c_fields():
    from src.config import settings
    assert hasattr(settings, "database_url")
    assert hasattr(settings, "use_pgvector")
    assert hasattr(settings, "s3_bucket")
    assert hasattr(settings, "jwt_secret")
    assert hasattr(settings, "yolo_weights")


def test_local_storage_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    from src import storage as storage_mod
    storage_mod.reset_storage_for_tests()
    store = storage_mod.LocalStorage(root=str(tmp_path / "up"))
    src = tmp_path / "a.txt"
    src.write_text("hello-mep", encoding="utf-8")
    key = store.put_file(str(src), "uploads/a.txt")
    assert store.exists(key)
    dest = store.fetch_to_local(key, str(tmp_path / "out.txt"))
    assert Path(dest).read_text(encoding="utf-8") == "hello-mep"
    store.delete(key)
    assert not store.exists(key)


def test_jwt_create_and_decode(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-phase-c-please-change")
    from src import auth_jwt
    token = auth_jwt.create_access_token("admin", extra={"role": "admin"})
    assert isinstance(token, str) and token.count(".") == 2
    claims = auth_jwt.decode_access_token(token)
    assert claims["sub"] == "admin"
    assert claims.get("role") == "admin"


def test_jwt_bootstrap_user(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x")
    monkeypatch.setenv("JWT_BOOTSTRAP_USER", "boss")
    monkeypatch.setenv("JWT_BOOTSTRAP_PASSWORD", "s3cret")
    from src import auth_jwt
    assert auth_jwt.verify_bootstrap_user("boss", "s3cret") is True
    assert auth_jwt.verify_bootstrap_user("boss", "wrong") is False


def test_yolo_weights_default(monkeypatch):
    monkeypatch.delenv("YOLO_WEIGHTS", raising=False)
    from src.yolo_mepf import resolve_weights_path
    assert resolve_weights_path("") == "yolo11n.pt"


def test_yolo_scaffold(tmp_path):
    from src.yolo_mepf import write_default_data_yaml, DEFAULT_MEPF_CLASSES
    yaml_path = write_default_data_yaml(str(tmp_path / "yolo_mepf"))
    text = Path(yaml_path).read_text(encoding="utf-8")
    assert "names:" in text
    assert DEFAULT_MEPF_CLASSES[0] in text
    assert (tmp_path / "yolo_mepf" / "images" / "train").is_dir()


def test_vectorstore_use_pgvector_flag(monkeypatch):
    monkeypatch.delenv("USE_PGVECTOR", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from src.vectorstore import use_pgvector
    assert use_pgvector() is False
