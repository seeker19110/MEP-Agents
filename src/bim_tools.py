"""Kiểm tra xung đột (Clash Detection) giữa các hệ MEPF trên bản vẽ DXF/DWG.

Prompt của `bim_agent_node` từ trước tới nay vẫn tuyên bố BIM Agent "kiểm tra xung đột",
nhưng KHÔNG hề có tool nào làm việc đó — nghĩa là agent chỉ có thể nói suông. Module này
bù đúng khoảng trống ấy bằng thuật toán hình học thuần (giao điểm đoạn thẳng, cung được
rời rạc hóa), không cần LLM suy luận, nên chạy tốt cả với model yếu/offline.

Phạm vi: chồng nhiều bản vẽ MEPF mặt bằng vốn KHÔNG có cao độ Z thật (bản vẽ 2D thuần)
là trường hợp phổ biến nhất — tool vẫn đọc cao độ Z nếu entity có khai báo (LINE 3D,
polyline có `elevation`) và dùng để LOẠI những giao điểm rõ ràng cách nhau đủ xa theo
chiều đứng (không phải xung đột thật). Khi cả hai tuyến đều không khai báo Z (Z=0 mặc
định), tool trung thực báo "chưa rõ cao độ, cần kiểm tra thủ công" thay vì kết luận thay
kỹ sư — đây là giới hạn thật của dữ liệu 2D, không phải lỗi của tool.
"""
import logging
import math
import os

import pandas as pd
from langchain_core.tools import tool

from src import cad_geometry
from src import cad_loader
from src import cad_standards
from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)

# Nhận diện hệ kỹ thuật từ tên Layer. Khớp theo thứ tự, từ khóa đặc thù đứng trước.
# CHỈ dùng làm fallback khi `cad_standards.match_layer` (nguồn sự thật duy nhất, dùng
# chung với `standardize_cad_drawing`) không nhận diện được layer — ví dụ layer đặt tên
# tự do, chưa từng qua chuẩn hóa, không khớp bất kỳ keyword nào trong LAYER_STANDARD.
# Trước đây module này tự giữ một bảng từ khóa riêng hoàn toàn tách biệt khỏi
# cad_standards.py: hai nguồn phân loại "hệ MEPF theo layer" độc lập, dễ lệch nhau khi
# chỉ một bên được cập nhật (ví dụ thêm layer chuẩn mới vào LAYER_STANDARD mà quên thêm
# keyword tương ứng ở đây). Gộp về một nguồn chính giải quyết rủi ro đó.
SYSTEM_KEYWORDS = [
    ("PCCC", ("pccc", "fire", "sprinkler", "ff_", "-ff", "chua chay", "hydrant")),
    ("HVAC", ("hvac", "duct", "gio", "air", "me_", "-me", "chiller", "fcu", "refrigerant")),
    ("Điện", ("elec", "dien", "power", "cable", "tray", "el_", "-el", "light", "lighting")),
    ("Cấp thoát nước", ("plumb", "nuoc", "water", "drain", "waste", "pl_", "-pl", "upvc", "ppr")),
]

# `cad_standards.LAYER_STANDARD[...]["discipline"]` dùng tên tiếng Anh (Mechanical,
# Electrical, Plumbing, Firefighting, General); phần còn lại của module này (và
# `qs_tools.auto_quantity_takeoff`) dùng nhãn tiếng Việt — quy đổi 1-1 tại đây.
_DISCIPLINE_TO_VN = {
    "Mechanical": "HVAC",
    "Electrical": "Điện",
    "Plumbing": "Cấp thoát nước",
    "Firefighting": "PCCC",
    "General": "",
}

# Khoảng cách đứng tối thiểu (đơn vị bản vẽ, thường mm) để coi hai tuyến CÁCH XA nhau
# theo cao độ là không xung đột thật, dù cắt nhau trên mặt bằng. Mặc định 150mm — nhỏ
# hơn khe hở lắp đặt tối thiểu giữa hai tuyến MEPF trong thực tế.
DEFAULT_MIN_VERTICAL_CLEARANCE = 150.0

