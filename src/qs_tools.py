"""Dự toán chi phí (QS): tra đơn giá vật tư/nhân công và tính giá trị dự toán.

Trước module này, bộ phận QS mới chỉ *đếm khối lượng* (`auto_quantity_takeoff`) chứ
chưa hề *lập dự toán* — không có đơn giá thì bảng khối lượng không ra được con số tiền,
tức là chưa dùng được cho hồ sơ thầu. Ở đây:

- `data/unit_prices.csv` là CSDL đơn giá (vật tư / nhân công / máy) tra theo TỪ KHÓA,
  cố ý để dạng CSV để chủ đầu tư tự sửa giá theo thời điểm và theo vùng.
- `calc_boq_cost` đọc thẳng file Excel khối lượng do `auto_quantity_takeoff` xuất ra,
  ghép đơn giá và tính ra bảng BOQ theo cấu trúc quen thuộc của hồ sơ Việt Nam
  (chi phí trực tiếp -> chi phí chung -> thu nhập chịu thuế tính trước -> VAT).

Toàn bộ phép tính là Python xác định, LLM không tham gia tính tiền.
"""
import logging
import os
import unicodedata

import polars as pl
from langchain_core.tools import tool

from src.workspace import resolve_safe_path, get_project_root

logger = logging.getLogger(__name__)

UNIT_PRICE_CSV = os.path.join("data", "unit_prices.csv")

# Định mức tỷ lệ mặc định theo Thông tư 11/2021/TT-BXD (có thể chỉnh khi gọi tool).
DEFAULT_OVERHEAD_PERCENT = 6.5   # chi phí chung, % trên chi phí trực tiếp
DEFAULT_PROFIT_PERCENT = 5.5     # thu nhập chịu thuế tính trước, % trên (trực tiếp + chung)
DEFAULT_VAT_PERCENT = 10.0       # thuế GTGT


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(text)) if unicodedata.category(c) != "Mn")


def _norm(text: str) -> str:
    """Chuẩn hóa để so khớp: bỏ dấu, thường hóa, gom khoảng trắng."""
    return " ".join(_strip_accents(text).lower().replace("_", " ").split())


def load_unit_prices(csv_path: str = None) -> pl.DataFrame:
    """Nạp bảng đơn giá. Đọc từ project root (tài nguyên dùng chung), không phải
    workspace của phiên — mọi phiên tra cùng một bảng giá.
    Có tích hợp Cache Redis để giảm thời gian đọc I/O đĩa.
    """
    try:
        import redis
        import pickle
        # Đọc qua biến môi trường thay vì hardcode "localhost" — cùng lý do đã sửa ở
        # src/celery_app.py: trong Docker Compose, "localhost" là container riêng của
        # chính process này, không phải service Redis (xem docker-compose.yml).
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        redis_port = int(os.environ.get("REDIS_PORT", "6379"))
        r = redis.Redis(host=redis_host, port=redis_port, db=0, socket_connect_timeout=1)
        cache_key = f"mep_unit_prices_{csv_path or 'default'}"
        cached_data = r.get(cache_key)
        if cached_data:
            return pickle.loads(cached_data)
    except Exception as e:
        r = None
        logger.debug(f"Redis cache không khả dụng: {e}")

    path = csv_path or os.path.join(get_project_root(), UNIT_PRICE_CSV)
    df = pl.read_csv(path)
    
    # Cast to float, fill nulls
    df = df.with_columns([
        pl.col("don_gia_vat_tu").cast(pl.Float64, strict=False).fill_null(0.0),
        pl.col("don_gia_nhan_cong").cast(pl.Float64, strict=False).fill_null(0.0),
        pl.col("don_gia_may").cast(pl.Float64, strict=False).fill_null(0.0),
    ])
        
    if r is not None:
        try:
            r.setex(cache_key, 3600, pickle.dumps(df))  # Cache 1 hour
        except Exception:
            pass

    return df


def match_unit_price(item_name: str, prices: pl.DataFrame):
    """Tìm đơn giá khớp nhất cho một tên hạng mục.

    Khớp theo từ khóa (substring) trước, rơi về fuzzy matching nếu không tìm thấy —
    hoạt động offline hoàn toàn, không cần API key/embedding.
    """
    # 1. Exact substring match theo từ khóa (tu_khoa)
    name_norm = _norm(item_name)
    best_row, best_score = None, 0
    
    for row in prices.iter_rows(named=True):
        for keyword in str(row.get("tu_khoa", "")).split("|"):
            kw = _norm(keyword)
            if kw and kw in name_norm and len(kw) > best_score:
                best_row, best_score = row, len(kw)
                
    # 2. Fuzzy matching nếu không tìm thấy exact
    if best_row is None:
        try:
            from rapidfuzz import fuzz
            best_fuzz = 0
            for row in prices.iter_rows(named=True):
                for keyword in str(row.get("tu_khoa", "")).split("|"):
                    kw = _norm(keyword)
                    if kw:
                        score = fuzz.partial_ratio(kw, name_norm)
                        if score > 85 and score > best_fuzz:
                            best_fuzz = score
                            best_row = row
        except ImportError:
            pass

    return best_row


