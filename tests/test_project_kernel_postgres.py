"""Project Kernel trên backend Postgres thật — quyết định thiết kế #1 trong docstring của
`src/project_kernel.py` ("SQLite mặc định, Postgres khi có DATABASE_URL thật").

Khác với lúc viết đặc tả (`docs/DAC_TA_PROJECT_KERNEL.md`), khi đó "chưa có instance
Postgres thật để chạy thử" là lý do hoãn nhánh Postgres (`TECH_DEBT.md` mục 1) — file này
CHẠY THẬT trên một instance Postgres 16 nếu biến môi trường `TEST_DATABASE_URL` trỏ tới
một instance có quyền `CREATE SCHEMA`. Không có biến đó thì toàn bộ test ở đây tự bỏ qua
(skip), không fail — đúng cách các test phụ thuộc hạ tầng khác trong dự án xử lý (VD test
OCR bỏ qua khi thiếu `tesseract-ocr`).

Không lặp lại toàn bộ 47 test của `test_project_kernel.py` (những test đó không quan tâm
backend nào chạy bên dưới, vì chỉ gọi API công khai). File này chỉ nhắm đúng phần khác biệt
giữa hai backend: cú pháp `ON CONFLICT` thay `INSERT OR IGNORE`, kiểu lỗi va chạm khóa khác
nhau (`psycopg.errors.UniqueViolation` so với `sqlite3.IntegrityError`), và `dict_row` thay
`sqlite3.Row`.

Chạy thử: `TEST_DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/db uv run pytest
tests/test_project_kernel_postgres.py -q` (cần `uv sync --extra phase-c` để có `psycopg`).
"""
import os
import uuid

import pytest

from src import project_kernel as pk

psycopg = pytest.importorskip("psycopg", reason="Cần `uv sync --extra phase-c` để cài psycopg.")

_BASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not _BASE_URL,
    reason="TEST_DATABASE_URL không cấu hình — bỏ qua test backend Postgres (cần instance thật).",
)


@pytest.fixture(autouse=True)
def postgres_schema(monkeypatch):
    """Mỗi test một schema Postgres riêng (tạo/xóa quanh test) — cùng tinh thần cô lập với
    `tmp_path` cho SQLite, nhưng ở mức schema vì Postgres không có khái niệm "một file"."""
    schema = f"pk_test_{uuid.uuid4().hex[:12]}"
    admin = psycopg.connect(_BASE_URL, autocommit=True)
    admin.execute(f"CREATE SCHEMA {schema}")
    admin.close()

    sep = "&" if "?" in _BASE_URL else "?"
    monkeypatch.delenv("PROJECT_KERNEL_DB_PATH", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"{_BASE_URL}{sep}options=-csearch_path%3D{schema}")
    pk.reset_property_schemas_for_tests()
    pk.init_db()
    yield
    pk.reset_property_schemas_for_tests()

    admin = psycopg.connect(_BASE_URL, autocommit=True)
    admin.execute(f"DROP SCHEMA {schema} CASCADE")
    admin.close()


@pytest.fixture
def project():
    return pk.create_project("Tòa nhà văn phòng ABC (Postgres)", owner="ky.su.a")


@pytest.fixture
def revision(project):
    return pk.create_revision(project["project_id"], created_by="ky.su.a")


def test_backend_that_su_dung_postgres(project):
    """Xác nhận test này thật sự chạy qua nhánh Postgres, không lặng lẽ rơi về SQLite."""
    with pk._LOCK, pk._connect() as conn:
        assert pk._is_postgres_conn(conn)


def test_tao_du_an_va_thanh_vien_admin_dau_tien(project):
    fetched = pk.get_project(project["project_id"])
    assert fetched["name"] == "Tòa nhà văn phòng ABC (Postgres)"
    members = pk.list_project_members(project["project_id"])
    assert len(members) == 1 and members[0]["role"] == "admin"


def test_revision_active_va_superseded(project):
    rev1 = pk.create_revision(project["project_id"], created_by="a")
    rev2 = pk.create_revision(project["project_id"], created_by="a")
    pk.activate_revision(rev1["revision_id"])
    pk.activate_revision(rev2["revision_id"])
    assert pk.get_active_revision(project["project_id"])["revision_id"] == rev2["revision_id"]
    assert pk.get_revision(rev1["revision_id"])["status"] == "superseded"


def test_dang_ky_object_va_doc_lai_dung_kieu_du_lieu(project, revision):
    """`properties`/`metadata` phải là `dict` Python thật sau khi đọc lại — không phải
    chuỗi JSON thô hay kiểu `Json`/`dict_row` đặc thù của psycopg lộ ra ngoài."""
    obj = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                              discipline="mechanical", tag="AHU-003",
                              properties={"cong_suat_lanh_kw": 15.5}, confidence=0.9)
    fetched = pk.get_object(obj["object_id"])
    assert isinstance(fetched["properties"], dict)
    assert fetched["properties"]["cong_suat_lanh_kw"] == 15.5
    assert isinstance(fetched["confidence"], float)


def test_khong_ghi_de_source_da_co_loi_la_valueerror_khong_phai_loi_psycopg_tho(project, monkeypatch):
    """`register_source` phải bọc `psycopg.errors.UniqueViolation` thành `ValueError` —
    không để lỗi đặc thù driver rò ra ngoài module."""
    monkeypatch.setattr(pk, "_new_id", lambda prefix: "source:fixed-id-pg-test")
    pk.register_source(project["project_id"], kind="dxf", storage_key="a.dxf", uploaded_by="a")
    with pytest.raises(ValueError):
        pk.register_source(project["project_id"], kind="dxf", storage_key="b.dxf", uploaded_by="a")
    assert pk.get_source("source:fixed-id-pg-test")["storage_key"] == "a.dxf"


def test_link_objects_trung_khong_loi_khong_tao_hang_thua(project, revision):
    obj1 = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                               discipline="mechanical")
    obj2 = pk.register_object(project["project_id"], revision["revision_id"], type="zone",
                               discipline="mechanical")
    pk.link_objects(obj1["object_id"], obj2["object_id"], "serves",
                     project["project_id"], revision["revision_id"])
    pk.link_objects(obj1["object_id"], obj2["object_id"], "serves",
                     project["project_id"], revision["revision_id"])
    assert len(pk.get_relations(obj1["object_id"], relation_type="serves")) == 1


def test_them_lai_thanh_vien_upsert_qua_on_conflict(project):
    pk.add_project_member(project["project_id"], "ky.su.b", role="viewer")
    pk.add_project_member(project["project_id"], "ky.su.b", role="admin")
    members = [m for m in pk.list_project_members(project["project_id"]) if m["username"] == "ky.su.b"]
    assert len(members) == 1 and members[0]["role"] == "admin"


def test_vong_doi_va_property_schema(project, revision):
    pk.register_property_schema("ahu", ["cong_suat_lanh_kw"])
    with pytest.raises(ValueError):
        pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                            discipline="mechanical", properties={})

    obj = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                              discipline="mechanical", properties={"cong_suat_lanh_kw": 10},
                              confidence=0.95)
    pk.update_object_status(obj["object_id"], "normalized")
    pk.update_object_status(obj["object_id"], "validated")
    assert pk.try_auto_activate(obj["object_id"]) is True
    assert pk.get_object(obj["object_id"])["status"] == "active"

    with pytest.raises(ValueError):
        pk.update_object_status(obj["object_id"], "discovered")