# Bán kính tìm ghi chú kích thước (Ø110, 600x400...) gần nhất quanh MỘT ENTITY để suy ra
# bề dày ống/gió — cùng giá trị mặc định với auto_quantity_takeoff (khớp thói quen vẽ ghi
# chú gần tuyến của người dùng thật).
DEFAULT_LABEL_SEARCH_RADIUS = 2000.0


# Tiền tố layer đã CHUẨN HÓA theo quy ước nội bộ (`src/cad_standards.py`, áp dụng bởi
# `standardize_cad_drawing`): `<HỆ>-<NHÓM>...`. Kiểm tra tiền tố này TRƯỚC bảng từ khóa vì
# các mã layer chuẩn (VD `M-SAD`, `M-PIPE-REF`, `E-CABLETRAY`, `F-SPRINKLER`) không chắc
# chứa các từ khóa tiếng Anh/Việt chung chung bên dưới (VD `M-SAD` không có "duct"/"gio"/
# "hvac") — thiếu bước này khiến bản vẽ ĐÃ chuẩn hóa lại KHÔNG được nhận diện hệ đúng,
# vô hiệu hóa `detect_clashes`/`check_pipe_connectivity` ngay sau khi vừa chuẩn hóa xong.
_PREFIX_SYSTEM = {"M": "HVAC", "E": "Điện", "P": "Cấp thoát nước", "F": "PCCC"}


def classify_layer_system(layer_name: str) -> str:
    """Suy ra hệ kỹ thuật ('HVAC', 'Điện', ...) từ tên layer; '' nếu không nhận ra.

    Nguồn sự thật chính là `cad_standards.match_layer` (cùng bảng `LAYER_STANDARD`
    dùng để chuẩn hóa layer) — đảm bảo layer đã chuẩn hóa hoặc gần khớp tên chuẩn luôn
    được gán đúng hệ, khớp 100% với kết quả của `standardize_cad_drawing`. Chỉ khi
    `cad_standards` không nhận diện được (layer đặt tên tự do, chưa chuẩn hóa) mới rơi
    xuống bảng tiền tố/từ khóa cục bộ bên dưới làm phương án dự phòng.
    """
    standard_key = cad_standards.match_layer(layer_name)
    if standard_key:
        discipline = cad_standards.LAYER_STANDARD[standard_key]["discipline"]
        vn = _DISCIPLINE_TO_VN.get(discipline, "")
        if vn:
            return vn

    name = (layer_name or "").lower()

    prefix = (layer_name or "").split("-", 1)[0].strip().upper()
    if prefix in _PREFIX_SYSTEM:
        return _PREFIX_SYSTEM[prefix]

    for system, keywords in SYSTEM_KEYWORDS:
        if any(kw in name for kw in keywords):
            return system
    return ""


def _segment_intersection(a1, a2, b1, b2):
    """Giao điểm của hai đoạn thẳng 2D, hoặc None nếu không cắt nhau.

    Dùng tham số hóa chuẩn: p + t*r và q + u*s, xung đột thật sự khi 0<=t<=1 và 0<=u<=1.
    Hai đoạn song song/trùng nhau được coi là KHÔNG xung đột (chúng chạy dọc nhau, không
    cắt qua nhau) để tránh báo động giả tràn lan trên các tuyến đi song song.
    """
    (x1, y1), (x2, y2) = a1, a2
    (x3, y3), (x4, y4) = b1, b2
    rx, ry = x2 - x1, y2 - y1
    sx, sy = x4 - x3, y4 - y3
    denom = rx * sy - ry * sx
    if abs(denom) < 1e-12:
        return None
    qpx, qpy = x3 - x1, y3 - y1
    t = (qpx * sy - qpy * sx) / denom
    u = (qpx * ry - qpy * rx) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return (x1 + t * rx, y1 + t * ry)
    return None


