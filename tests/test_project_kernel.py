"""Project Kernel — registry canonical cho project/revision/source/object.

Bước 1 ("schema + module trơn") của đặc tả `docs/DAC_TA_PROJECT_KERNEL.md`. Module đứng
độc lập (canh ở `test_no_import_cycles.py`), chưa có tool/route nào gọi vào — test ở đây
chỉ kiểm chứng bản thân registry, đúng phạm vi mục 12 của đặc tả.
"""
import sqlite3

import pytest

from src import project_kernel as pk


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    """Mỗi test một file CSDL riêng — không test nào thấy dữ liệu của test khác."""
    monkeypatch.setenv("PROJECT_KERNEL_DB_PATH", str(tmp_path / "project_kernel.sqlite"))
    pk.init_db()
    yield


@pytest.fixture
def project():
    return pk.create_project("Tòa nhà văn phòng ABC", owner="ky.su.a")


@pytest.fixture
def revision(project):
    return pk.create_revision(project["project_id"], created_by="ky.su.a", note="Bản đầu")


# --- Project / revision / source: đường vui ---

def test_tao_du_an_doc_lai_dung_nguyen_truong(project):
    fetched = pk.get_project(project["project_id"])
    assert fetched["name"] == "Tòa nhà văn phòng ABC"
    assert fetched["owner"] == "ky.su.a"
    assert fetched["status"] == "active"
    assert fetched["metadata"] == {}


def test_tao_du_an_rong_ten_hoac_owner_nem_loi():
    with pytest.raises(ValueError):
        pk.create_project("", owner="a")
    with pytest.raises(ValueError):
        pk.create_project("Dự án X", owner="")


def test_list_projects_chi_tra_dung_owner(project):
    pk.create_project("Dự án của người khác", owner="ky.su.b")
    mine = pk.list_projects("ky.su.a")
    assert len(mine) == 1
    assert mine[0]["project_id"] == project["project_id"]


def test_tao_revision_can_du_an_ton_tai():
    with pytest.raises(ValueError):
        pk.create_revision("project:khong-ton-tai", created_by="a")


def test_activate_revision_chi_mot_active_moi_luc(project):
    rev1 = pk.create_revision(project["project_id"], created_by="a")
    rev2 = pk.create_revision(project["project_id"], created_by="a")

    pk.activate_revision(rev1["revision_id"])
    assert pk.get_active_revision(project["project_id"])["revision_id"] == rev1["revision_id"]

    pk.activate_revision(rev2["revision_id"])
    assert pk.get_active_revision(project["project_id"])["revision_id"] == rev2["revision_id"]
    # rev1 phải bị hạ xuống superseded, không còn là active thứ hai.
    assert pk.get_revision(rev1["revision_id"])["status"] == "superseded"


def test_register_source_hop_le(project):
    src = pk.register_source(project["project_id"], kind="dxf", storage_key="uploads/a.dxf",
                              uploaded_by="ky.su.a", checksum="abc123")
    assert src["kind"] == "dxf"
    assert pk.get_source(src["source_id"])["storage_key"] == "uploads/a.dxf"


def test_register_source_loai_khong_hop_le_nem_loi(project):
    with pytest.raises(ValueError):
        pk.register_source(project["project_id"], kind="jpg", storage_key="a.jpg",
                            uploaded_by="a")


def test_khong_the_ghi_de_source_da_co(project, monkeypatch):
    """`register_source` KHÔNG được lặng lẽ UPDATE khi trùng ID — nguyên tắc "không được
    ghi đè source" (`progress.md` mục 8). Ép trùng ID bằng cách khóa `_new_id` lại."""
    monkeypatch.setattr(pk, "_new_id", lambda prefix: "source:fixed-id-for-test")
    pk.register_source(project["project_id"], kind="dxf", storage_key="a.dxf", uploaded_by="a")
    with pytest.raises(ValueError):
        pk.register_source(project["project_id"], kind="dxf", storage_key="b.dxf", uploaded_by="a")
    # Bản ghi đầu tiên phải còn nguyên, không bị ghi đè bởi lần gọi thứ hai.
    assert pk.get_source("source:fixed-id-for-test")["storage_key"] == "a.dxf"


