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

QUY ƯỚC MÀU (không có TCVN nào quy định màu Layer MEPF, nên áp dụng quy ước chung
phổ biến trong ngành: MỖI HỆ MỘT DẢI MÀU (hue) RIÊNG BIỆT, không hệ nào dùng lại
đúng mã màu của hệ khác — mục tiêu là nhìn màu đoán ngay ra hệ, không nhầm lẫn):
- **Mechanical (M)**: dải XANH LÁ (green, ACI 80-99) — ống gió + ống nước/gas.
- **Electrical (E)**: dải CAM/VÀNG (orange, ACI 20-39) — đèn, dây, máng cáp, ELV.
- **Plumbing (P)**: dải XANH DƯƠNG (blue, ACI 140-169) — các loại ống nước.
- **Firefighting (F)**: dải ĐỎ (red, ACI 10-19) — ống, đầu phun, thiết bị báo cháy.
- **General (G)**: xám/trắng trung tính (7, 8) — không thuộc hệ nào nên không cần
  dải màu riêng, chỉ cần khác hẳn 4 dải trên.
Trong mỗi dải, sắc độ (đậm/nhạt, thuần/pha) phân biệt vai trò con: "cấp" dùng sắc
thuần/sáng nhất của dải, "hồi"/"thải" dùng sắc đậm hoặc pha hơn — nhưng KHÔNG còn
mượn màu của hệ khác để biểu đạt (VD trước đây "nóng = đỏ" cho cả ống nước nóng
Plumbing lẫn PCCC, khiến nhìn nhanh dễ tưởng hai hệ là một; nay ống nước nóng vẫn
nằm trong dải xanh dương của Plumbing, chỉ đổi sắc độ).
Ngoại lệ duy nhất, có chủ đích: thiết bị chính (`*-EQUIP-*`) của cả 3 hệ M/P/F dùng
chung màu xám trung tính (9) — thiết bị luôn có Block/nhãn riêng để nhận diện, thêm
mã màu theo hệ cho khối thiết bị chỉ gây nhiễu chứ không giúp phân biệt gì thêm.
Toàn bộ mã màu đã được xác minh bằng `ezdxf.colors.aci2rgb()` (đúng bảng màu ACI
thật của AutoCAD) để đảm bảo không có 2 mã số ACI khác nhau nhưng lại RA MÀU GIỐNG
HỆT nhau (VD ACI 1 và ACI 10 cùng là đỏ thuần `(255,0,0)` — bẫy dễ mắc nếu chọn màu
theo cảm tính mà không tra bảng thật).
"""
import unicodedata

LAYER_STANDARD = {
    # ---------------------------------------------------------------- MECHANICAL (HVAC)
    # Ống gió (Duct) — dùng đúng ký hiệu viết tắt quốc tế phổ biến trong hồ sơ MEPF.
    "M-SAD": {"color": 90, "discipline": "Mechanical", "description": "Ống gió cấp (Supply Air Duct)",
              "keywords": ["SAD", "ONGGIOCAP", "DUCTSUPPLY", "GIOCAPSA", "SUPPLYAIRDUCT", "GIOCAP"]},
    "M-RAD": {"color": 92, "discipline": "Mechanical", "description": "Ống gió hồi (Return Air Duct)",
              "keywords": ["RAD", "ONGGIOHOI", "DUCTRETURN", "GIOHOIRA", "RETURNAIRDUCT", "GIOHOI"]},
    "M-FAD": {"color": 93, "discipline": "Mechanical", "description": "Ống gió tươi (Fresh Air Duct)",
              "keywords": ["FAD", "ONGGIOTUOI", "FRESHAIRDUCT", "GIOTUOI", "OUTDOORAIRDUCT"]},
    "M-EAD": {"color": 94, "discipline": "Mechanical", "description": "Ống gió thải (Exhaust Air Duct)",
              "keywords": ["EAD", "ONGGIOTHAI", "EXHAUSTAIRDUCT", "GIOTHAI"]},
    "M-KEAD": {"color": 95, "discipline": "Mechanical", "description": "Ống gió thải bếp (Kitchen Exhaust Air Duct)",
               "keywords": ["KEAD", "ONGGIOTHAIBEP", "KITCHENEXHAUST", "GIOTHAIBEP", "HUTMUIBEP"]},
    "M-PAD": {"color": 96, "discipline": "Mechanical",
              "description": "Ống gió tăng áp cầu thang/PCCC (Pressurization Air Duct)",
              "keywords": ["PAD", "ONGGIOTANGAP", "PRESSURIZATIONDUCT", "TANGAPCAUTHANG", "TANGAP"]},
    "M-SEAD": {"color": 97, "discipline": "Mechanical", "description": "Ống gió hút khói (Smoke Exhaust Air Duct)",
               "keywords": ["SEAD", "ONGGIOHUTKHOI", "SMOKEEXHAUSTDUCT", "HUTKHOI", "SMOKEEXTRACT"]},
    # Ống nước/gas (Pipe)
    "M-PIPE-REF": {"color": 80, "discipline": "Mechanical", "description": "Ống đồng gas lạnh (Refrigerant Pipe)",
                   "keywords": ["ONGDONG", "ONGGASLANH", "REFRIGERANTPIPE", "ONGGAS", "COPPERPIPE"]},
    "M-PIPE-COND": {"color": 82, "discipline": "Mechanical",
                     "description": "Ống nước ngưng (Condensate Drain Pipe)",
                     "keywords": ["ONGNUOCNGUNG", "CONDENSATEPIPE", "NUOCNGUNG", "DRAINPIPECOND"]},
    "M-PIPE-CHWS": {"color": 83, "discipline": "Mechanical",
                     "description": "Ống cấp nước lạnh Chiller (Chilled Water Supply)",
                     "keywords": ["CHWS", "ONGCAPNUOCLANH", "CHILLEDWATERSUPPLY", "ONGCAPCHILLER"]},
    "M-PIPE-CHWR": {"color": 84, "discipline": "Mechanical",
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
    "E-LIGHT": {"color": 20, "discipline": "Electrical", "description": "Đèn chiếu sáng thường",
                "keywords": ["DENCHIEUSANG", "LIGHTING", "DENOP", "DENTRAN", "LIGHTFIXTURE"]},
    "E-LIGHT-EMG": {"color": 22, "discipline": "Electrical",
                     "description": "Đèn sự cố / Đèn Exit (Emergency & Exit Light)",
                     "keywords": ["DENSUCO", "DENEXIT", "EMERGENCYLIGHT", "EXITLIGHT", "DENTHOATHIEM"]},
    "E-LIGHT-SWITCH": {"color": 23, "discipline": "Electrical", "description": "Công tắc đèn",
                        "keywords": ["CONGTACDEN", "LIGHTSWITCH", "CONGTAC"]},
    "E-POWER": {"color": 24, "discipline": "Electrical", "description": "Ổ cắm & đường dây động lực",
                "keywords": ["OCAMDIEN", "OUTLETPOWER", "DONGLUC", "SOCKETPOWER", "OCAM"]},
    "E-CABLE-TRAY": {"color": 25, "discipline": "Electrical", "description": "Máng cáp / Thang cáp",
                      "keywords": ["MANGCAP", "THANGCAP", "CABLETRAY"]},
    "E-TRUNKING": {"color": 26, "discipline": "Electrical", "description": "Máng nhựa đi dây (Trunking)",
                    "keywords": ["MANGNHUA", "TRUNKING", "MANGDIEN"]},
    "E-PANEL": {"color": 27, "discipline": "Electrical", "description": "Tủ điện / Bảng điện",
                "keywords": ["TUDIEN", "BANGDIEN", "PANELBOARD", "DISTRIBUTIONPANEL"]},
    "E-GENERATOR": {"color": 30, "discipline": "Electrical",
                     "description": "Máy phát điện dự phòng & Tủ chuyển nguồn ATS",
                     "keywords": ["MAYPHATDIEN", "GENERATOR", "ATS", "TUCHUYENNGUON"]},
    "E-LIGHTNING": {"color": 32, "discipline": "Electrical", "description": "Chống sét & Tiếp địa",
                     "keywords": ["CHONGSET", "LIGHTNINGPROTECTION", "TIEPDIA", "GROUNDING"]},
    "E-ELV-DATA": {"color": 33, "discipline": "Electrical", "description": "Mạng Data / Điện thoại (ELV)",
                    "keywords": ["MANGDATA", "MANGLAN", "DIENTHOAI", "TELEPHONEDATA", "STRUCTUREDCABLING"]},
    "E-ELV-CCTV": {"color": 34, "discipline": "Electrical", "description": "Camera an ninh (CCTV)",
                    "keywords": ["CAMERA", "CCTV", "ANNINH"]},
    "E-ELV-ACCESS": {"color": 35, "discipline": "Electrical", "description": "Kiểm soát vào ra (Access Control)",
                      "keywords": ["KIEMSOATVAORA", "ACCESSCONTROL", "THEDIEUTU"]},
    "E-CONDUIT": {"color": 36, "discipline": "Electrical", "description": "Ống luồn dây điện ngầm (Conduit)",
                   "keywords": ["ONGLUONDIEN", "CONDUIT", "ONGDIENNGAM"]},
    "E-EQUIP-TRANSFORMER": {"color": 9, "discipline": "Electrical", "description": "Máy biến áp (Transformer)",
                             "keywords": ["MAYBIENAP", "TRANSFORMER", "TRAMBIENAP"]},
    "E-EQUIP-CAPACITOR": {"color": 9, "discipline": "Electrical",
                           "description": "Tủ bù công suất (Capacitor Bank)",
                           "keywords": ["TUBUCONGSUAT", "CAPACITORBANK", "TUBU"]},

    # ---------------------------------------------------------------- PLUMBING (Cấp thoát nước)
    "P-PIPE-CAP": {"color": 160, "discipline": "Plumbing", "description": "Ống cấp nước sinh hoạt (Cold Water Supply)",
                   "keywords": ["ONGCAPNUOCSINHHOAT", "ONGCAPNUOC", "CAPNUOC", "COLDWATERSUPPLY", "PIPECAP"]},
    "P-PIPE-HW": {"color": 162, "discipline": "Plumbing",
                  "description": "Ống cấp nước nóng sinh hoạt (Domestic Hot Water Supply)",
                  "keywords": ["ONGCAPNUOCNONGSINHHOAT", "ONGNUOCNONG", "HOTWATERSUPPLY", "NUOCNONG"]},
    "P-PIPE-HWR": {"color": 163, "discipline": "Plumbing",
                   "description": "Ống hồi nước nóng (Hot Water Return / Recirculation)",
                   "keywords": ["ONGHOINUOCNONG", "HOTWATERRETURN", "HOINUOCNONG", "RECIRCULATION"]},
    "P-PIPE-THOAT": {"color": 164, "discipline": "Plumbing",
                      "description": "Ống thoát nước thải (Soil / Waste Drainage)",
                      "keywords": ["ONGTHOATNUOC", "THOATNUOC", "DRAINAGE", "PIPETHOAT", "THOATSAN", "THOATTHAI"]},
    "P-PIPE-VENT": {"color": 165, "discipline": "Plumbing", "description": "Ống thông hơi (Vent Pipe)",
                     "keywords": ["ONGTHONGHOI", "VENTPIPE", "THONGHOI"]},
    "P-PIPE-RAIN": {"color": 166, "discipline": "Plumbing",
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
    "F-SPRINKLER": {"color": 10, "discipline": "Firefighting", "description": "Đầu phun Sprinkler",
                     "keywords": ["DAUPHUNSPRINKLER", "SPRINKLERHEAD", "DAUPHUNCHUACHAY"]},
    "F-PIPE-SPK": {"color": 12, "discipline": "Firefighting", "description": "Ống cấp nước hệ Sprinkler",
                    "keywords": ["ONGSPRINKLER", "SPRINKLERPIPE", "ONGCHUACHAYSPRINKLER"]},
    "F-PIPE-HYD": {"color": 13, "discipline": "Firefighting",
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
    "F-DETECT": {"color": 14, "discipline": "Firefighting", "description": "Đầu báo cháy",
                 "keywords": ["DAUBAOCHAY", "SMOKEDETECTOR", "FIREDETECTOR", "BAOCHAY"]},
    "F-ALARM-DEVICE": {"color": 15, "discipline": "Firefighting",
                        "description": "Chuông / Còi / Đèn báo cháy (Bell/Strobe/Manual Call Point)",
                        "keywords": ["CHUONGBAOCHAY", "COIBAOCHAY", "MANUALCALLPOINT", "FIREBELL", "FIREALARMDEVICE"]},
    "F-GAS-SUPPRESS": {"color": 16, "discipline": "Firefighting",
                        "description": "Hệ thống chữa cháy khí (FM200 / Khí sạch)",
                        "keywords": ["CHUACHAYKHI", "GASSUPPRESSION", "FM200", "CLEANAGENT", "KHISACH"]},
    "F-EXTINGUISHER": {"color": 17, "discipline": "Firefighting", "description": "Bình chữa cháy xách tay",
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

# Đơn vị bóc khối lượng theo thói quen hồ sơ thầu Việt Nam: thiết bị/cấu kiện đơn lẻ
# lắp rời (đèn, ổ cắm, công tắc, đầu phun, đầu báo...) tính "Cái"; cụm thiết bị trọn bộ
# có nhiều phụ kiện đi kèm khi lắp đặt (FCU, bơm, tủ điện...) tính "Bộ". Trước đây
# `auto_quantity_takeoff` (qs_tools.py) gán CỨNG "Bộ" cho MỌI Block bất kể loại, không
# khớp thói quen hồ sơ ngành — nay tra theo `unit` khai báo ở đây, "Bộ" chỉ còn là giá
# trị dự phòng cho Block không nhận diện được.
BLOCK_STANDARD = {
    "DIFFUSER_SUPPLY": {"discipline": "Mechanical", "ma_hieu": "M-DIFF-S", "default_layer": "M-SAD",
                         "description": "Miệng gió cấp (Supply Diffuser)", "unit": "Cái",
                         "keywords": ["MIENGGIOCAP", "SUPPLYDIFFUSER", "DIFFUSERCAP", "GIOCAPSA"]},
    "DIFFUSER_RETURN": {"discipline": "Mechanical", "ma_hieu": "M-DIFF-R", "default_layer": "M-RAD",
                         "description": "Miệng gió hồi (Return Diffuser)", "unit": "Cái",
                         "keywords": ["MIENGGIOHOI", "RETURNDIFFUSER", "DIFFUSERHOI", "GIOHOIRA"]},
    "FCU": {"discipline": "Mechanical", "ma_hieu": "M-FCU", "default_layer": "M-EQUIP-FCU",
            "description": "Dàn lạnh FCU (Fan Coil Unit)", "unit": "Bộ",
            "keywords": ["FANCOILUNIT", "DANLANH"]},
    "LIGHT_PANEL": {"discipline": "Electrical", "ma_hieu": "E-LT-PANEL", "default_layer": "E-LIGHT",
                     "description": "Đèn Panel/Downlight vuông", "unit": "Bộ",
                     "keywords": ["DENPANEL", "PANELLIGHT", "DENOPVUONG"]},
    "LIGHT_DOWNLIGHT": {"discipline": "Electrical", "ma_hieu": "E-LT-DL", "default_layer": "E-LIGHT",
                         "description": "Đèn Downlight âm trần", "unit": "Bộ",
                         "keywords": ["DENDOWNLIGHT", "DOWNLIGHT", "DENAMTRAN"]},
    "SOCKET": {"discipline": "Electrical", "ma_hieu": "E-SOCKET", "default_layer": "E-POWER",
               "description": "Ổ cắm điện", "unit": "Cái",
               "keywords": ["OCAMDIEN", "ELECTRICALOUTLET", "OUTLETSOCKET"]},
    "SWITCH": {"discipline": "Electrical", "ma_hieu": "E-SWITCH", "default_layer": "E-LIGHT-SWITCH",
               "description": "Công tắc đèn", "unit": "Cái",
               "keywords": ["CONGTACDEN", "LIGHTSWITCH"]},
    "SPRINKLER": {"discipline": "Firefighting", "ma_hieu": "F-SPRK", "default_layer": "F-SPRINKLER",
                  "description": "Đầu phun Sprinkler chữa cháy", "unit": "Cái",
                  "keywords": ["DAUPHUNSPRINKLER", "SPRINKLERHEAD"]},
    "PUMP": {"discipline": "Plumbing", "ma_hieu": "P-PUMP", "default_layer": "P-EQUIP-PUMP",
             "description": "Bơm (cấp nước/PCCC tùy hệ bố trí)", "unit": "Bộ",
             "keywords": ["WATERPUMP", "MAYBOM"]},
}


# Tên tiếng Việt cho 9 màu ACI (AutoCAD Color Index) cơ bản 1-9 — đây là 9 màu duy
# nhất có tên chuẩn hóa giống nhau trên mọi bản AutoCAD/ezdxf. Màu mở rộng (10-255,
# dùng cho các hệ ELV/báo cháy cần nhiều màu phân biệt) KHÔNG có tên chuẩn hóa phổ
# quát — cố tình không đoán tên để tránh ghi chú sai, chỉ báo "ACI <n>".
ACI_BASIC_COLOR_NAMES = {
    1: "Đỏ",
    2: "Vàng",
    3: "Lục (xanh lá)",
    4: "Lam nhạt (Cyan)",
    5: "Lam (xanh dương)",
    6: "Tím hồng (Magenta)",
    7: "Trắng/Đen (theo nền)",
    8: "Xám đậm",
    9: "Xám nhạt",
}


def color_name(aci: int) -> str:
    """Tên màu tiếng Việt cho mã màu ACI. Chỉ 9 màu cơ bản (1-9) có tên chuẩn hóa;
    màu mở rộng trả về dạng "ACI <n>" — người dùng cần xem trực tiếp trong CAD."""
    return ACI_BASIC_COLOR_NAMES.get(aci, f"ACI {aci}")


def color_legend_rows() -> list[dict]:
    """Toàn bộ quy chuẩn màu Layer MEPF, nhóm theo discipline (Mechanical > Electrical
    > Plumbing > Firefighting > General), dùng để in bảng chú thích/legend cho khách
    hàng hoặc vẽ trực tiếp vào bản vẽ (xem `add_color_legend` trong `src/tools.py`)."""
    discipline_order = {"Mechanical": 0, "Electrical": 1, "Plumbing": 2, "Firefighting": 3, "General": 4}
    rows = [
        {
            "layer": key,
            "discipline": std["discipline"],
            "description": std["description"],
            "color": std["color"],
            "color_name": color_name(std["color"]),
        }
        for key, std in LAYER_STANDARD.items()
    ]
    rows.sort(key=lambda r: (discipline_order.get(r["discipline"], 9), r["layer"]))
    return rows


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