def _z_at(z1, z2, t):
    return z1 + (z2 - z1) * t


def _segment_z_range(a1, a2, t):
    """Xấp xỉ cao độ tại điểm giao (nội suy tuyến tính theo tham số t dọc đoạn thẳng)."""
    return _z_at(a1[2], a2[2], t)


def _point_seg_closest(px, py, ax, ay, bx, by):
    """Điểm gần nhất trên đoạn AB tới điểm P: (khoảng cách, t dọc AB, x, y)."""
    l2 = (bx - ax) ** 2 + (by - ay) ** 2
    if l2 < 1e-12:
        return math.hypot(px - ax, py - ay), 0.0, ax, ay
    t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / l2))
    cx, cy = ax + t * (bx - ax), ay + t * (by - ay)
    return math.hypot(px - cx, py - cy), t, cx, cy


def _closest_approach(a1, a2, b1, b2):
    """Khoảng cách nhỏ nhất giữa hai đoạn thẳng 2D KHÔNG cắt nhau, cùng tham số (ta, tb)
    tại điểm gần nhau nhất trên mỗi đoạn (dùng để nội suy Z). Khoảng cách nhỏ nhất giữa
    hai đoạn không cắt nhau luôn đạt được tại một trong 4 phép chiếu đầu-mút-lên-đoạn-kia."""
    (ax1, ay1), (ax2, ay2) = a1, a2
    (bx1, by1), (bx2, by2) = b1, b2
    d1, tb1, _, _ = _point_seg_closest(ax1, ay1, bx1, by1, bx2, by2)  # a1 chiếu lên b
    d2, tb2, _, _ = _point_seg_closest(ax2, ay2, bx1, by1, bx2, by2)  # a2 chiếu lên b
    d3, ta3, _, _ = _point_seg_closest(bx1, by1, ax1, ay1, ax2, ay2)  # b1 chiếu lên a
    d4, ta4, _, _ = _point_seg_closest(bx2, by2, ax1, ay1, ax2, ay2)  # b2 chiếu lên a
    candidates = [(d1, 0.0, tb1), (d2, 1.0, tb2), (d3, ta3, 0.0), (d4, ta4, 1.0)]
    distance, ta, tb = min(candidates, key=lambda c: c[0])
    return distance, ta, tb


def _extract_labels(msp):
    """Ghi chú kích thước (TEXT/MTEXT) có chứa số đo (Ø110, 600x400...) kèm vị trí, dùng
    để suy ra bề dày ống/gió cho từng entity gần đó."""
    labels = []
    for entity in msp:
        dxftype = entity.dxftype()
        if dxftype == "TEXT":
            txt, pos = entity.dxf.text, entity.dxf.insert
        elif dxftype == "MTEXT":
            txt, pos = entity.text, entity.dxf.insert
        else:
            continue
        half_width = cad_geometry.parse_nominal_half_width(txt or "")
        if half_width:
            labels.append((pos.x, pos.y, half_width))
    return labels


def _nearest_label_half_width(labels, x, y, radius):
    best_half_width, best_dist = None, radius
    for lx, ly, half_width in labels:
        d = math.hypot(lx - x, ly - y)
        if d <= best_dist:
            best_dist = d
            best_half_width = half_width
    return best_half_width


def _extract_segments(msp, labels=None, label_radius=DEFAULT_LABEL_SEARCH_RADIUS):
    """Mọi đoạn (kể cả cung đã rời rạc hóa) của bản vẽ kèm layer, hệ kỹ thuật, Z, và bán
    kính/nửa bề rộng danh nghĩa suy từ ghi chú kích thước gần nhất (None nếu không có ghi
    chú nào đủ gần — khi đó chỉ xét đường tâm, không đoán bề dày)."""
    segments = []
    for entity in msp:
        layer = entity.dxf.layer
        system = classify_layer_system(layer)
        if not system:
            continue
        points = cad_geometry.entity_points_3d(entity)
        if len(points) < 2:
            continue
        half_width = None
        if labels:
            mx = sum(p[0] for p in points) / len(points)
            my = sum(p[1] for p in points) / len(points)
            half_width = _nearest_label_half_width(labels, mx, my, label_radius)
        for i in range(1, len(points)):
            segments.append((system, layer, points[i - 1], points[i], half_width))
    return segments