# --- Object: đường vui + bất biến ID ---

def test_dang_ky_doi_tuong_doc_lai_dung_nguyen_truong(project, revision):
    obj = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                              discipline="mechanical", tag="AHU-003",
                              properties={"cong_suat_lanh_kw": 15.5}, confidence=0.9)
    fetched = pk.get_object(obj["object_id"])
    assert fetched["tag"] == "AHU-003"
    assert fetched["type"] == "ahu"
    assert fetched["discipline"] == "mechanical"
    assert fetched["status"] == "discovered"
    assert fetched["confidence"] == 0.9
    assert fetched["properties"] == {"cong_suat_lanh_kw": 15.5}


def test_object_id_khong_bao_gio_trung_ke_ca_cung_tag(project, revision):
    """Gọi `register_object` hai lần với cùng `tag` phải ra hai `object_id` khác nhau —
    ID không bao giờ tái sử dụng/suy từ tag (mục 7 đặc tả)."""
    obj1 = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                               discipline="mechanical", tag="AHU-003")
    obj2 = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                               discipline="mechanical", tag="AHU-003")
    assert obj1["object_id"] != obj2["object_id"]
    assert len(pk.list_objects(project["project_id"])) == 2


def test_object_id_khong_the_parse_nguoc_ve_type_tuy_tien():
    """Tiền tố chỉ để dò mắt, không mang tính đảm bảo — nhưng ít nhất phải khớp `type` đã
    chuẩn hóa, không phải chuỗi ngẫu nhiên."""
    obj_id = pk._new_id("Pipe Segment!!")
    assert obj_id.startswith("pipe_segment:")


def test_cach_ly_du_an_object_khong_lo_sang_du_an_khac(project, revision):
    project_b = pk.create_project("Dự án B", owner="ky.su.a")
    revision_b = pk.create_revision(project_b["project_id"], created_by="a")

    pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                        discipline="mechanical")
    pk.register_object(project_b["project_id"], revision_b["revision_id"], type="ahu",
                        discipline="mechanical")

    assert len(pk.list_objects(project["project_id"])) == 1
    assert len(pk.list_objects(project_b["project_id"])) == 1


def test_dang_ky_doi_tuong_can_du_an_va_revision_ton_tai(project, revision):
    with pytest.raises(ValueError):
        pk.register_object("project:khong-ton-tai", revision["revision_id"], type="ahu",
                            discipline="mechanical")
    with pytest.raises(ValueError):
        pk.register_object(project["project_id"], "revision:khong-ton-tai", type="ahu",
                            discipline="mechanical")


def test_confidence_ngoai_khoang_nem_loi(project, revision):
    with pytest.raises(ValueError):
        pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                            discipline="mechanical", confidence=1.5)
    with pytest.raises(ValueError):
        pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                            discipline="mechanical", confidence=-0.1)


# --- Vòng đời đối tượng ---

def test_update_object_status_di_dung_chuoi(project, revision):
    obj = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                              discipline="mechanical")
    pk.update_object_status(obj["object_id"], "normalized")
    pk.update_object_status(obj["object_id"], "validated")
    pk.update_object_status(obj["object_id"], "active")
    assert pk.get_object(obj["object_id"])["status"] == "active"

    # Vòng lặp active <-> modified phải được phép.
    pk.update_object_status(obj["object_id"], "modified")
    pk.update_object_status(obj["object_id"], "active")
    assert pk.get_object(obj["object_id"])["status"] == "active"


def test_update_object_status_nhay_lui_tuy_y_bi_chan(project, revision):
    obj = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                              discipline="mechanical")
    # discovered -> active (nhảy cóc, bỏ qua normalized/validated) phải bị chặn.
    with pytest.raises(ValueError):
        pk.update_object_status(obj["object_id"], "active")


