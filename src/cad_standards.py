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

QUY ƯỚC ĐẶT TÊN (cấu trúc `<HỆ>-<NHÓM>[-<PHÂN LOẠI>]`):
- `M-` Mechanical (Cơ/Điều hòa thông gió), `E-` Electrical (Điện), `P-` Plumbing (Cấp
  thoát nước), `F-` Firefighting (PCCC), `G-` General (chung, không thuộc riêng hệ nào).
- Nhóm thứ 2 nói rõ loại đối tượng: ống gió/ống nước thì ghi tắt hệ thống cụ thể (SAD,
  RAD, CHWS...); thiết bị dùng `EQUIP-<LOẠI>` (VD `M-EQUIP-AHU`, `F-EQUIP-PUMP`); nhóm
  không có thiết bị/ống rõ ràng (đèn, ổ cắm, báo cháy...) đặt tên mô tả ngắn gọn.

Quy ước màu tổng quát để nhìn Layer là đoán ngay được vai trò (áp dụng xuyên suốt
cả 4 hệ, không chỉ riêng 1 hệ):
- "Cấp" (nguồn/gió/nước lạnh đi vào không gian) -> Xanh dương (5)
- "Hồi" (đi ngược về nguồn) -> Cyan (4)
- Nóng (nước nóng, sưởi) -> Đỏ (1) — quy ước "nóng = đỏ, lạnh = xanh" kinh điển
- Liên quan an toàn cháy nổ/thoát hiểm (PCCC, tăng áp, hút khói, đèn sự cố)
  -> luôn thuộc dải màu đỏ/cam để nổi bật, kể cả khi Layer đó do hệ M hay E vẽ
- Thiết bị chính (`*-EQUIP-*`) của cả 3 hệ M/P/F dùng chung màu xám trung tính (9) —
  các hệ đã có màu ý nghĩa riêng cho đường ống/dây, thiết bị chỉ cần nổi khối, không
  cần thêm 1 lớp mã màu riêng cho từng loại máy.