def _has_declared_elevation(points_3d) -> bool:
    """Bản vẽ có thật sự khai báo cao độ Z hay không (không chỉ toàn số 0 mặc định)."""
    return any(abs(p[2]) > 1e-9 for p in points_3d)


@tool
def detect_clashes(file_path: str, output_excel_path: str = "bao_cao_xung_dot.xlsx",
                   min_vertical_clearance: float = DEFAULT_MIN_VERTICAL_CLEARANCE,
                   label_search_radius: float = DEFAULT_LABEL_SEARCH_RADIUS) -> str:
    """Kiểm tra XUNG ĐỘT (clash detection) giữa các hệ MEPF trên bản vẽ CAD (.dxf/.dwg).

    Quét toàn bộ tuyến ống/gió/cáp (kể cả đoạn cong ARC/bulge), phân loại theo hệ dựa
    trên tên Layer (HVAC, Điện, Cấp thoát nước, PCCC), rồi tìm xung đột giữa hai hệ KHÁC
    NHAU theo HAI cách:
    1. Đường tâm cắt nhau trực tiếp trên mặt bằng (như trước đây).
    2. BỀ DÀY ống/gió chồng lấn dù đường tâm KHÔNG cắt nhau — VD hai tuyến chạy song
       song sát nhau, đường tâm không giao nhau nhưng đường kính/kích thước thật khiến
       chúng va chạm vật lý. Bán kính/nửa bề rộng mỗi tuyến được suy từ ghi chú kích
       thước gần nhất trên bản vẽ (TEXT/MTEXT dạng "Ø110", "DN100", "600x400", trong
       phạm vi `label_search_radius`); tuyến không có ghi chú kích thước gần đó sẽ CHỈ
       được xét theo đường tâm (không đoán bừa kích thước để tránh báo động giả).
    Xuất danh sách tọa độ xung đột kèm loại (cắt trực tiếp / chồng lấn theo bề dày) ra
    file Excel. Nếu bản vẽ có khai báo cao độ Z thật (LINE 3D, polyline có `elevation`),
    tool dùng Z để LOẠI các điểm mà hai tuyến thực ra cách nhau đủ xa theo chiều đứng —
    không phải xung đột thật. Thuần hình học, không cần LLM suy luận. Dùng khi khách
    hàng yêu cầu "kiểm tra xung đột", "clash", "va chạm giữa các hệ".
    """
    logger.info("Detecting clashes: %s", file_path)
    try:
        doc, load_notes = cad_loader.load_drawing(file_path)
        msp = doc.modelspace()
        labels = _extract_labels(msp)
        segments = _extract_segments(msp, labels=labels, label_radius=label_search_radius)

        base_dir = os.path.dirname(resolve_safe_path(file_path))
        xref_segs_raw, xref_notes = cad_loader.resolve_xref_segments(
            doc, base_dir,
            lambda space: [
                {"layer": layer, "start": s, "end": e, "length": 0, "is_arc": False}
                for entity in list(space)
                for (layer, s, e) in (
                    (entity.dxf.layer, points[i - 1], points[i])
                    for points in [cad_geometry.entity_points_3d(entity)]
                    for i in range(1, len(points))
                ) if classify_layer_system(layer)
            ],
        )
        has_xref_segments = False
        for seg in xref_segs_raw:
            system = classify_layer_system(seg["layer"])
            if system:
                # Ghi chú kích thước trong file XREF chưa được đọc — tuyến từ XREF luôn
                # có half_width=None (chỉ xét đường tâm), không đoán bừa qua ranh giới file.
                segments.append((system, seg["layer"], seg["start"], seg["end"], None))
                has_xref_segments = True
        load_notes.extend(xref_notes)

        if not segments:
            return ("Không tìm thấy tuyến nào thuộc các hệ MEPF trong bản vẽ (dựa trên tên Layer). "
                    "Hãy đặt tên Layer theo quy ước có chứa từ khóa hệ (VD: 'HVAC_DUCT', 'ELEC_TRAY', "
                    "'PCCC_SPRINKLER', 'PLUMB_WASTE') rồi kiểm tra lại.")

        has_any_elevation = any(_has_declared_elevation([a, b]) for _, _, a, b, _ in segments)
        segments_missing_size = sum(1 for *_, hw in segments if hw is None)

        clashes = []
        seen = set()
        skipped_by_elevation = 0
        thickness_clash_count = 0
        for i in range(len(segments)):
            sys_a, layer_a, a1, a2, hw_a = segments[i]
            for j in range(i + 1, len(segments)):
                sys_b, layer_b, b1, b2, hw_b = segments[j]
                if sys_a == sys_b:
                    continue  # xung đột trong cùng một hệ là chuyện bình thường (nhánh rẽ)

                point = _segment_intersection((a1[0], a1[1]), (a2[0], a2[1]), (b1[0], b1[1]), (b2[0], b2[1]))
                clash_type = "Cắt trực tiếp (đường tâm)"
                overlap_note = ""

                if point is None:
                    # Không cắt tâm — vẫn có thể va chạm vật lý nếu biết bề dày cả hai tuyến.
                    if hw_a is None or hw_b is None:
                        continue
                    distance, ta, tb = _closest_approach((a1[0], a1[1]), (a2[0], a2[1]), (b1[0], b1[1]), (b2[0], b2[1]))
                    required = hw_a + hw_b
                    if distance >= required:
                        continue
                    thickness_clash_count += 1
                    clash_type = "Chồng lấn theo bề dày ống/gió"
                    overlap_note = (f" Đường tâm cách nhau {distance:.0f}mm, tổng bán kính/nửa bề rộng "
                                    f"{required:.0f}mm -> chồng lấn {required - distance:.0f}mm.")
                    px = a1[0] + ta * (a2[0] - a1[0])
                    py = a1[1] + ta * (a2[1] - a1[1])
                    point = (px, py)
                else:
                    l2a = (a2[0] - a1[0]) ** 2 + (a2[1] - a1[1]) ** 2
                    l2b = (b2[0] - b1[0]) ** 2 + (b2[1] - b1[1]) ** 2
                    ta = (((point[0] - a1[0]) * (a2[0] - a1[0]) + (point[1] - a1[1]) * (a2[1] - a1[1])) / l2a
                         if l2a > 0 else 0.0)
                    tb = (((point[0] - b1[0]) * (b2[0] - b1[0]) + (point[1] - b1[1]) * (b2[1] - b1[1])) / l2b
                         if l2b > 0 else 0.0)

                # Có khai báo Z thật thì dùng để loại điểm cách xa nhau theo chiều đứng.
                z_gap = None
                if has_any_elevation:
                    z_a = _segment_z_range(a1, a2, ta)
                    z_b = _segment_z_range(b1, b2, tb)
                    z_gap = abs(z_a - z_b)
                    if z_gap >= min_vertical_clearance:
                        skipped_by_elevation += 1
                        continue

                key = (round(point[0], 3), round(point[1], 3), tuple(sorted((sys_a, sys_b))), clash_type)
                if key in seen:
                    continue
                seen.add(key)
                muc_do = (f"Cách nhau {z_gap:.0f}mm theo cao độ — CẦN kiểm tra (dưới khe hở tối thiểu)."
                         if z_gap is not None else "Chưa rõ cao độ (bản vẽ không khai báo Z) — cần kiểm tra thủ công.")
                clashes.append({
                    "STT": len(clashes) + 1,
                    "Hệ 1": sys_a, "Layer 1": layer_a,
                    "Hệ 2": sys_b, "Layer 2": layer_b,
                    "Loại": clash_type,
                    "Tọa độ X": round(point[0], 2), "Tọa độ Y": round(point[1], 2),
                    "Mức độ": muc_do + overlap_note,
                })

        if not clashes:
            systems = sorted({s for s, _, _, _, _ in segments})
            extra = f" ({skipped_by_elevation} giao điểm mặt bằng đã loại vì cách xa theo cao độ.)" if skipped_by_elevation else ""
            return (f"KHÔNG phát hiện xung đột giữa các hệ. "
                    f"Đã quét {len(segments)} đoạn tuyến thuộc {len(systems)} hệ: {', '.join(systems)}.{extra}")

        out_path = output_excel_path if output_excel_path.endswith(".xlsx") else output_excel_path + ".xlsx"
        out_safe = resolve_safe_path(out_path)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        pd.DataFrame(clashes).to_excel(out_safe, index=False)

        by_pair = {}
        for c in clashes:
            pair = f"{c['Hệ 1']} x {c['Hệ 2']}"
            by_pair[pair] = by_pair.get(pair, 0) + 1

        report = [
            f"PHÁT HIỆN {len(clashes)} ĐIỂM XUNG ĐỘT giữa các hệ MEPF (đã ghi file: {out_path}).",
            f"- Đã quét {len(segments)} đoạn tuyến.",
        ]
        for note in load_notes:
            report.append(f"- {note}")
        if thickness_clash_count:
            report.append(f"- Trong đó {thickness_clash_count} điểm là CHỒNG LẤN THEO BỀ DÀY ống/gió "
                          f"(đường tâm không cắt nhau nhưng kích thước thật khiến chúng va chạm vật lý) — "
                          f"suy từ ghi chú kích thước gần tuyến (Ø, DN, WxH) trong bán kính {label_search_radius:.0f}mm.")
        if segments_missing_size:
            report.append(f"- {segments_missing_size} đoạn tuyến KHÔNG có ghi chú kích thước gần đó nên "
                          f"chỉ được xét theo đường tâm (chưa kiểm tra được va chạm do bề dày) — "
                          f"cần kỹ sư đối chiếu bản vẽ chi tiết cho các đoạn này.")
        if has_xref_segments:
            report.append("- Tuyến gộp từ XREF chỉ xét theo đường tâm (chưa đọc được ghi chú kích thước "
                          "nằm trong file tham chiếu ngoài).")
        if has_any_elevation:
            report.append(f"- Bản vẽ có khai báo cao độ Z: đã loại {skipped_by_elevation} giao điểm mặt bằng "
                          f"cách nhau >= {min_vertical_clearance:.0f}mm theo chiều đứng (không phải xung đột thật).")
        else:
            report.append("- Bản vẽ KHÔNG khai báo cao độ Z (thuần 2D) — mọi giao điểm dưới đây "
                          "đều cần kỹ sư đối chiếu cao độ lắp đặt thủ công.")
        report.append("- Thống kê theo cặp hệ:")
        for pair, count in sorted(by_pair.items(), key=lambda x: -x[1]):
            report.append(f"  + {pair}: {count} điểm")
        report.append("- Chi tiết 10 điểm đầu:")
        for c in clashes[:10]:
            report.append(f"  {c['STT']}. [{c['Loại']}] {c['Hệ 1']} ({c['Layer 1']}) x {c['Hệ 2']} ({c['Layer 2']}) "
                          f"tại (X={c['Tọa độ X']}, Y={c['Tọa độ Y']}) — {c['Mức độ']}")
        if len(clashes) > 10:
            report.append(f"  ... và {len(clashes) - 10} điểm khác trong file Excel.")
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi kiểm tra xung đột: {e}"