def test_update_object_status_archived_la_trang_thai_cuoi(project, revision):
    obj = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                              discipline="mechanical")
    for step in ("normalized", "validated", "active", "superseded", "archived"):
        pk.update_object_status(obj["object_id"], step)
    # archived -> active (hồi phục trực tiếp) chưa có ở lượt này, phải bị chặn.
    with pytest.raises(ValueError):
        pk.update_object_status(obj["object_id"], "active")


# --- Source ref & relation ---

def test_attach_source_ref_can_object_va_source_ton_tai(project, revision):
    obj = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                              discipline="mechanical")
    src = pk.register_source(project["project_id"], kind="dxf", storage_key="a.dxf",
                              uploaded_by="a")
    pk.attach_source_ref(obj["object_id"], src["source_id"], locator="layer=M-DUCT,handle=1A2B")

    with pytest.raises(ValueError):
        pk.attach_source_ref("object:khong-ton-tai", src["source_id"])
    with pytest.raises(ValueError):
        pk.attach_source_ref(obj["object_id"], "source:khong-ton-tai")


def test_link_objects_loai_quan_he_khong_hop_le_nem_loi(project, revision):
    obj1 = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                               discipline="mechanical")
    obj2 = pk.register_object(project["project_id"], revision["revision_id"], type="zone",
                               discipline="mechanical")
    with pytest.raises(ValueError):
        pk.link_objects(obj1["object_id"], obj2["object_id"], "loai_khong_ton_tai",
                         project["project_id"], revision["revision_id"])


def test_link_objects_goi_hai_lan_khong_tao_hang_trung(project, revision):
    obj1 = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                               discipline="mechanical")
    obj2 = pk.register_object(project["project_id"], revision["revision_id"], type="zone",
                               discipline="mechanical")
    pk.link_objects(obj1["object_id"], obj2["object_id"], "serves",
                     project["project_id"], revision["revision_id"])
    pk.link_objects(obj1["object_id"], obj2["object_id"], "serves",
                     project["project_id"], revision["revision_id"])

    relations = pk.get_relations(obj1["object_id"], relation_type="serves")
    assert len(relations) == 1


def test_link_objects_hai_loai_quan_he_cung_cap_deu_giu(project, revision):
    obj1 = pk.register_object(project["project_id"], revision["revision_id"], type="ahu",
                               discipline="mechanical")
    obj2 = pk.register_object(project["project_id"], revision["revision_id"], type="db",
                               discipline="electrical")
    pk.link_objects(obj1["object_id"], obj2["object_id"], "powered_by",
                     project["project_id"], revision["revision_id"])
    pk.link_objects(obj1["object_id"], obj2["object_id"], "near",
                     project["project_id"], revision["revision_id"])

    relations = pk.get_relations(obj1["object_id"])
    assert {r["relation_type"] for r in relations} == {"powered_by", "near"}


# --- Không dùng chung file CSDL người dùng ---

def test_khong_dung_chung_file_csdl_nguoi_dung(tmp_path, monkeypatch):
    """`PROJECT_KERNEL_DB_PATH` phải tách khỏi `USER_DB_PATH` — hai schema không được khóa
    lẫn nhau khi ghi đồng thời (mục 5 đặc tả)."""
    user_db = tmp_path / "users.sqlite"
    kernel_db = tmp_path / "project_kernel.sqlite"
    monkeypatch.setenv("USER_DB_PATH", str(user_db))
    monkeypatch.setenv("PROJECT_KERNEL_DB_PATH", str(kernel_db))
    pk.init_db()
    assert kernel_db.exists()
    assert not user_db.exists()


def test_khong_co_ham_xoa_cung_doi_tuong():
    """Đúng mục 9 đặc tả: không có `delete_object` — chỉ chuyển trạng thái."""
    assert not hasattr(pk, "delete_object")