@tool
def lookup_unit_price(keyword: str) -> str:
    """Tra đơn giá vật tư/nhân công của một hạng mục MEPF trong CSDL đơn giá nội bộ."""
    logger.info("Lookup unit price: %s", keyword)
    try:
        prices = load_unit_prices()
        kw_norm = _norm(keyword)
        hits = []
        
        try:
            from rapidfuzz import fuzz
            has_fuzz = True
        except ImportError:
            has_fuzz = False
            
        for row in prices.iter_rows(named=True):
            row_name_norm = _norm(str(row.get("ten_cong_tac", "")))
            is_match = False
            if kw_norm in row_name_norm:
                is_match = True
            else:
                for k in str(row.get("tu_khoa", "")).split("|"):
                    k_norm = _norm(k)
                    if k_norm and k_norm in kw_norm:
                        is_match = True
                        break
                    elif has_fuzz and k_norm and fuzz.partial_ratio(k_norm, kw_norm) > 85:
                        is_match = True
                        break
            if is_match:
                hits.append(row)

        if not hits:
            return (f"Không tìm thấy đơn giá cho '{keyword}' trong CSDL ({UNIT_PRICE_CSV}). "
                    f"Hãy bổ sung dòng đơn giá mới vào file CSV này trước khi lập dự toán.")

        lines = [f"Đơn giá tra được cho '{keyword}' (đơn vị: VNĐ):"]
        for row in hits[:10]:
            total = row["don_gia_vat_tu"] + row["don_gia_nhan_cong"] + row["don_gia_may"]
            lines.append(
                f"- [{row['ma_hieu']}] {row['ten_cong_tac']} ({row['don_vi']}): "
                f"VT {row['don_gia_vat_tu']:,.0f} + NC {row['don_gia_nhan_cong']:,.0f} + "
                f"M {row['don_gia_may']:,.0f} = {total:,.0f}/{row['don_vi']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Lỗi tra đơn giá: {e}"


@tool
def calc_boq_cost(takeoff_excel_path: str, output_excel_path: str = "du_toan_chi_phi.xlsx",
                  overhead_percent: float = DEFAULT_OVERHEAD_PERCENT,
                  profit_percent: float = DEFAULT_PROFIT_PERCENT,
                  vat_percent: float = DEFAULT_VAT_PERCENT) -> str:
    """Lập BẢNG DỰ TOÁN CHI PHÍ (BOQ) thật từ file Excel khối lượng đã bóc tách.

    Đọc file Excel do `auto_quantity_takeoff` xuất ra (các cột STT / Hạng mục / Đơn vị /
    Khối lượng), tự tra đơn giá trong `data/unit_prices.csv`, nhân khối lượng x đơn giá
    và xuất file Excel dự toán theo cấu trúc hồ sơ Việt Nam: chi phí trực tiếp (vật tư,
    nhân công, máy) -> chi phí chung -> thu nhập chịu thuế tính trước -> thuế GTGT ->
    tổng giá trị dự toán. Hạng mục không tra được đơn giá vẫn được liệt kê và đánh dấu
    rõ "CHƯA CÓ ĐƠN GIÁ" thay vì bị bỏ qua âm thầm.
    """
    logger.info("Calculating BOQ cost: %s -> %s", takeoff_excel_path, output_excel_path)
    try:
        src_path = resolve_safe_path(takeoff_excel_path)
        if not os.path.exists(src_path):
            return (f"Không tìm thấy file khối lượng '{takeoff_excel_path}'. "
                    f"Hãy chạy `auto_quantity_takeoff` trước để tạo bảng khối lượng.")

        df = pl.read_excel(src_path)
        cols = df.columns
        name_col = next((c for c in cols if _norm(c) in ("hang muc", "ten cong tac", "noi dung")), None)
        qty_col = next((c for c in cols if _norm(c) in ("khoi luong", "so luong")), None)
        unit_col = next((c for c in cols if _norm(c) == "don vi"), None)
        
        if not name_col or not qty_col:
            return (f"File '{takeoff_excel_path}' không có cột 'Hạng mục' và 'Khối lượng' cần thiết. "
                    f"Các cột hiện có: {cols}")

        prices = load_unit_prices()
        rows, missing = [], []
        
        for item in df.iter_rows(named=True):
            name = str(item.get(name_col, ""))
            try:
                qty = float(item.get(qty_col, 0.0))
            except (TypeError, ValueError):
                qty = 0.0
                
            match = match_unit_price(name, prices)

            if match is None:
                missing.append(name)
                rows.append({
                    "STT": len(rows) + 1, "Mã hiệu": "", "Hạng mục": name,
                    "Đơn vị": str(item.get(unit_col, "")) if unit_col else "", "Khối lượng": qty,
                    "Đơn giá VT": 0, "Đơn giá NC": 0, "Đơn giá M": 0,
                    "Thành tiền VT": 0, "Thành tiền NC": 0, "Thành tiền M": 0,
                    "Thành tiền": 0, "Ghi chú": "CHƯA CÓ ĐƠN GIÁ - cần bổ sung vào data/unit_prices.csv",
                })
                continue

            vt, nc, m = match.get("don_gia_vat_tu", 0.0), match.get("don_gia_nhan_cong", 0.0), match.get("don_gia_may", 0.0)
            rows.append({
                "STT": len(rows) + 1, "Mã hiệu": str(match.get("ma_hieu", "")), "Hạng mục": name,
                "Đơn vị": str(match.get("don_vi", "")), "Khối lượng": qty,
                "Đơn giá VT": vt, "Đơn giá NC": nc, "Đơn giá M": m,
                "Thành tiền VT": round(qty * vt), "Thành tiền NC": round(qty * nc),
                "Thành tiền M": round(qty * m),
                "Thành tiền": round(qty * (vt + nc + m)),
                "Ghi chú": str(match.get("ten_cong_tac", "")),
            })

        if not rows:
            return "File khối lượng rỗng, không có hạng mục nào để lập dự toán."

        direct_cost = sum(r["Thành tiền"] for r in rows)
        overhead = direct_cost * overhead_percent / 100.0
        profit = (direct_cost + overhead) * profit_percent / 100.0
        before_vat = direct_cost + overhead + profit
        vat = before_vat * vat_percent / 100.0
        total = before_vat + vat

        summary_rows = [
            ("I", "CHI PHÍ TRỰC TIẾP (Vật tư + Nhân công + Máy)", direct_cost),
            ("II", f"CHI PHÍ CHUNG ({overhead_percent}% x I)", overhead),
            ("III", f"THU NHẬP CHỊU THUẾ TÍNH TRƯỚC ({profit_percent}% x (I+II))", profit),
            ("IV", "GIÁ TRỊ TRƯỚC THUẾ (I+II+III)", before_vat),
            ("V", f"THUẾ GTGT ({vat_percent}%)", vat),
            ("VI", "TỔNG GIÁ TRỊ DỰ TOÁN SAU THUẾ", total),
        ]

        out_path = output_excel_path if output_excel_path.endswith(".xlsx") else output_excel_path + ".xlsx"
        out_safe = resolve_safe_path(out_path)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)

        detail_df = pl.DataFrame(rows)
        summary_df = pl.DataFrame(
            [{"Khoản mục": code, "Nội dung": label, "Giá trị (VNĐ)": round(value)}
             for code, label, value in summary_rows]
        )
        
        import xlsxwriter
        with xlsxwriter.Workbook(out_safe) as workbook:
            detail_df.write_excel(workbook=workbook, worksheet="Chi tiết dự toán")
            summary_df.write_excel(workbook=workbook, worksheet="Tổng hợp")

        report = [
            f"LẬP DỰ TOÁN CHI PHÍ THÀNH CÔNG — đã ghi file Excel: {out_path}",
            f"- Số hạng mục: {len(rows)} (tra được đơn giá: {len(rows) - len(missing)})",
            "",
            "TỔNG HỢP GIÁ TRỊ DỰ TOÁN:",
        ]
        for code, label, value in summary_rows:
            report.append(f"  {code}. {label}: {round(value):,} VNĐ")
        if missing:
            report.append("")
            report.append(f"- CẢNH BÁO: {len(missing)} hạng mục CHƯA CÓ ĐƠN GIÁ nên đang tính bằng 0, "
                          f"tổng dự toán vì vậy còn THIẾU. Cần bổ sung vào data/unit_prices.csv: "
                          + ", ".join(missing[:8]) + ("..." if len(missing) > 8 else ""))
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi lập dự toán chi phí: {e}"


# --- Xuất BOQ theo mẫu chuẩn hồ sơ thầu Việt Nam ---

# Nhận diện hệ kỹ thuật của từng hạng mục để gom nhóm theo chương mục quen thuộc.
SYSTEM_GROUPS = [
    ("A", "HỆ THỐNG ĐIỀU HÒA KHÔNG KHÍ & THÔNG GIÓ (HVAC)",
     ("ong gio", "duct", "diffuser", "mieng gio", "fcu", "ahu", "chiller", "dan lanh",
      "ong dong", "refrigerant", "quat", "hvac", "thong gio")),
    ("B", "HỆ THỐNG ĐIỆN (ELECTRICAL)",
     ("cap dien", "cable", "day dien", "den", "light", "socket", "o cam", "switch",
      "cong tac", "tu dien", "panel", "mang cap", "tray", "elec", "dien")),
    ("C", "HỆ THỐNG CẤP THOÁT NƯỚC (PLUMBING)",
     ("ong upvc", "upvc", "ppr", "cap nuoc", "thoat nuoc", "be nuoc", "bon nuoc", "bom",
      "pump", "water", "drain", "plumb", "nuoc")),
    ("D", "HỆ THỐNG PHÒNG CHÁY CHỮA CHÁY (PCCC)",
     ("sprinkler", "dau phun", "chua chay", "pccc", "hong nuoc", "hydrant", "binh bot",
      "extinguisher", "bao chay", "ong thep")),
]
OTHER_GROUP = ("E", "HẠNG MỤC KHÁC")