@tool
def check_pipe_connectivity(file_path: str, output_excel_path: str = "bao_cao_ho_ket_noi.xlsx",
                            label_search_radius: float = DEFAULT_LABEL_SEARCH_RADIUS) -> str:
    """Phát hiện các ĐẦU ỐNG/GIÓ/CÁP BỊ HỞ (không kết nối) trên bản vẽ CAD (.dxf/.dwg).

    Với mỗi hệ MEPF (HVAC, Điện, Cấp thoát nước, PCCC) riêng biệt, dựng đồ thị topology từ
    toàn bộ đoạn tuyến (kể cả cung đã rời rạc hóa) rồi tìm các nút chỉ có ĐÚNG 1 đoạn nối
    vào (bậc = 1) — đây là đầu tuyến hở: có thể là điểm đấu nối vào thiết bị hợp lệ (miệng
    gió, van, đầu phun) HOẶC lỗi vẽ thiếu đoạn nối/đứt tuyến. Tool không tự phân biệt được
    hai trường hợp này (không có dữ liệu thiết bị 3D thật), nên xuất toàn bộ đầu hở để kỹ
    sư đối chiếu bằng mắt — không kết luận thay. Dùng khi khách yêu cầu "kiểm tra kết nối
    đường ống", "tuyến có bị đứt/hở không", "đường ống mồ côi".
    """
    logger.info("Checking pipe connectivity: %s", file_path)
    try:
        doc, load_notes = cad_loader.load_drawing(file_path)
        msp = doc.modelspace()
        labels = _extract_labels(msp)
        segments = _extract_segments(msp, labels=labels, label_radius=label_search_radius)

        if not segments:
            return ("Không tìm thấy tuyến nào thuộc các hệ MEPF trong bản vẽ (dựa trên tên Layer). "
                    "Hãy đặt tên Layer theo quy ước có chứa từ khóa hệ (VD: 'HVAC_DUCT', 'ELEC_TRAY', "
                    "'PCCC_SPRINKLER', 'PLUMB_WASTE') rồi kiểm tra lại.")

        by_system: dict[str, list] = {}
        for system, layer, a, b, _hw in segments:
            by_system.setdefault(system, []).append({
                "start": a, "end": b, "length": math.dist(a[:2], b[:2]), "layer": layer,
            })

        open_ends = []
        for system, segs in by_system.items():
            layer_by_point = {}
            for seg in segs:
                p1 = (round(seg["start"][0], 1), round(seg["start"][1], 1), round(seg["start"][2], 1))
                p2 = (round(seg["end"][0], 1), round(seg["end"][1], 1), round(seg["end"][2], 1))
                layer_by_point.setdefault(p1, seg["layer"])
                layer_by_point.setdefault(p2, seg["layer"])
            for point in cad_geometry.detect_disconnected_pipes(segs):
                open_ends.append({
                    "STT": len(open_ends) + 1,
                    "Hệ": system,
                    "Layer": layer_by_point.get(point, ""),
                    "Tọa độ X": point[0], "Tọa độ Y": point[1], "Tọa độ Z": point[2],
                })

        if not open_ends:
            systems = sorted(by_system.keys())
            return (f"KHÔNG phát hiện đầu tuyến hở. Đã kiểm tra {len(segments)} đoạn tuyến "
                    f"thuộc {len(systems)} hệ: {', '.join(systems)}.")

        out_path = output_excel_path if output_excel_path.endswith(".xlsx") else output_excel_path + ".xlsx"
        out_safe = resolve_safe_path(out_path)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        pd.DataFrame(open_ends).to_excel(out_safe, index=False)

        by_pair = {}
        for e in open_ends:
            by_pair[e["Hệ"]] = by_pair.get(e["Hệ"], 0) + 1

        report = [
            f"PHÁT HIỆN {len(open_ends)} ĐẦU TUYẾN HỞ (đã ghi file: {out_path}).",
            f"- Đã kiểm tra {len(segments)} đoạn tuyến.",
            "- LƯU Ý: đầu hở có thể là điểm đấu nối hợp lệ vào thiết bị (miệng gió, van, đầu "
            "phun...) hoặc lỗi vẽ thiếu đoạn/đứt tuyến — cần kỹ sư đối chiếu, tool không tự "
            "kết luận thay.",
        ]
        for note in load_notes:
            report.append(f"- {note}")
        report.append("- Thống kê theo hệ:")
        for system, count in sorted(by_pair.items(), key=lambda x: -x[1]):
            report.append(f"  + {system}: {count} đầu hở")
        report.append("- Chi tiết 10 đầu tuyến đầu tiên:")
        for e in open_ends[:10]:
            report.append(f"  {e['STT']}. [{e['Hệ']}] Layer {e['Layer']} tại "
                          f"(X={e['Tọa độ X']:.0f}, Y={e['Tọa độ Y']:.0f}, Z={e['Tọa độ Z']:.0f})")
        if len(open_ends) > 10:
            report.append(f"  ... và {len(open_ends) - 10} đầu hở khác trong file Excel.")
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi kiểm tra kết nối đường ống: {e}"


