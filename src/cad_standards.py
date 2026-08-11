"""Tiêu chuẩn đặt tên/màu Layer và mô tả Block MEPF dùng nội bộ.

LƯU Ý: TCVN không quy định tên Layer hay cấu trúc Block trong CAD (đó là quy ước
riêng của từng văn phòng thiết kế). Bảng dưới đây là **quy ước chuẩn hóa nội bộ**
áp dụng cho toàn bộ bản vẽ đi qua `standardize_cad_drawing` (xem `src/tools.py`),
gom theo 4 hệ MEPF (Mechanical/Electrical/Plumbing/Firefighting) + General. Sửa
trực tiếp các dict bên dưới nếu văn phòng bạn dùng quy ước khác.

Mỗi Layer chuẩn có "keywords": các chuỗi (đã chuẩn hóa qua `normalize()`) hay gặp
trong bản vẽ người dùng đẩy vào, dùng để tự nhận diện & đổi tên. Chỉ những layer/
block khớp keyword cụ thể mới được TỰ ĐỘNG đổi tên; layer/block không khớp được
liệt kê để người dùng tự kiểm tra thay vì đoán bừa.
"""
import unicodedata


def normalize(name: str) -> str:
    """Chuẩn hóa chuỗi để so khớp: bỏ dấu tiếng Việt, viết hoa, chỉ giữ chữ/số."""
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFD", name)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return "".join(ch for ch in stripped.upper() if ch.isalnum())


LAYER_STANDARD = {
    "M-DUCT-SUPPLY": {"color": 5, "discipline": "Mechanical", "description": "Ống gió cấp (Supply Air Duct)",
                       "keywords": ["ONGGIOCAP", "DUCTSUPPLY", "GIOCAPSA", "SUPPLYAIR", "GIOCAP"]},
    "M-DUCT-RETURN": {"color": 4, "discipline": "Mechanical", "description": "Ống gió hồi (Return Air Duct)",
                       "keywords": ["ONGGIOHOI", "DUCTRETURN", "GIOHOIRA", "RETURNAIR", "GIOHOI"]},
    "M-PIPE-CHW": {"color": 140, "discipline": "Mechanical", "description": "Ống nước lạnh điều hòa (Chilled Water)",
                   "keywords": ["ONGNUOCLANH", "CHILLEDWATER", "ONGCHW", "PIPECHW"]},
    "M-EQUIP": {"color": 6, "discipline": "Mechanical", "description": "Thiết bị Cơ (FCU/AHU/Chiller)",
                "keywords": ["THIETBICO", "THIETBIDIEUHOA", "AHU", "CHILLER", "MECHEQUIP"]},

    "E-LIGHT": {"color": 2, "discipline": "Electrical", "description": "Đèn chiếu sáng",
                "keywords": ["DENCHIEUSANG", "LIGHTING", "DENOP", "DENTRAN", "LIGHTFIXTURE"]},
    "E-LIGHT-SWITCH": {"color": 32, "discipline": "Electrical", "description": "Công tắc đèn",
                        "keywords": ["CONGTACDEN", "LIGHTSWITCH", "CONGTAC"]},
    "E-POWER": {"color": 1, "discipline": "Electrical", "description": "Ổ cắm & đường dây động lực",
                "keywords": ["OCAMDIEN", "OUTLETPOWER", "DONGLUC", "SOCKETPOWER", "OCAM"]},
    "E-CABLE-TRAY": {"color": 30, "discipline": "Electrical", "description": "Máng cáp / Thang cáp",
                      "keywords": ["MANGCAP", "THANGCAP", "CABLETRAY"]},
    "E-PANEL": {"color": 6, "discipline": "Electrical", "description": "Tủ điện / Bảng điện",
                "keywords": ["TUDIEN", "BANGDIEN", "PANELBOARD", "DISTRIBUTIONPANEL"]},
    "E-LIGHTNING": {"color": 12, "discipline": "Electrical", "description": "Hệ thống chống sét",
                     "keywords": ["CHONGSET", "LIGHTNINGPROTECTION", "TIEPDIA", "GROUNDING"]},

    "P-PIPE-CAP": {"color": 3, "discipline": "Plumbing", "description": "Ống cấp nước (Water Supply)",
                   "keywords": ["ONGCAPNUOC", "CAPNUOC", "WATERSUPPLY", "PIPECAP"]},
    "P-PIPE-THOAT": {"color": 43, "discipline": "Plumbing", "description": "Ống thoát nước (Drainage)",
                      "keywords": ["ONGTHOATNUOC", "THOATNUOC", "DRAINAGE", "PIPETHOAT", "THOATSAN"]},
    "P-EQUIP": {"color": 84, "discipline": "Plumbing", "description": "Thiết bị Cấp thoát nước (Bơm/Bể)",
                "keywords": ["THIETBICAPTHOAT", "BENUOC", "MAYBOMNUOC", "PLUMBEQUIP"]},

    "F-SPRINKLER": {"color": 1, "discipline": "Firefighting", "description": "Đầu phun Sprinkler",
                     "keywords": ["DAUPHUNSPRINKLER", "SPRINKLERHEAD", "DAUPHUNCHUACHAY"]},
    "F-PIPE": {"color": 12, "discipline": "Firefighting", "description": "Ống chữa cháy",
               "keywords": ["ONGCHUACHAY", "ONGPCCC", "FIREPIPE", "ONGSPRINKLER"]},
    "F-EQUIP": {"color": 10, "discipline": "Firefighting", "description": "Thiết bị PCCC (Bơm chữa cháy/Bình chữa cháy)",
                "keywords": ["THIETBIPCCC", "BOMCHUACHAY", "BINHCHUACHAY", "FIREPUMP", "FIREEQUIP"]},
    "F-DETECT": {"color": 200, "discipline": "Firefighting", "description": "Đầu báo cháy",
                 "keywords": ["DAUBAOCHAY", "SMOKEDETECTOR", "FIREDETECTOR", "BAOCHAY"]},

    "G-TEXT": {"color": 7, "discipline": "General", "description": "Chữ ghi chú",
               "keywords": ["GHICHU", "NOTETEXT", "ANNOTATION"]},
    "G-DIM": {"color": 7, "discipline": "General", "description": "Kích thước",
              "keywords": ["KICHTHUOC", "DIMENSION"]},
    "G-GRID": {"color": 8, "discipline": "General", "description": "Lưới trục / Cột",
               "keywords": ["LUOITRUC", "GRIDLINE", "TRUCCOT", "COLUMNGRID"]},
}