def classify_boq_group(item_name: str):
    """Xếp một hạng mục vào chương mục BOQ (A/B/C/D/E) theo từ khóa tên."""
    name = _norm(item_name)
    for code, title, keywords in SYSTEM_GROUPS:
        if any(kw in name for kw in keywords):
            return code, title
    return OTHER_GROUP


@tool
def export_boq_vietnam(boq_excel_path: str, output_excel_path: str = "BOQ_mau_chuan.xlsx",
                       project_name: str = "", contractor: str = "", location: str = "") -> str:
    """Xuất BẢNG TIÊN LƯỢNG - DỰ TOÁN theo MẪU CHUẨN hồ sơ thầu Việt Nam.

    Nhận file Excel dự toán do `calc_boq_cost` tạo ra (hoặc bảng khối lượng của
    `auto_quantity_takeoff`) và định dạng lại thành bảng quen thuộc với hồ sơ thầu:
    có tiêu đề công trình, hạng mục được gom theo CHƯƠNG MỤC từng hệ (A. HVAC, B. Điện,
    C. Cấp thoát nước, D. PCCC), đánh số STT theo chương, cộng tiểu tổng từng chương và
    tổng cộng cuối bảng. Dùng khi khách hàng cần bảng nộp thầu chứ không phải bảng thô.
    """
    logger.info("Exporting Vietnamese BOQ template: %s -> %s", boq_excel_path, output_excel_path)
    try:
        src = resolve_safe_path(boq_excel_path)
        if not os.path.exists(src):
            return (f"Không tìm thấy file '{boq_excel_path}'. Hãy chạy `auto_quantity_takeoff` và "
                    f"`calc_boq_cost` trước để có bảng dự toán nguồn.")

        df = pd.read_excel(src)
        name_col = next((c for c in df.columns if _norm(c) in ("hang muc", "ten cong tac", "noi dung")), None)
        qty_col = next((c for c in df.columns if _norm(c) in ("khoi luong", "so luong")), None)
        if not name_col or not qty_col:
            return f"File '{boq_excel_path}' thiếu cột 'Hạng mục'/'Khối lượng'. Cột hiện có: {list(df.columns)}"

        unit_col = next((c for c in df.columns if _norm(c) == "don vi"), None)
        total_col = next((c for c in df.columns if _norm(c) == "thanh tien"), None)
        code_col = next((c for c in df.columns if _norm(c) == "ma hieu"), None)
        unit_price_available = {
            "vt": next((c for c in df.columns if _norm(c) == "don gia vt"), None),
            "nc": next((c for c in df.columns if _norm(c) == "don gia nc"), None),
        }

        # Gom hạng mục theo chương mục.
        groups = {}
        for _, item in df.iterrows():
            code, title = classify_boq_group(str(item[name_col]))
            groups.setdefault((code, title), []).append(item)

        rows = []
        grand_total = 0.0
        for (code, title) in sorted(groups, key=lambda g: g[0]):
            items = groups[(code, title)]
            rows.append({"STT": code, "Mã hiệu": "", "Nội dung công việc": title,
                         "Đơn vị": "", "Khối lượng": None, "Đơn giá VT": None,
                         "Đơn giá NC": None, "Thành tiền": None})
            group_total = 0.0
            for i, item in enumerate(items, start=1):
                line_total = float(item[total_col]) if total_col and pd.notna(item.get(total_col)) else 0.0
                group_total += line_total
                rows.append({
                    "STT": f"{code}.{i}",
                    "Mã hiệu": item[code_col] if code_col and pd.notna(item.get(code_col)) else "",
                    "Nội dung công việc": item[name_col],
                    "Đơn vị": item[unit_col] if unit_col and pd.notna(item.get(unit_col)) else "",
                    "Khối lượng": item[qty_col],
                    "Đơn giá VT": item[unit_price_available["vt"]] if unit_price_available["vt"] else None,
                    "Đơn giá NC": item[unit_price_available["nc"]] if unit_price_available["nc"] else None,
                    "Thành tiền": line_total if total_col else None,
                })
            grand_total += group_total
            rows.append({"STT": "", "Mã hiệu": "", "Nội dung công việc": f"Cộng {title}",
                         "Đơn vị": "", "Khối lượng": None, "Đơn giá VT": None,
                         "Đơn giá NC": None, "Thành tiền": round(group_total) if total_col else None})

        rows.append({"STT": "", "Mã hiệu": "", "Nội dung công việc": "TỔNG CỘNG",
                     "Đơn vị": "", "Khối lượng": None, "Đơn giá VT": None,
                     "Đơn giá NC": None, "Thành tiền": round(grand_total) if total_col else None})

        out_path = output_excel_path if output_excel_path.endswith(".xlsx") else output_excel_path + ".xlsx"
        out_safe = resolve_safe_path(out_path)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)

        header = pd.DataFrame([
            {"Thông tin": "Công trình", "Nội dung": project_name or "(chưa nhập tên công trình)"},
            {"Thông tin": "Địa điểm", "Nội dung": location or "(chưa nhập địa điểm)"},
            {"Thông tin": "Đơn vị lập", "Nội dung": contractor or "(chưa nhập đơn vị)"},
            {"Thông tin": "Tên bảng", "Nội dung": "BẢNG TIÊN LƯỢNG - DỰ TOÁN HẠNG MỤC MEPF"},
            {"Thông tin": "Đơn vị tiền tệ", "Nội dung": "VNĐ"},
        ])
        with pd.ExcelWriter(out_safe, engine="openpyxl") as writer:
            header.to_excel(writer, sheet_name="Trang bìa", index=False)
            pd.DataFrame(rows).to_excel(writer, sheet_name="Tiên lượng - Dự toán", index=False)

        report = [
            f"XUẤT BOQ THEO MẪU CHUẨN VIỆT NAM THÀNH CÔNG: {out_path}",
            f"- Công trình: {project_name or '(chưa nhập)'}",
            f"- Số chương mục: {len(groups)}",
        ]
        for (code, title) in sorted(groups, key=lambda g: g[0]):
            report.append(f"  {code}. {title}: {len(groups[(code, title)])} hạng mục")
        if total_col:
            report.append(f"- TỔNG CỘNG: {round(grand_total):,} VNĐ")
        else:
            report.append("- Lưu ý: File nguồn chưa có cột 'Thành tiền' nên bảng chỉ có khối lượng, "
                          "chưa có giá trị tiền. Chạy `calc_boq_cost` trước để có dự toán đầy đủ.")
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi xuất BOQ mẫu chuẩn: {e}"

# Đặt SAU các hàm phía trên (không phải đầu file) vì import `src.tools` ở đây, mà
# `src.tools` (module cha) lại import ngược từ `qs_tools` ở module-level -> đặt ở đầu
# file sẽ tạo vòng import khi `qs_tools` được nạp trước `tools`. Xem giải thích tương tự
# ở `src/api.py`.
import json  # noqa: E402
import math  # noqa: E402
import pandas as pd  # noqa: E402
from ezdxf import audit  # noqa: E402
from src import cad_loader, cad_geometry, cad_standards, cad_units  # noqa: E402
from src.tools import normalize_mepf_parameter_spec  # noqa: E402
from src.bim_tools import classify_layer_system  # noqa: E402