@tool
def read_ifc_model(file_path: str, output_excel_path: str = "ifc_report.xlsx") -> str:
    """Đọc thông tin từ mô hình 3D BIM định dạng IFC (.ifc) sử dụng thư viện ifcopenshell.

    Trích xuất danh sách các đối tượng thiết bị, ống, cáp (BuildingElement) và các thuộc tính cơ bản
    để xuất ra file Excel. Dùng cho nhiệm vụ bóc tách khối lượng hoặc phân tích dữ liệu từ mô hình 3D.
    """
    logger.info("Reading IFC model: %s", file_path)
    try:
        import ifcopenshell
        safe_path = resolve_safe_path(file_path)
        if not os.path.exists(safe_path):
            return f"Không tìm thấy file: {file_path}"

        model = ifcopenshell.open(safe_path)

        data = []
        # Lấy các loại entity thường dùng trong MEPF
        entities = model.by_type("IfcBuildingElement") + model.by_type("IfcDistributionElement")

        if not entities:
            return "Không tìm thấy thiết bị hoặc đường ống MEPF nào (IfcBuildingElement/IfcDistributionElement) trong file IFC."

        for entity in entities:
            guid = entity.GlobalId
            name = entity.Name or ""
            entity_type = entity.is_a()

            # Một số thuộc tính cơ bản
            properties = {}
            for relDefinesByProperties in entity.IsDefinedBy:
                if relDefinesByProperties.is_a("IfcRelDefinesByProperties"):
                    propSet = relDefinesByProperties.RelatingPropertyDefinition
                    if propSet.is_a("IfcPropertySet"):
                        for prop in propSet.HasProperties:
                            if prop.is_a("IfcPropertySingleValue"):
                                properties[prop.Name] = prop.NominalValue.wrappedValue if prop.NominalValue else ""

            data.append({
                "Loại (Type)": entity_type,
                "Tên (Name)": name,
                "GUID": guid,
                "Thuộc tính cơ bản": str(properties)[:200] if properties else ""
            })

        out_path = output_excel_path if output_excel_path.endswith(".xlsx") else output_excel_path + ".xlsx"
        out_safe = resolve_safe_path(out_path)
        parent = os.path.dirname(out_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)

        df = pd.DataFrame(data)
        df.to_excel(out_safe, index=False)

        return f"Đã đọc thành công mô hình IFC. Tổng số đối tượng tìm thấy: {len(data)}. Dữ liệu chi tiết đã xuất ra file {out_path}."

    except ImportError:
        return "Thiếu thư viện ifcopenshell. Hãy cài đặt ifcopenshell để đọc file IFC."
    except Exception as e:
        return f"Lỗi đọc file IFC: {e}"
