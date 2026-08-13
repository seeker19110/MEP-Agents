"""Cảnh báo bảng đơn giá đã cũ (`src/qs_tools.py`).

Đầu ra của bộ phận QS là CON SỐ TIỀN đi vào hồ sơ thầu. Một bảng giá cũ vẫn cho ra bảng
dự toán trông hoàn chỉnh, không dấu hiệu gì — đúng kiểu sai lệch âm thầm mà nguyên tắc số
2 của dự án cấm. Trước đây không có cơ chế nào canh việc này.
"""
import json
from datetime import date, timedelta

import pytest

import src.tools  # noqa: F401 - nạp theo đúng thứ tự import thường dùng
from src.qs_tools import unit_price_effective_date, unit_price_freshness_note


def _meta(tmp_path, **fields):
    path = tmp_path / "unit_prices.meta.json"
    path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_khong_canh_bao_khi_gia_con_moi(tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_PRICE_MAX_AGE_DAYS", raising=False)
    moi = (date.today() - timedelta(days=10)).isoformat()
    assert unit_price_freshness_note(_meta(tmp_path, ngay_hieu_luc=moi)) == ""


def test_canh_bao_khi_qua_nguong(tmp_path, monkeypatch):
    monkeypatch.delenv("UNIT_PRICE_MAX_AGE_DAYS", raising=False)
    cu = (date.today() - timedelta(days=400)).isoformat()
    note = unit_price_freshness_note(_meta(tmp_path, ngay_hieu_luc=cu, nguon="Sở XD 2024"))
    assert "CẢNH BÁO ĐƠN GIÁ" in note
    assert cu in note
    assert "400 ngày" in note
    assert "Sở XD 2024" in note


def test_canh_bao_khi_khong_khai_bao_ngay(tmp_path):
    """Không khai báo cũng phải nói ra — im lặng thì người đọc tưởng giá còn dùng được."""
    note = unit_price_freshness_note(_meta(tmp_path, nguon="ai đó"))
    assert "KHÔNG khai báo ngày hiệu lực" in note


def test_canh_bao_khi_thieu_han_file_meta(tmp_path):
    assert "KHÔNG khai báo ngày hiệu lực" in unit_price_freshness_note(str(tmp_path / "khong_co.json"))


def test_bao_loi_khi_ngay_sai_dinh_dang(tmp_path):
    note = unit_price_freshness_note(_meta(tmp_path, ngay_hieu_luc="01/01/2026"))
    assert "không đúng định dạng" in note


def test_nguong_doi_duoc_bang_bien_moi_truong(tmp_path, monkeypatch):
    ngay = (date.today() - timedelta(days=30)).isoformat()
    path = _meta(tmp_path, ngay_hieu_luc=ngay)

    monkeypatch.setenv("UNIT_PRICE_MAX_AGE_DAYS", "365")
    assert unit_price_freshness_note(path) == ""

    monkeypatch.setenv("UNIT_PRICE_MAX_AGE_DAYS", "7")
    assert "CẢNH BÁO ĐƠN GIÁ" in unit_price_freshness_note(path)


def test_tat_han_canh_bao_bang_nguong_0(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIT_PRICE_MAX_AGE_DAYS", "0")
    cu = (date.today() - timedelta(days=9999)).isoformat()
    assert unit_price_freshness_note(_meta(tmp_path, ngay_hieu_luc=cu)) == ""


def test_khong_dua_vao_thoi_gian_sua_file(tmp_path):
    """Cố ý KHÔNG dùng mtime: `git clone` đặt lại mtime thành thời điểm clone, nên bảng
    giá ba năm trước sẽ trông như vừa cập nhật. Ngày hiệu lực phải là do người cập nhật
    khai báo."""
    cu = (date.today() - timedelta(days=1200)).isoformat()
    path = _meta(tmp_path, ngay_hieu_luc=cu)          # file vừa được ghi xong, mtime = bây giờ
    assert "CẢNH BÁO ĐƠN GIÁ" in unit_price_freshness_note(path)


def test_file_meta_that_cua_du_an_hop_le():
    """`data/unit_prices.meta.json` đi kèm repo phải đọc được và đúng định dạng ngày."""
    ngay, meta = unit_price_effective_date()
    assert ngay, "thiếu ngay_hieu_luc trong data/unit_prices.meta.json"
    date.fromisoformat(ngay)
    assert meta.get("nguon"), "nên ghi rõ nguồn giá để người đọc biết mức tin cậy"


def test_canh_bao_xuat_hien_trong_bao_cao_du_toan(tmp_path, monkeypatch):
    """Cảnh báo phải nằm trong CHÍNH báo cáo dự toán — để trong log thì không ai đọc."""
    import polars as pl

    from src.qs_tools import calc_boq_cost
    from src.workspace import set_workspace_dir

    set_workspace_dir(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UNIT_PRICE_MAX_AGE_DAYS", "1")

    pl.DataFrame({
        "STT": [1],
        "Hạng mục": ["Ống gió tôn tráng kẽm"],
        "Đơn vị": ["m2"],
        "Khối lượng": [10.0],
    }).write_excel(str(tmp_path / "kl.xlsx"))

    report = calc_boq_cost.invoke({
        "takeoff_excel_path": "kl.xlsx",
        "output_excel_path": "dt.xlsx",
    })
    assert "CẢNH BÁO ĐƠN GIÁ" in report, report