# Chỉ 1 linetype dùng chung để tránh lỗi thiếu linetype table entry khi áp cho
# một bản vẽ chưa nạp sẵn các linetype đứt/chấm khác.
LAYER_LINETYPE = "Continuous"

BLOCK_STANDARD = {
    "DIFFUSER_SUPPLY": {"discipline": "Mechanical", "ma_hieu": "M-DIFF-S", "default_layer": "M-DUCT-SUPPLY",
                         "description": "Miệng gió cấp (Supply Diffuser)",
                         "keywords": ["MIENGGIOCAP", "SUPPLYDIFFUSER", "DIFFUSERCAP", "GIOCAPSA"]},
    "DIFFUSER_RETURN": {"discipline": "Mechanical", "ma_hieu": "M-DIFF-R", "default_layer": "M-DUCT-RETURN",
                         "description": "Miệng gió hồi (Return Diffuser)",
                         "keywords": ["MIENGGIOHOI", "RETURNDIFFUSER", "DIFFUSERHOI", "GIOHOIRA"]},
    "FCU": {"discipline": "Mechanical", "ma_hieu": "M-FCU", "default_layer": "M-EQUIP",
            "description": "Dàn lạnh FCU (Fan Coil Unit)",
            "keywords": ["FANCOILUNIT", "DANLANH"]},
    "LIGHT_PANEL": {"discipline": "Electrical", "ma_hieu": "E-LT-PANEL", "default_layer": "E-LIGHT",
                     "description": "Đèn Panel/Downlight vuông",
                     "keywords": ["DENPANEL", "PANELLIGHT", "DENOPVUONG"]},
    "LIGHT_DOWNLIGHT": {"discipline": "Electrical", "ma_hieu": "E-LT-DL", "default_layer": "E-LIGHT",
                         "description": "Đèn Downlight âm trần",
                         "keywords": ["DENDOWNLIGHT", "DOWNLIGHT", "DENAMTRAN"]},
    "SOCKET": {"discipline": "Electrical", "ma_hieu": "E-SOCKET", "default_layer": "E-POWER",
               "description": "Ổ cắm điện",
               "keywords": ["OCAMDIEN", "ELECTRICALOUTLET", "OUTLETSOCKET"]},
    "SWITCH": {"discipline": "Electrical", "ma_hieu": "E-SWITCH", "default_layer": "E-LIGHT-SWITCH",
               "description": "Công tắc đèn",
               "keywords": ["CONGTACDEN", "LIGHTSWITCH"]},
    "SPRINKLER": {"discipline": "Firefighting", "ma_hieu": "F-SPRK", "default_layer": "F-SPRINKLER",
                  "description": "Đầu phun Sprinkler chữa cháy",
                  "keywords": ["DAUPHUNSPRINKLER", "SPRINKLERHEAD"]},
    "PUMP": {"discipline": "Plumbing", "ma_hieu": "P-PUMP", "default_layer": "P-EQUIP",
             "description": "Bơm (cấp nước/PCCC tùy hệ bố trí)",
             "keywords": ["MAYBOMNUOC", "WATERPUMP", "MAYBOM"]},
}


def _register_canonical_names_as_keywords(registry: dict) -> None:
    """Cho phép tên đã đúng chuẩn (chỉ khác hoa/thường hoặc dấu gạch ngang) cũng tự
    khớp về chính nó, thay vì chỉ khớp qua các keyword liệt kê thủ công."""
    for key, meta in registry.items():
        own = normalize(key)
        if own and own not in meta["keywords"]:
            meta["keywords"].append(own)


_register_canonical_names_as_keywords(LAYER_STANDARD)
_register_canonical_names_as_keywords(BLOCK_STANDARD)


def _best_keyword_match(normalized_name: str, registry: dict) -> str | None:
    """Trả về key trong `registry` có keyword khớp dài nhất (khớp cụ thể nhất) với
    `normalized_name`, hoặc None nếu không có keyword nào khớp."""
    best_key, best_len = None, 0
    for key, meta in registry.items():
        for kw in meta.get("keywords", ()):
            if kw and (kw in normalized_name or normalized_name in kw):
                if len(kw) > best_len:
                    best_key, best_len = key, len(kw)
    return best_key


def match_layer(name: str) -> str | None:
    """Đoán tên layer chuẩn tương ứng với `name` (tên layer thô trong bản vẽ người
    dùng đẩy vào). Trả về None nếu không nhận diện được (cần người dùng tự kiểm tra
    thay vì đoán bừa)."""
    normalized = normalize(name)
    if not normalized:
        return None
    return _best_keyword_match(normalized, LAYER_STANDARD)


def match_block(name: str) -> str | None:
    """Đoán tên Block chuẩn tương ứng với `name` (tên Block thô trong bản vẽ người
    dùng đẩy vào). Trả về None nếu không nhận diện được."""
    normalized = normalize(name)
    if not normalized:
        return None
    return _best_keyword_match(normalized, BLOCK_STANDARD)