"""
import unicodedata

LAYER_STANDARD = {
    # ---------------------------------------------------------------- MECHANICAL (HVAC)
    # Ống gió (Duct) — dùng đúng ký hiệu viết tắt quốc tế phổ biến trong hồ sơ MEPF.
    "M-SAD": {"color": 5, "discipline": "Mechanical", "description": "Ống gió cấp (Supply Air Duct)",
              "keywords": ["SAD", "ONGGIOCAP", "DUCTSUPPLY", "GIOCAPSA", "SUPPLYAIRDUCT", "GIOCAP"]},
    "M-RAD": {"color": 4, "discipline": "Mechanical", "description": "Ống gió hồi (Return Air Duct)",
              "keywords": ["RAD", "ONGGIOHOI", "DUCTRETURN", "GIOHOIRA", "RETURNAIRDUCT", "GIOHOI"]},
    "M-FAD": {"color": 3, "discipline": "Mechanical", "description": "Ống gió tươi (Fresh Air Duct)",
              "keywords": ["FAD", "ONGGIOTUOI", "FRESHAIRDUCT", "GIOTUOI", "OUTDOORAIRDUCT"]},
    "M-EAD": {"color": 6, "discipline": "Mechanical", "description": "Ống gió thải (Exhaust Air Duct)",
              "keywords": ["EAD", "ONGGIOTHAI", "EXHAUSTAIRDUCT", "GIOTHAI"]},
    "M-KEAD": {"color": 30, "discipline": "Mechanical", "description": "Ống gió thải bếp (Kitchen Exhaust Air Duct)",
               "keywords": ["KEAD", "ONGGIOTHAIBEP", "KITCHENEXHAUST", "GIOTHAIBEP", "HUTMUIBEP"]},
    "M-PAD": {"color": 1, "discipline": "Mechanical",
              "description": "Ống gió tăng áp cầu thang/PCCC (Pressurization Air Duct)",
              "keywords": ["PAD", "ONGGIOTANGAP", "PRESSURIZATIONDUCT", "TANGAPCAUTHANG", "TANGAP"]},
    "M-SEAD": {"color": 12, "discipline": "Mechanical", "description": "Ống gió hút khói (Smoke Exhaust Air Duct)",
               "keywords": ["SEAD", "ONGGIOHUTKHOI", "SMOKEEXHAUSTDUCT", "HUTKHOI", "SMOKEEXTRACT"]},
    # Ống nước/gas (Pipe)
    "M-PIPE-REF": {"color": 140, "discipline": "Mechanical", "description": "Ống đồng gas lạnh (Refrigerant Pipe)",
                   "keywords": ["ONGDONG", "ONGGASLANH", "REFRIGERANTPIPE", "ONGGAS", "COPPERPIPE"]},
    "M-PIPE-COND": {"color": 8, "discipline": "Mechanical",
                     "description": "Ống nước ngưng (Condensate Drain Pipe)",
                     "keywords": ["ONGNUOCNGUNG", "CONDENSATEPIPE", "NUOCNGUNG", "DRAINPIPECOND"]},
    "M-PIPE-CHWS": {"color": 5, "discipline": "Mechanical",
                     "description": "Ống cấp nước lạnh Chiller (Chilled Water Supply)",
                     "keywords": ["CHWS", "ONGCAPNUOCLANH", "CHILLEDWATERSUPPLY", "ONGCAPCHILLER"]},
    "M-PIPE-CHWR": {"color": 4, "discipline": "Mechanical",
                     "description": "Ống hồi nước lạnh Chiller (Chilled Water Return)",
                     "keywords": ["CHWR", "ONGHOINUOCLANH", "CHILLEDWATERRETURN", "ONGHOICHILLER"]},
    # Thiết bị (Equipment) — tách theo từng loại máy chính thay vì gộp chung 1 layer.
    "M-EQUIP-AHU": {"color": 9, "discipline": "Mechanical", "description": "Bộ xử lý không khí (Air Handling Unit)",
                     "keywords": ["AHU", "AIRHANDLINGUNIT", "BOXULYKHONGKHI"]},
    "M-EQUIP-FCU": {"color": 9, "discipline": "Mechanical", "description": "Dàn lạnh (Fan Coil Unit)",
                     "keywords": ["FCU", "FANCOILUNIT", "DANLANHFCU"]},
    "M-EQUIP-VRV": {"color": 9, "discipline": "Mechanical", "description": "Dàn nóng/dàn lạnh VRV-VRF",
                     "keywords": ["VRV", "VRF", "DANNONGVRV", "DANLANHVRV"]},
    "M-EQUIP-CHILLER": {"color": 9, "discipline": "Mechanical", "description": "Máy làm lạnh nước (Chiller)",
                         "keywords": ["CHILLER", "MAYLAMLANHNUOC"]},
    "M-EQUIP-CTWR": {"color": 9, "discipline": "Mechanical", "description": "Tháp giải nhiệt (Cooling Tower)",
                      "keywords": ["COOLINGTOWER", "THAPGIAINHIET"]},
    "M-EQUIP-PUMP": {"color": 9, "discipline": "Mechanical",
                      "description": "Bơm nước lạnh/giải nhiệt (Chilled/Condenser Water Pump)",
                      "keywords": ["BOMNUOCLANH", "BOMGIAINHIET", "CHILLEDWATERPUMP", "CONDENSERWATERPUMP"]},
    "M-EQUIP-FAN": {"color": 9, "discipline": "Mechanical",
                     "description": "Quạt thông gió/hút/tăng áp (Ventilation/Exhaust/Pressurization Fan)",
                     "keywords": ["QUATTHONGGIO", "QUATHUT", "QUATTANGAP", "VENTILATIONFAN", "EXHAUSTFAN"]},

    # ---------------------------------------------------------------- ELECTRICAL
    "E-LIGHT": {"color": 2, "discipline": "Electrical", "description": "Đèn chiếu sáng thường",
                "keywords": ["DENCHIEUSANG", "LIGHTING", "DENOP", "DENTRAN", "LIGHTFIXTURE"]},
    "E-LIGHT-EMG": {"color": 11, "discipline": "Electrical",
                     "description": "Đèn sự cố / Đèn Exit (Emergency & Exit Light)",
                     "keywords": ["DENSUCO", "DENEXIT", "EMERGENCYLIGHT", "EXITLIGHT", "DENTHOATHIEM"]},
    "E-LIGHT-SWITCH": {"color": 32, "discipline": "Electrical", "description": "Công tắc đèn",
                        "keywords": ["CONGTACDEN", "LIGHTSWITCH", "CONGTAC"]},
    "E-POWER": {"color": 1, "discipline": "Electrical", "description": "Ổ cắm & đường dây động lực",
                "keywords": ["OCAMDIEN", "OUTLETPOWER", "DONGLUC", "SOCKETPOWER", "OCAM"]},
    "E-CABLE-TRAY": {"color": 30, "discipline": "Electrical", "description": "Máng cáp / Thang cáp",
                      "keywords": ["MANGCAP", "THANGCAP", "CABLETRAY"]},
    "E-TRUNKING": {"color": 33, "discipline": "Electrical", "description": "Máng nhựa đi dây (Trunking)",
                    "keywords": ["MANGNHUA", "TRUNKING", "MANGDIEN"]},
    "E-PANEL": {"color": 6, "discipline": "Electrical", "description": "Tủ điện / Bảng điện",
                "keywords": ["TUDIEN", "BANGDIEN", "PANELBOARD", "DISTRIBUTIONPANEL"]},
    "E-GENERATOR": {"color": 14, "discipline": "Electrical",
                     "description": "Máy phát điện dự phòng & Tủ chuyển nguồn ATS",
                     "keywords": ["MAYPHATDIEN", "GENERATOR", "ATS", "TUCHUYENNGUON"]},
    "E-LIGHTNING": {"color": 12, "discipline": "Electrical", "description": "Chống sét & Tiếp địa",
                     "keywords": ["CHONGSET", "LIGHTNINGPROTECTION", "TIEPDIA", "GROUNDING"]},
    "E-ELV-DATA": {"color": 140, "discipline": "Electrical", "description": "Mạng Data / Điện thoại (ELV)",
                    "keywords": ["MANGDATA", "MANGLAN", "DIENTHOAI", "TELEPHONEDATA", "STRUCTUREDCABLING"]},
    "E-ELV-CCTV": {"color": 141, "discipline": "Electrical", "description": "Camera an ninh (CCTV)",
                    "keywords": ["CAMERA", "CCTV", "ANNINH"]},
    "E-ELV-ACCESS": {"color": 142, "discipline": "Electrical", "description": "Kiểm soát vào ra (Access Control)",
                      "keywords": ["KIEMSOATVAORA", "ACCESSCONTROL", "THEDIEUTU"]},
    "E-CONDUIT": {"color": 24, "discipline": "Electrical", "description": "Ống luồn dây điện ngầm (Conduit)",
                   "keywords": ["ONGLUONDIEN", "CONDUIT", "ONGDIENNGAM"]},
    "E-EQUIP-TRANSFORMER": {"color": 9, "discipline": "Electrical", "description": "Máy biến áp (Transformer)",
                             "keywords": ["MAYBIENAP", "TRANSFORMER", "TRAMBIENAP"]},
    "E-EQUIP-CAPACITOR": {"color": 9, "discipline": "Electrical",
                           "description": "Tủ bù công suất (Capacitor Bank)",
                           "keywords": ["TUBUCONGSUAT", "CAPACITORBANK", "TUBU"]},

    # ---------------------------------------------------------------- PLUMBING (Cấp thoát nước)
    "P-PIPE-CAP": {"color": 5, "discipline": "Plumbing", "description": "Ống cấp nước sinh hoạt (Cold Water Supply)",
                   "keywords": ["ONGCAPNUOCSINHHOAT", "ONGCAPNUOC", "CAPNUOC", "COLDWATERSUPPLY", "PIPECAP"]},
    "P-PIPE-HW": {"color": 1, "discipline": "Plumbing",
                  "description": "Ống cấp nước nóng sinh hoạt (Domestic Hot Water Supply)",
                  "keywords": ["ONGCAPNUOCNONGSINHHOAT", "ONGNUOCNONG", "HOTWATERSUPPLY", "NUOCNONG"]},
    "P-PIPE-HWR": {"color": 12, "discipline": "Plumbing",
                   "description": "Ống hồi nước nóng (Hot Water Return / Recirculation)",
                   "keywords": ["ONGHOINUOCNONG", "HOTWATERRETURN", "HOINUOCNONG", "RECIRCULATION"]},
    "P-PIPE-THOAT": {"color": 43, "discipline": "Plumbing",
                      "description": "Ống thoát nước thải (Soil / Waste Drainage)",
                      "keywords": ["ONGTHOATNUOC", "THOATNUOC", "DRAINAGE", "PIPETHOAT", "THOATSAN", "THOATTHAI"]},
    "P-PIPE-VENT": {"color": 8, "discipline": "Plumbing", "description": "Ống thông hơi (Vent Pipe)",
                     "keywords": ["ONGTHONGHOI", "VENTPIPE", "THONGHOI"]},
    "P-PIPE-RAIN": {"color": 140, "discipline": "Plumbing",
                     "description": "Ống thoát nước mưa (Rainwater / Storm Drainage)",
                     "keywords": ["ONGTHOATNUOCMUA", "RAINWATER", "STORMDRAIN", "NUOCMUA"]},
    "P-EQUIP-PUMP": {"color": 9, "discipline": "Plumbing",
                      "description": "Bơm cấp nước/bơm tăng áp (Water Supply/Booster Pump)",
                      "keywords": ["BOMCAPNUOC", "BOMTANGAP", "BOOSTERPUMP", "MAYBOMNUOC"]},
    "P-EQUIP-TANK": {"color": 9, "discipline": "Plumbing",
                      "description": "Bể nước ngầm/bể mái/bồn áp lực (Water Tank/Pressure Vessel)",
                      "keywords": ["BENUOCNGAM", "BENUOCMAI", "BONAPLUC", "WATERTANK", "PRESSUREVESSEL"]},
    "P-EQUIP-WH": {"color": 9, "discipline": "Plumbing",
                    "description": "Bình nóng lạnh/máy nước nóng (Water Heater)",
                    "keywords": ["BINHNONGLANH", "MAYNUOCNONG", "WATERHEATER"]},
    "P-EQUIP-STP": {"color": 9, "discipline": "Plumbing",
                     "description": "Trạm xử lý nước thải/bể tự hoại (STP/Septic Tank)",
                     "keywords": ["TRAMXULYNUOCTHAI", "BETUHOAI", "SEPTICTANK", "STP"]},

    # ---------------------------------------------------------------- FIREFIGHTING (PCCC)
    "F-SPRINKLER": {"color": 1, "discipline": "Firefighting", "description": "Đầu phun Sprinkler",
                     "keywords": ["DAUPHUNSPRINKLER", "SPRINKLERHEAD", "DAUPHUNCHUACHAY"]},
    "F-PIPE-SPK": {"color": 12, "discipline": "Firefighting", "description": "Ống cấp nước hệ Sprinkler",
                    "keywords": ["ONGSPRINKLER", "SPRINKLERPIPE", "ONGCHUACHAYSPRINKLER"]},
    "F-PIPE-HYD": {"color": 10, "discipline": "Firefighting",
                    "description": "Ống họng nước vách tường / trụ cứu hỏa (Standpipe / Hydrant)",
                    "keywords": ["ONGHONGNUOC", "STANDPIPE", "HYDRANTPIPE", "ONGTRUCUUHOA", "HONGNUOCVACHTUONG"]},
    "F-EQUIP-PUMP": {"color": 9, "discipline": "Firefighting",
                      "description": "Bơm chữa cháy (Jockey/Điện/Diesel)",
                      "keywords": ["BOMCHUACHAY", "FIREPUMP", "JOCKEYPUMP", "DIESELPUMP"]},
    "F-EQUIP-TANK": {"color": 9, "discipline": "Firefighting", "description": "Bể nước chữa cháy (Fire Water Tank)",
                      "keywords": ["BENUOCCHUACHAY", "FIREWATERTANK"]},
    "F-EQUIP-VALVE": {"color": 9, "discipline": "Firefighting",
                       "description": "Van điều khiển hệ thống (Alarm Check Valve/Zone Control Valve)",
                       "keywords": ["VANDIEUKHIEN", "ALARMCHECKVALVE", "ZONECONTROLVALVE", "VANBAODONG"]},
    "F-DETECT": {"color": 200, "discipline": "Firefighting", "description": "Đầu báo cháy",
                 "keywords": ["DAUBAOCHAY", "SMOKEDETECTOR", "FIREDETECTOR", "BAOCHAY"]},
    "F-ALARM-DEVICE": {"color": 201, "discipline": "Firefighting",
                        "description": "Chuông / Còi / Đèn báo cháy (Bell/Strobe/Manual Call Point)",
                        "keywords": ["CHUONGBAOCHAY", "COIBAOCHAY", "MANUALCALLPOINT", "FIREBELL", "FIREALARMDEVICE"]},
    "F-GAS-SUPPRESS": {"color": 202, "discipline": "Firefighting",
                        "description": "Hệ thống chữa cháy khí (FM200 / Khí sạch)",
                        "keywords": ["CHUACHAYKHI", "GASSUPPRESSION", "FM200", "CLEANAGENT", "KHISACH"]},
    "F-EXTINGUISHER": {"color": 203, "discipline": "Firefighting", "description": "Bình chữa cháy xách tay",
                        "keywords": ["BINHCHUACHAY", "FIREEXTINGUISHER", "BINHBOTBC"]},

    # ---------------------------------------------------------------- GENERAL
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
    "DIFFUSER_SUPPLY": {"discipline": "Mechanical", "ma_hieu": "M-DIFF-S", "default_layer": "M-SAD",
                         "description": "Miệng gió cấp (Supply Diffuser)",
                         "keywords": ["MIENGGIOCAP", "SUPPLYDIFFUSER", "DIFFUSERCAP", "GIOCAPSA"]},
    "DIFFUSER_RETURN": {"discipline": "Mechanical", "ma_hieu": "M-DIFF-R", "default_layer": "M-RAD",
                         "description": "Miệng gió hồi (Return Diffuser)",
                         "keywords": ["MIENGGIOHOI", "RETURNDIFFUSER", "DIFFUSERHOI", "GIOHOIRA"]},
    "FCU": {"discipline": "Mechanical", "ma_hieu": "M-FCU", "default_layer": "M-EQUIP-FCU",
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
    "PUMP": {"discipline": "Plumbing", "ma_hieu": "P-PUMP", "default_layer": "P-EQUIP-PUMP",
             "description": "Bơm (cấp nước/PCCC tùy hệ bố trí)",
             "keywords": ["WATERPUMP", "MAYBOM"]},
}


def normalize(name: str) -> str:
    """Chuẩn hóa chuỗi để so khớp: bỏ dấu tiếng Việt, viết hoa, chỉ giữ chữ/số."""
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFD", name)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return "".join(ch for ch in stripped.upper() if ch.isalnum())


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
    """Trả về key trong `registry` có keyword khớp dài nhất (khớp cụ thể nhất) nằm
    TRONG `normalized_name`, hoặc None nếu không có keyword nào khớp.

    Cố ý CHỈ so khớp một chiều (keyword là chuỗi con của tên) chứ không so khớp
    ngược lại (tên là chuỗi con của keyword) — vì chiều ngược dễ gây nhầm giữa các
    ký hiệu viết tắt ngắn dùng chung một phần chữ, ví dụ layer tên "EAD" (Exhaust)
    sẽ vô tình khớp "KEAD" (Kitchen Exhaust) nếu so khớp 2 chiều, do "EAD" là chuỗi
    con của "KEAD". So khớp 1 chiều + ưu tiên keyword dài nhất giải quyết đúng cả 2
    trường hợp: "EAD" chỉ khớp M-EAD, "KEAD" khớp M-KEAD (khớp dài hơn, cụ thể hơn).
    """
    best_key, best_len = None, 0
    for key, meta in registry.items():
        for kw in meta.get("keywords", ()):
            if kw and kw in normalized_name and len(kw) > best_len:
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