@tool
def auto_quantity_takeoff(file_path: str, output_excel_path: str = "bao_cao_du_toan.xlsx",
                          max_distance: float = 2000.0, wastage_percent: float = 5.0,
                          pipe_stock_length_mm: float = 6000.0,
                          drawing_unit: str = "") -> str:
    """Bóc tách khối lượng TỰ ĐỘNG & TOÀN DIỆN từ file CAD (.dxf/.dwg) và xuất thẳng ra
    Excel CHỈ BẰNG MỘT LẦN GỌI TOOL DUY NHẤT — không cần LLM tự đếm block, tự cộng chiều
    dài hay tự soạn JSON (những bước dễ sai với model AI yếu/model chạy offline qua Ollama).
    Quy trình bên trong (thuần toán học/hình học, KHÔNG dùng LLM):
    1. Nạp bản vẽ (tự chuyển .dwg sang .dxf nếu cần, tự gộp nội dung XREF nếu có) và audit
       làm sạch cấu trúc file.
    2. XÁC ĐỊNH VÀ QUY ĐỔI ĐƠN VỊ BẢN VẼ ($INSUNITS, hoặc tham số `drawing_unit` do người
       dùng khai, hoặc suy đoán từ kích thước bao khi bản vẽ Unitless). Chiều dài được quy
       đổi THẬT theo đơn vị đó — bản vẽ vẽ bằng mét/inch/feet ra đúng số mét, thay vì mặc
       định coi mọi bản vẽ là mm rồi chia cứng 1000 (sai 1000 lần với bản vẽ mét). Chỉ khi
       KHÔNG xác định được đơn vị mới cảnh báo để kỹ sư khai lại `drawing_unit`.
    3. PHÁT HIỆN HÌNH HỌC TRÙNG LẶP (overkill) trước khi cộng chiều dài — nếu bản vẽ chưa
       qua `optimize_cad_drawing`, các đoạn ống bị trace/copy chồng đè sẽ bị cộng dồn thừa;
       tool cảnh báo tổng chiều dài nghi trùng lặp theo layer thay vì âm thầm tính sai. Riêng
       hình học TRÙNG VỊ TRÍ giữa nội dung XREF và hình học vẽ trực tiếp trong bản vẽ chính
       (khác layer nên overkill theo layer không bắt được — thường do khách trace lại nội
       dung xref khi gộp thủ công nhiều nguồn) được kiểm tra và cảnh báo RIÊNG.
    4. BUNG RUỘT BLOCK: đếm cả thiết bị lồng bên trong block khác và cộng tuyến ống/dây vẽ
       BÊN TRONG block (cụm WC, module ống gió lặp lại) — phần này trước đây bị bỏ sót 100%;
       một entity MINSERT (lưới hàng x cột, VD dàn đèn) được đếm đủ số bản sao thay vì đếm 1.
    5. Đếm số lượng từng loại Block (thiết bị) theo tên + thuộc tính (attributes) — biến thể
       Block ĐỘNG (AutoCAD lưu thành block ẩn danh `*U12`) được tra lại TÊN GỐC để không xé
       một chủng loại thiết bị thành nhiều dòng tên vô nghĩa; cảnh báo
       riêng các Block bị insert lệch tỷ lệ (scale khác 1) vì kích thước thực tế sẽ khác chuẩn,
       và cảnh báo riêng các đối tượng thuộc Layer đang TẮT/ĐÓNG BĂNG (vẫn được tính vào khối
       lượng vì không tự đoán ý khách, nhưng nêu rõ để khách xác nhận có nên loại hay không).
    6. Cộng dồn tổng chiều dài THẬT từng tuyến ống/dây theo Layer — tính đúng cung cong
       (bulge trong LWPOLYLINE, entity ARC/CIRCLE, đường cong tự do SPLINE/ELLIPSE) thay vì
       chỉ đo dây cung, cộng cả chênh lệch cao độ Z nếu tuyến đi xiên giữa các cao độ, quy
       tọa độ OCS về WCS cho đối tượng vẽ trong UCS lật/xoay, và LOẠI lưới 3D (polyface/
       polygon mesh) khỏi chiều dài ống vì đó là bề mặt mô hình chứ không phải tuyến.
    7. Suy ra số lượng phụ kiện co/tê/măng sông theo từng layer từ chính hình học tuyến —
       cần thiết vì ống vẽ bằng LINE/POLYLINE thuần (không chèn Block phụ kiện) trước đây
       bị bỏ sót hoàn toàn phần phụ kiện.
    8. Liên kết Ghi chú văn bản (TEXT/MTEXT, ví dụ 'Ống uPVC Ø110') với Layer ống gần nhất
       (Spatial Matching) để đặt tên hạng mục đúng theo bản vẽ thay vì chỉ ghi tên Layer thô —
       nếu tuyến gần nhất và tuyến gần nhì thuộc HAI HỆ KHÁC NHAU (VD ống gió HVAC và máng cáp
       Điện chạy song song sát nhau) với khoảng cách tương đương, ghi chú được coi là MƠ HỒ và
       KHÔNG gán vào tuyến nào (liệt kê riêng để kỹ sư tự đối chiếu) thay vì đoán bừa theo hệ
       gần nhất.
    9. Cộng % hao hụt vật tư (`wastage_percent`, mặc định 5%) vào khối lượng ống/dây — số đo
       hình học thuần luôn thấp hơn khối lượng cần mua thực tế do cắt nối, bù trừ khi thi công.
    10. Ghi toàn bộ kết quả (STT, Hạng mục, Đơn vị, Khối lượng, Ghi chú) ra file Excel thật.
    Dùng tool này làm bước ĐẦU TIÊN VÀ DUY NHẤT khi cần bóc khối lượng/lập dự toán từ CAD;
    chỉ cần dùng `read_cad`/`analyze_cad_spatial_context` riêng lẻ khi cần phân tích sâu hơn.
    """
    logger.info("Auto Quantity Takeoff (offline, deterministic): %s -> %s", file_path, output_excel_path)
    try:
        doc, load_notes = cad_loader.load_drawing(file_path)

        # Xác định đơn vị bản vẽ TRƯỚC KHI tính toán và QUY ĐỔI THẬT theo đơn vị đó. Bản
        # cũ chia cứng cho 1000 (mặc định mm) và chỉ *cảnh báo* khi đơn vị khác — bản vẽ vẽ
        # bằng mét vẫn xuất ra Excel với con số nhỏ hơn thực tế 1000 lần. Cảnh báo không sửa
        # được số; quy đổi thì có.
        dwg_unit = cad_units.detect_drawing_unit(doc, drawing_unit)
        insunits_warning = cad_units.unit_warning(dwg_unit) or None

        # Mọi ngưỡng dưới đây vốn khai theo MILIMET nên phải đổi sang đơn vị bản vẽ, nếu
        # không thì đổi đúng chiều dài mà vẫn suy sai số phụ kiện và bán kính gán ghi chú.
        stock_length_du = dwg_unit.mm(pipe_stock_length_mm)
        joint_tolerance_du = dwg_unit.mm(cad_geometry.JOINT_TOLERANCE)
        max_distance_du = dwg_unit.mm(max_distance)

        auditor = audit.Auditor(doc)
        auditor.run()
        audit_fixes = len(auditor.fixes)

        msp = doc.modelspace()

        block_counts = {}  # (name, attrib_str) -> count
        scaled_blocks = {}  # (name, xscale, yscale) -> count
        exploded_blocks = {}  # tên block -> chiều dài tuyến lấy được từ ruột block
        anonymous_blocks = {}  # block ẩn danh (*U…) không tra được tên gốc -> số lần chèn
        nested_block_hits = {}  # tên block lồng bên trong block khác -> số lượng
        # Ngưỡng coi hình học trong block là TUYẾN THẬT chứ không phải nét vẽ ký hiệu.
        significant_block_length_du = dwg_unit.mm(1000.0)
        texts = []
        all_segments = []  # dùng cho cả tổng chiều dài, spatial-match và suy phụ kiện

        # Layer bị TẮT (off) hoặc ĐÓNG BĂNG (frozen) thường là nội dung tham chiếu cũ/không
        # còn hiệu lực trong bản vẽ hiện hành — vẫn đếm vào khối lượng (không tự loại vì có
        # thể khách chỉ tạm tắt để dễ nhìn, không có nghĩa là bỏ) nhưng CẢNH BÁO riêng để QS
        # tự xác nhận với khách, tránh lẫn nội dung không dùng vào dự toán.
        _layer_visibility_cache = {}
        off_frozen_layer_hits = {}

        def _is_layer_off_or_frozen(layer_name: str) -> bool:
            if layer_name not in _layer_visibility_cache:
                layer_obj = doc.layers.get(layer_name) if layer_name in doc.layers else None
                _layer_visibility_cache[layer_name] = bool(
                    layer_obj and (layer_obj.is_off() or layer_obj.is_frozen())
                )
            return _layer_visibility_cache[layer_name]

        for entity in msp:
            dxftype = entity.dxftype()
            entity_layer = entity.dxf.layer
            if _is_layer_off_or_frozen(entity_layer):
                off_frozen_layer_hits[entity_layer] = off_frozen_layer_hits.get(entity_layer, 0) + 1

            if dxftype == 'INSERT':
                # Block động được AutoCAD lưu thành block ẩn danh (*U12); lấy lại tên gốc
                # để không xé một chủng loại thiết bị thành nhiều dòng tên vô nghĩa.
                b_name, is_anonymous = cad_geometry.effective_block_name(entity, doc)
                if is_anonymous:
                    anonymous_blocks[b_name] = anonymous_blocks.get(b_name, 0) + 1
                attribs = {}
                if hasattr(entity, 'attribs') and entity.attribs:
                    for attrib in entity.attribs:
                        if hasattr(attrib, 'dxf') and hasattr(attrib.dxf, 'tag'):
                            attribs[attrib.dxf.tag] = getattr(attrib.dxf, 'text', '')
                attr_str = json.dumps(attribs, ensure_ascii=False) if attribs else ""
                key = (b_name, attr_str)
                # MINSERT: một entity INSERT có thể là cả một LƯỚI hàng x cột (dàn đèn,
                # dàn đầu phun). Đếm 1 là bóc thiếu cả dàn.
                repeat = cad_geometry.insert_repeat_count(entity)
                block_counts[key] = block_counts.get(key, 0) + repeat
                if cad_geometry.is_scaled(entity):
                    xs, ys, _ = cad_geometry.block_scale(entity)
                    skey = (b_name, round(xs, 3), round(ys, 3))
                    scaled_blocks[skey] = scaled_blocks.get(skey, 0) + repeat

                # Bung ruột Block để lấy tuyến ống/dây và thiết bị vẽ BÊN TRONG block —
                # phần này trước đây bị bỏ sót hoàn toàn (xem `cad_geometry.explode_insert`).
                inner_segments, inner_inserts = cad_geometry.explode_insert(entity, doc)
                inner_length = sum(s["length"] for s in inner_segments)
                if inner_length >= significant_block_length_du:
                    # Ngưỡng độ dài: nét vẽ của một KÝ HIỆU (van, đèn, ổ cắm) chỉ dài vài
                    # chục mm và không phải tuyến — cộng chúng vào sẽ thổi phồng chiều dài
                    # ống. Chỉ block chứa tuyến thật (dài hơn ngưỡng) mới được gộp.
                    all_segments.extend(inner_segments)
                    exploded_blocks[b_name] = exploded_blocks.get(b_name, 0.0) + inner_length
                for inner_name, inner_qty in inner_inserts:
                    inner_key = (inner_name, "")
                    block_counts[inner_key] = block_counts.get(inner_key, 0) + inner_qty
                    nested_block_hits[inner_name] = nested_block_hits.get(inner_name, 0) + inner_qty
                continue

            if dxftype in ('TEXT', 'MTEXT'):
                raw = entity.dxf.text if dxftype == 'TEXT' else entity.text
                t_str = normalize_mepf_parameter_spec((raw or '').strip())
                pos = entity.dxf.insert
                if t_str:
                    texts.append({"text": t_str, "pos": (pos.x, pos.y)})
                continue

            all_segments.extend(cad_geometry.collect_segments([entity]))

        local_segment_count = len(all_segments)  # ranh giới: segment sau chỉ số này là từ XREF

        # XREF: gộp thêm tuyến nằm trong file tham chiếu ngoài, nếu có khai báo và tìm
        # được file đi kèm. Không tìm được thì nêu rõ tên trong load_notes thay vì âm thầm
        # bỏ qua — bỏ sót một xref có thể làm khối lượng thiếu cả một hệ thống.
        base_dir = os.path.dirname(resolve_safe_path(file_path))
        import concurrent.futures

        xref_defs = {name: path for name, path in cad_loader.list_xrefs(doc)}
        xref_segments = []
        if xref_defs:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Chạy resolve_xref_segments trong luồng riêng để tăng tốc đọc file I/O
                future = executor.submit(
                    cad_loader.resolve_xref_segments,
                    doc, base_dir, lambda space: cad_geometry.collect_segments(list(space))
                )
                xref_segments, xref_notes = future.result()
                all_segments.extend(xref_segments)
                load_notes.extend(xref_notes)

        # Phát hiện hình học TRÙNG LẶP (overkill) trước khi cộng dồn chiều dài — nếu khách
        # gửi file chưa qua `optimize_cad_drawing`, các đoạn ống bị trace/copy chồng đè sẽ
        # bị CỘNG DỒN LÀM ĐÔI chiều dài mà không có dấu hiệu bất thường nào trong kết quả.
        # Chỉ cảnh báo (không tự xóa) vì tool này không được phép âm thầm sửa hình học.
        _OVERKILL_TOLERANCE = joint_tolerance_du

        def _rounded_endpoints(seg):
            (sax, say, _), (sbx, sby, _) = seg["start"], seg["end"]
            p1 = (round(sax / _OVERKILL_TOLERANCE), round(say / _OVERKILL_TOLERANCE))
            p2 = (round(sbx / _OVERKILL_TOLERANCE), round(sby / _OVERKILL_TOLERANCE))
            return frozenset((p1, p2))

        seen_seg_keys = {}
        duplicate_length_by_layer = {}
        for seg in all_segments:
            key = (seg["layer"], _rounded_endpoints(seg))
            if key in seen_seg_keys:
                duplicate_length_by_layer[seg["layer"]] = duplicate_length_by_layer.get(seg["layer"], 0.0) + seg["length"]
            else:
                seen_seg_keys[key] = True

        # Chồng lấn XREF <-> hình học vẽ LOCAL: khác với overkill cùng layer ở trên, đây là
        # trường hợp khách vô tình VẼ LẠI (trace) nội dung xref vào bản vẽ chính (thường khi
        # gộp thủ công nhiều nguồn) — layer có thể KHÁC tên nên overkill theo layer ở trên
        # không bắt được. Chỉ so khớp LOCAL với XREF (không so cùng nhóm với nhau) để tránh
        # báo nhầm hai hệ thống thật khác nhau tình cờ chạy trùng vị trí.
        xref_overlap_length = 0.0
        xref_overlap_layers = set()
        if xref_segments:
            local_points = {}
            for seg in all_segments[:local_segment_count]:
                local_points.setdefault(_rounded_endpoints(seg), []).append(seg)
            for xseg in xref_segments:
                matches = local_points.get(_rounded_endpoints(xseg))
                if matches:
                    xref_overlap_length += xseg["length"]
                    xref_overlap_layers.add(xseg["layer"])
                    xref_overlap_layers.update(m["layer"] for m in matches)

        layer_lengths = {}
        for seg in all_segments:
            layer_lengths[seg["layer"]] = layer_lengths.get(seg["layer"], 0.0) + seg["length"]

        # Liên kết ghi chú <-> layer ống gần nhất, để đặt tên hạng mục theo đúng ghi chú
        # trên bản vẽ (ví dụ 'Ống uPVC Ø110') thay vì chỉ hiển thị tên Layer kỹ thuật.
        # Đề phòng GÁN NHẦM HỆ: hai tuyến khác hệ (VD ống gió HVAC và máng cáp Điện) chạy
        # song song sát nhau có thể khiến layer gần nhất KHÔNG PHẢI hệ đúng của ghi chú —
        # nếu tuyến gần nhì thuộc hệ KHÁC và khoảng cách gần tương đương, coi là mơ hồ và
        # bỏ qua thay vì đoán bừa (liệt kê riêng để kỹ sư tự kiểm tra).
        _AMBIGUITY_RATIO = 1.3
        layer_systems = {layer: classify_layer_system(layer) for layer in {s["layer"] for s in all_segments}}
        layer_labels = {}  # layer -> {label: count of matching texts}
        ambiguous_labels = []
        if texts and all_segments:
            try:
                import numpy as np
                # Vectorized calculations
                seg_arr = np.array([
                    [s["start"][0], s["start"][1], s["end"][0], s["end"][1]]
                    for s in all_segments
                ], dtype=float)
                seg_systems = np.array([layer_systems[s["layer"]] for s in all_segments])

                ax = seg_arr[:, 0]
                ay = seg_arr[:, 1]
                bx = seg_arr[:, 2]
                by = seg_arr[:, 3]

                dx = bx - ax
                dy = by - ay
                l2 = dx**2 + dy**2
                zero_l2 = (l2 == 0)
                l2_safe = np.where(zero_l2, 1.0, l2)

                for t in texts:
                    tx, ty = t["pos"]

                    t_val = ((tx - ax) * dx + (ty - ay) * dy) / l2_safe
                    t_val = np.clip(t_val, 0.0, 1.0)

                    proj_x = ax + t_val * dx
                    proj_y = ay + t_val * dy

                    dist_sq = (tx - proj_x)**2 + (ty - proj_y)**2
                    dist_sq = np.where(zero_l2, (tx - ax)**2 + (ty - ay)**2, dist_sq)

                    min_idx = np.argmin(dist_sq)
                    min_dist = np.sqrt(dist_sq[min_idx])

                    if min_dist > max_distance_du:
                        continue

                    nearest_system = seg_systems[min_idx]
                    if nearest_system:
                        diff_system_mask = seg_systems != nearest_system
                        if diff_system_mask.any():
                            alt_min_dist = math.sqrt(np.min(np.where(diff_system_mask, dist_sq, np.inf)))
                            if alt_min_dist <= min_dist * _AMBIGUITY_RATIO:
                                ambiguous_labels.append(t["text"])
                                continue

                    best_layer = all_segments[min_idx]["layer"]
                    bucket = layer_labels.setdefault(best_layer, {})
                    bucket[t["text"]] = bucket.get(t["text"], 0) + 1
            except ImportError:
                # Fallback to python loop if numpy is not available
                def _seg_dist(px, py, seg):
                    (sax, say, _), (sbx, sby, _) = seg["start"], seg["end"]
                    sl2 = (sbx - sax) ** 2 + (sby - say) ** 2
                    if sl2 == 0:
                        return math.hypot(px - sax, py - say)
                    st = max(0.0, min(1.0, ((px - sax) * (sbx - sax) + (py - say) * (sby - say)) / sl2))
                    return math.hypot(px - (sax + st * (sbx - sax)), py - (say + st * (sby - say)))

                for t in texts:
                    tx, ty = t["pos"]
                    min_dist, best_layer, best_system = float('inf'), None, ""
                    alt_min_dist = float('inf')
                    for seg in all_segments:
                        d = _seg_dist(tx, ty, seg)
                        if d < min_dist:
                            min_dist, best_layer, best_system = d, seg["layer"], layer_systems[seg["layer"]]
                    if best_layer is None or min_dist > max_distance_du:
                        continue
                    if best_system:
                        for seg in all_segments:
                            if layer_systems[seg["layer"]] and layer_systems[seg["layer"]] != best_system:
                                d = _seg_dist(tx, ty, seg)
                                if d < alt_min_dist:
                                    alt_min_dist = d
                        if alt_min_dist <= min_dist * _AMBIGUITY_RATIO:
                            ambiguous_labels.append(t["text"])
                            continue
                    bucket = layer_labels.setdefault(best_layer, {})
                    bucket[t["text"]] = bucket.get(t["text"], 0) + 1

        fittings_by_layer = cad_geometry.detect_fittings(
            all_segments, stock_length=stock_length_du, tolerance=joint_tolerance_du)

        rows = []
        stt = 1
        for (b_name, attr_str), count in sorted(block_counts.items(), key=lambda x: -x[1]):
            ghi_chu = attr_str if attr_str else ""
            # Đơn vị tra theo loại Block (đèn/ổ cắm/đầu phun... = "Cái", cụm thiết bị
            # trọn bộ như FCU/bơm = "Bộ") qua cad_standards.BLOCK_STANDARD, khớp thói
            # quen hồ sơ thầu VN — "Bộ" chỉ còn là dự phòng khi không nhận diện được
            # Block (trước đây gán cứng "Bộ" cho mọi Block bất kể loại).
            block_key = cad_standards.match_block(b_name)
            unit = cad_standards.BLOCK_STANDARD[block_key]["unit"] if block_key else "Bộ"
            rows.append({"STT": stt, "Hạng mục": b_name, "Đơn vị": unit, "Khối lượng": count, "Ghi chú": ghi_chu})
            stt += 1

        for layer, length in sorted(layer_lengths.items(), key=lambda x: -x[1]):
            if length <= 0:
                continue
            label = layer
            note = f"Layer: {layer}"
            if layer in layer_labels:
                best_label = max(layer_labels[layer].items(), key=lambda x: x[1])[0]
                label = best_label
            # `length` (và mọi seg["length"] khác trong hàm này) là đơn vị bản vẽ gốc,
            # mặc định coi là mm (khớp DEFAULT_PIPE_STOCK_LENGTH = 6000mm = 6m ở
            # cad_geometry.py). Cột "Khối lượng" ở đây khai đơn vị "m" nên PHẢI đổi
            # mm -> m trước khi ghi ra — thiếu bước này từng khiến khối lượng xuất ra
            # sai lệch gấp 1000 lần (bug đã sửa, xem test_qs_tools_units.py).
            length_m = dwg_unit.length_m(length)
            length_with_wastage_m = length_m * (1 + wastage_percent / 100.0)
            if wastage_percent > 0:
                note += f" (đã cộng {wastage_percent:.0f}% hao hụt vật tư)"
            rows.append({"STT": stt, "Hạng mục": label, "Đơn vị": "m",
                        "Khối lượng": round(length_with_wastage_m, 2), "Ghi chú": note})
            stt += 1

            fittings = fittings_by_layer.get(layer, {})
            fitting_labels = {"co": "Co (elbow)", "te": "Tê (nhánh rẽ)", "mang_song": "Măng sông (nối ống)"}
            for key, qty in fittings.items():
                if qty <= 0:
                    continue
                rows.append({
                    "STT": stt, "Hạng mục": f"{fitting_labels[key]} - {label}", "Đơn vị": "Cái",
                    "Khối lượng": qty,
                    "Ghi chú": f"Suy từ hình học tuyến (Layer: {layer}) — cần đối chiếu bản vẽ chi tiết",
                })
                stt += 1

        if not rows:
            return "Không tìm thấy Block hoặc tuyến ống/dây nào trong bản vẽ để bóc khối lượng."

        out_path = output_excel_path if output_excel_path.endswith('.xlsx') else output_excel_path + '.xlsx'
        out_safe_path = resolve_safe_path(out_path)
        dir_name = os.path.dirname(out_safe_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        df = pd.DataFrame(rows)
        df.to_excel(out_safe_path, index=False)

        summary = ""
        if insunits_warning:
            summary += insunits_warning + "\n\n"
        if off_frozen_layer_hits:
            summary += (
                f"[CẢNH BÁO] {sum(off_frozen_layer_hits.values())} đối tượng thuộc "
                f"{len(off_frozen_layer_hits)} Layer đang bị TẮT (off) hoặc ĐÓNG BĂNG (frozen) "
                f"vẫn được TÍNH VÀO khối lượng bên dưới: "
                + ", ".join(sorted(off_frozen_layer_hits.keys()))
                + ". Layer tắt/đóng băng thường là nội dung tham chiếu cũ không còn hiệu lực — "
                "xác nhận lại với khách có nên loại các Layer này khỏi dự toán hay không.\n\n"
            )
        if ambiguous_labels:
            sample = ", ".join(f"'{x}'" for x in ambiguous_labels[:5])
            summary += (
                f"[CẢNH BÁO] {len(ambiguous_labels)} ghi chú kích thước KHÔNG được gán vào tuyến "
                f"nào vì nằm gần ranh giới giữa 2 hệ khác nhau (VD: {sample}"
                + (", ..." if len(ambiguous_labels) > 5 else "") +
                ") — cần đối chiếu bản vẽ thủ công để tránh gán nhầm hệ, thay vì đoán bừa "
                "theo layer gần nhất.\n\n"
            )
        if duplicate_length_by_layer:
            total_dup_m = dwg_unit.length_m(sum(duplicate_length_by_layer.values()))
            summary += (
                f"[CẢNH BÁO NGHIÊM TRỌNG] Phát hiện hình học TRÙNG LẶP (overkill) ước tính "
                f"~{total_dup_m:.1f} m bị cộng dồn thừa vào khối lượng, tại các Layer: "
                + ", ".join(sorted(duplicate_length_by_layer.keys())) + ". "
                "Nên chạy `optimize_cad_drawing` để dọn trùng lặp rồi bóc lại khối lượng trước "
                "khi dùng bảng dự toán này.\n\n"
            )
        if xref_overlap_length > 0:
            total_xref_dup_m = dwg_unit.length_m(xref_overlap_length)
            summary += (
                f"[CẢNH BÁO NGHIÊM TRỌNG] Phát hiện ~{total_xref_dup_m:.1f} m hình học TRÙNG VỊ TRÍ "
                f"giữa nội dung XREF và hình học VẼ TRỰC TIẾP trong bản vẽ chính (khác layer nên "
                f"KHÔNG bị bắt bởi cảnh báo overkill ở trên), tại các Layer liên quan: "
                + ", ".join(sorted(xref_overlap_layers)) + ". "
                "Thường do khách VẼ LẠI (trace) nội dung xref vào bản vẽ chính khi gộp thủ công "
                "nhiều nguồn — kiểm tra kỹ trước khi dùng khối lượng này, có thể đang bị TÍNH ĐÔI.\n\n"
            )

        summary += (
            f"BÓC TÁCH KHỐI LƯỢNG TỰ ĐỘNG THÀNH CÔNG (offline, không cần LLM tính toán).\n"
            f"- Đơn vị bản vẽ: {dwg_unit.name} ({dwg_unit.source}); mọi chiều dài đã quy đổi ra mét "
            f"theo hệ số 1 đơn vị = {dwg_unit.mm_per_unit:g} mm.\n"
            f"- Đã làm sạch bản vẽ (Audit sửa {audit_fixes} lỗi).\n"
            f"- Tổng {len(block_counts)} loại Block (thiết bị) và {len([lyr for lyr, v in layer_lengths.items() if v > 0])} tuyến ống/dây có khối lượng.\n"
            f"- Khối lượng ống/dây đã cộng {wastage_percent:.0f}% hao hụt vật tư theo định mức.\n"
            f"- Đã ghi {len(rows)} dòng dự toán ra file Excel tại: {out_path}\n"
        )
        if exploded_blocks:
            total_inner_m = dwg_unit.length_m(sum(exploded_blocks.values()))
            summary += (
                f"- Đã cộng thêm ~{total_inner_m:.1f} m tuyến ống/dây vẽ BÊN TRONG Block "
                f"({', '.join(sorted(exploded_blocks))}) — phần này nằm trong ruột block nên "
                f"trước đây bị bóc thiếu hoàn toàn.\n"
            )
        if anonymous_blocks:
            summary += (
                f"[CẢNH BÁO] {sum(anonymous_blocks.values())} lần chèn thuộc "
                f"{len(anonymous_blocks)} Block ẨN DANH ({', '.join(sorted(anonymous_blocks))}) — "
                f"đây là biến thể của Block động (dynamic block) mà bản vẽ không lưu kèm tên gốc. "
                f"Các dòng này đang mang tên kỹ thuật vô nghĩa và có thể là cùng MỘT chủng loại "
                f"thiết bị bị tách thành nhiều dòng; cần mở bản vẽ đối chiếu và đặt lại tên hạng "
                f"mục trước khi gửi dự toán.\n"
            )
        if nested_block_hits:
            summary += (
                f"- Đã đếm thêm {sum(nested_block_hits.values())} thiết bị LỒNG bên trong Block "
                f"khác ({', '.join(sorted(nested_block_hits))}).\n"
            )
        for note in load_notes:
            summary += f"- {note}\n"
        if scaled_blocks:
            summary += f"\nCẢNH BÁO: {len(scaled_blocks)} loại Block bị insert LỆCH TỶ LỆ (kích thước thực tế khác chuẩn):\n"
            for (b_name, xs, ys), count in sorted(scaled_blocks.items(), key=lambda x: -x[1])[:10]:
                summary += f"  - {b_name}: scale ({xs}, {ys}) x {count} lần chèn — kiểm tra lại với khách trước khi lập dự toán.\n"
        preview_rows = rows[:15]
        summary += "\nXem trước:\n"
        for r in preview_rows:
            summary += f"  {r['STT']}. {r['Hạng mục']} — {r['Khối lượng']} {r['Đơn vị']}\n"
        if len(rows) > 15:
            summary += f"  ... và {len(rows) - 15} dòng khác trong file Excel.\n"
        return summary
    except Exception as e:
        return f"Lỗi bóc tách khối lượng tự động: {e}"


@tool
def calc_support_hangers(pipe_or_duct_length_m: float, spacing_m: float = 2.0,
                         support_type: str = "ong", riser_count: int = 0) -> str:
    """
    Tính số lượng giá đỡ/ty treo (support/hanger) cho một tuyến ống hoặc ống gió theo chiều
    dài — hạng mục vật tư phụ trợ thường bị bỏ sót trong BOQ khi chỉ bóc khối lượng đường ống
    chính (`auto_quantity_takeoff` không tự suy ra số lượng giá đỡ vì phụ thuộc khoảng cách
    lắp đặt theo quy phạm, không thể đếm trực tiếp từ hình học bản vẽ).
    Tham số:
    - pipe_or_duct_length_m: Tổng chiều dài tuyến ống/ống gió cần treo đỡ (m).
    - spacing_m: Khoảng cách tối đa giữa các giá đỡ (m). Mặc định 2.0m — tham khảo cho ống
      kim loại cỡ trung bình; ống nhựa/ống nhỏ cần khoảng cách gần hơn (1.0-1.5m), ống gió
      lớn có thể xa hơn (2.5-3m) — hiệu chỉnh theo quy phạm/catalog nhà sản xuất cụ thể.
    - support_type: 'ong' (ống nước/gas) hoặc 'ong_gio' (ống gió) — chỉ ảnh hưởng nhãn báo cáo.
    - riser_count: Số điểm ống đứng (riser) trên tuyến — mỗi điểm cần thêm 1 giá đỡ cố định
      (clamp) tại mỗi tầng đi qua, cộng thêm vào số giá đỡ ngang.
    """
    logger.info(f"Calculating Support Hangers: L={pipe_or_duct_length_m}m, spacing={spacing_m}m")
    try:
        if pipe_or_duct_length_m <= 0:
            return "Lỗi: Chiều dài tuyến phải lớn hơn 0."
        if spacing_m <= 0:
            return "Lỗi: Khoảng cách giá đỡ phải lớn hơn 0."

        qty_horizontal = math.ceil(pipe_or_duct_length_m / spacing_m) + 1
        qty_riser = riser_count if riser_count > 0 else 0
        qty_total = qty_horizontal + qty_riser

        label = "ống gió" if (support_type or "ong").lower().strip() == "ong_gio" else "ống"

        report = [
            f"Tính giá đỡ/ty treo cho tuyến {label} dài {pipe_or_duct_length_m} m "
            f"(khoảng cách tối đa {spacing_m} m/giá đỡ):",
            f"- Giá đỡ/ty treo ngang theo chiều dài: {qty_horizontal} bộ",
        ]
        if qty_riser:
            report.append(f"- Giá đỡ cố định (clamp) tại điểm ống đứng: {qty_riser} bộ")
        report += [
            f"=> TỔNG SỐ GIÁ ĐỠ/TY TREO: {qty_total} bộ",
            "- Khoảng cách mặc định chỉ mang tính tham khảo — PHẢI đối chiếu quy phạm lắp đặt/"
            "catalog nhà sản xuất theo cỡ ống/gió thực tế của tuyến trước khi đưa vào BOQ chính "
            "thức (ống cỡ lớn/ống gió nặng cần giá đỡ dày hơn khoảng cách mặc định).",
            "- Đây là hạng mục vật tư phụ trợ dễ bị bỏ sót khi lập BOQ nhanh chỉ từ khối lượng "
            "đường ống chính — nên cộng thêm dòng riêng cho giá đỡ/ty treo vào bảng dự toán.",
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính giá đỡ/ty treo: {e}"


def build_revit_boq_excel(elements: list[dict], output_excel_path: str,
                           wastage_percent: float = 5.0) -> str | None:
    """Lập bảng khối lượng (BOQ) thật từ payload cấu kiện Revit (xem
    `revit/MEPAgents.extension/.../Auto BOQ.pushbutton/script.py::get_mep_elements`).

    Trước đây `/api/v1/revit/analyze` chỉ ĐẾM số cấu kiện rồi trả một câu thông báo
    tĩnh — hoàn toàn không tương đương với `auto_quantity_takeoff` (luồng AutoCAD), dù
    cùng mục đích bóc khối lượng. Hàm này áp DÙNG CHUNG quy ước đơn vị/hao hụt với
    `auto_quantity_takeoff`: cấu kiện có `length_mm` (Ống gió/Ống nước — đã được plugin
    Revit quy đổi feet -> mm) được cộng dồn theo (category, name), đổi mm -> m, cộng
    `wastage_percent`% hao hụt, làm tròn 2 chữ số thập phân; cấu kiện không có chiều dài
    (phụ kiện, thiết bị cơ điện) được đếm theo "Cái". Nhờ vậy kết quả từ Revit và AutoCAD
    dùng cùng đơn vị/quy tắc, có thể đối chiếu trực tiếp thay vì là hai luồng lệch nhau.

    Trả về đường dẫn file Excel đã ghi, hoặc None nếu không có cấu kiện nào để bóc.
    """
    length_mm_by_key: dict[tuple[str, str], float] = {}
    count_by_key: dict[tuple[str, str], int] = {}
    for el in elements:
        category = el.get("category") or "Unknown"
        name = el.get("name") or category
        key = (category, name)
        length_mm = el.get("length_mm")
        if length_mm is not None:
            length_mm_by_key[key] = length_mm_by_key.get(key, 0.0) + float(length_mm)
        else:
            count_by_key[key] = count_by_key.get(key, 0) + 1

    rows = []
    stt = 1
    for (category, name), length_mm in sorted(length_mm_by_key.items(), key=lambda x: -x[1]):
        length_with_wastage_m = (length_mm / 1000.0) * (1 + wastage_percent / 100.0)
        note = f"Category: {category}"
        if wastage_percent > 0:
            note += f" (đã cộng {wastage_percent:.0f}% hao hụt vật tư)"
        rows.append({"STT": stt, "Hạng mục": name, "Đơn vị": "m",
                     "Khối lượng": round(length_with_wastage_m, 2), "Ghi chú": note})
        stt += 1

    for (category, name), qty in sorted(count_by_key.items(), key=lambda x: -x[1]):
        rows.append({"STT": stt, "Hạng mục": name, "Đơn vị": "Cái", "Khối lượng": qty,
                     "Ghi chú": f"Category: {category}"})
        stt += 1

    if not rows:
        return None

    dir_name = os.path.dirname(output_excel_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    pd.DataFrame(rows).to_excel(output_excel_path, index=False, sheet_name="BOQ Revit")
    return output_excel_path


