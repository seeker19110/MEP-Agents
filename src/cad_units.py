"""Quy đổi ĐƠN VỊ bản vẽ — mắt xích sai lệch lớn nhất từ bản vẽ tới bảng khối lượng.

Trước module này, `auto_quantity_takeoff` **mặc định coi mọi bản vẽ vẽ bằng mm** và chia
cứng cho 1000 để ra mét. Bản vẽ vẽ bằng mét (INSUNITS=6, khá phổ biến ở hồ sơ hạ tầng và
bản vẽ xuất từ Revit theo đơn vị m) bị chia thêm 1000 lần nữa: tuyến 6 m ra 0.006 m. Tool
có cảnh báo, nhưng cảnh báo không sửa được con số — bảng dự toán vẫn sai và vẫn xuất ra
Excel như thường.

Ở đây đơn vị được **quy đổi thật** thay vì chỉ cảnh báo:

- `$INSUNITS` khai báo rõ đơn vị -> dùng đúng hệ số quy đổi của đơn vị đó.
- `$INSUNITS = 0` (Unitless, rất nhiều file thực tế rơi vào đây) -> suy đoán từ ĐỘ LỚN
  hình học của chính bản vẽ: một mặt bằng MEPF vẽ bằng mm trải hàng chục nghìn đơn vị,
  vẽ bằng mét chỉ vài chục. Suy đoán luôn kèm `confidence` thấp để tool gọi biết mà cảnh
  báo cho kỹ sư xác nhận.
- Người dùng khai `drawing_unit` -> ưu tiên tuyệt đối, vì kỹ sư biết bản vẽ của mình hơn
  cả header (header sai/thiếu là chuyện thường khi file đi qua nhiều lần convert).

Mọi ngưỡng tính bằng mm ở nơi khác (chiều dài cây ống 6000, dung sai nối tuyến, bán kính
gán ghi chú) đều phải nhân với `mm_per_unit` trước khi dùng, nếu không thì đổi đúng chiều
dài mà vẫn suy sai số phụ kiện.
"""
import logging

logger = logging.getLogger(__name__)

# Số MILIMET của một đơn vị bản vẽ, theo mã $INSUNITS trong header DXF.
INSUNITS_TO_MM = {
    1: 25.4,          # Inch
    2: 304.8,         # Feet
    3: 1_609_344.0,   # Mile
    4: 1.0,           # Millimet
    5: 10.0,          # Centimet
    6: 1000.0,        # Met
    7: 1_000_000.0,   # Kilomet
    8: 2.54e-5,       # Microinch
    9: 0.0254,        # Mil
    10: 914.4,        # Yard
    11: 1e-7,         # Angstrom
    12: 1e-6,         # Nanomet
    13: 0.001,        # Micron
    14: 100.0,        # Decimet
    15: 10_000.0,     # Decamet
    16: 100_000.0,    # Hectomet
}

INSUNITS_NAMES = {
    0: "Không xác định (Unitless)", 1: "Inch", 2: "Feet", 3: "Mile", 4: "Millimet (mm)",
    5: "Centimet (cm)", 6: "Met (m)", 7: "Kilomet (km)", 8: "Microinch", 9: "Mil",
    10: "Yard", 11: "Angstrom", 12: "Nanomet", 13: "Micron", 14: "Decimet (dm)",
    15: "Decamet (dam)", 16: "Hectomet (hm)",
}

# Tên đơn vị người dùng gõ tay -> số mm mỗi đơn vị. Nhận cả cách viết tắt thường gặp.
UNIT_ALIASES = {
    "mm": 1.0, "millimet": 1.0, "milimet": 1.0, "millimeter": 1.0,
    "cm": 10.0, "centimet": 10.0, "centimeter": 10.0,
    "dm": 100.0, "decimet": 100.0,
    "m": 1000.0, "met": 1000.0, "meter": 1000.0, "metre": 1000.0,
    "km": 1_000_000.0, "kilomet": 1_000_000.0,
    "inch": 25.4, "in": 25.4, '"': 25.4,
    "ft": 304.8, "feet": 304.8, "foot": 304.8,
    "yd": 914.4, "yard": 914.4,
}

# Ngưỡng suy đoán khi bản vẽ Unitless: kích thước bao (cạnh lớn nhất) của một mặt bằng
# MEPF thực tế nằm trong khoảng vài mét tới vài trăm mét. Quy ra từng đơn vị ứng viên,
# đơn vị nào cho ra kích thước NẰM TRONG khoảng hợp lý thì là ứng viên đúng.
_PLAUSIBLE_EXTENT_M = (2.0, 5000.0)
_UNITLESS_CANDIDATES = (("Millimet (mm)", 1.0), ("Met (m)", 1000.0), ("Centimet (cm)", 10.0))


class DrawingUnit:
    """Đơn vị bản vẽ đã xác định, kèm nguồn gốc và độ tin cậy.

    `mm_per_unit` là hệ số nhân duy nhất cần dùng: mọi chiều dài đọc từ file nhân với nó
    ra milimet, chia thêm 1000 ra mét.
    """

    def __init__(self, mm_per_unit: float, name: str, source: str, confident: bool,
                 suspected: str = ""):
        self.mm_per_unit = float(mm_per_unit)
        self.name = name
        self.source = source
        self.confident = confident
        # Đơn vị mà hình học bản vẽ GỢI Ý, khi khác với đơn vị đang dùng để quy đổi. Chỉ
        # để cảnh báo, không tự áp — xem `detect_drawing_unit`.
        self.suspected = suspected

    @property
    def to_meters(self) -> float:
        """Hệ số nhân đưa một chiều dài theo đơn vị bản vẽ về MÉT."""
        return self.mm_per_unit / 1000.0

    def length_m(self, raw_length: float) -> float:
        """Đổi một chiều dài đo theo đơn vị bản vẽ sang mét."""
        return raw_length * self.to_meters

    def mm(self, millimeters: float) -> float:
        """Đổi một ngưỡng khai báo bằng MILIMET sang đơn vị bản vẽ.

        Dùng cho các hằng số vốn viết theo mm (cây ống 6000 mm, dung sai nối 1 mm): so
        sánh chúng với hình học thô mà quên đổi là suy sai toàn bộ số phụ kiện khi bản
        vẽ không dùng mm.
        """
        return millimeters / self.mm_per_unit

    def __repr__(self):  # pragma: no cover - chỉ phục vụ log
        return f"DrawingUnit({self.name}, {self.mm_per_unit} mm/đơn vị, {self.source})"


def parse_unit_override(text: str):
    """`DrawingUnit` từ tên đơn vị người dùng khai, hoặc None nếu không nhận diện được."""
    if not text:
        return None
    key = str(text).strip().lower()
    mm_per_unit = UNIT_ALIASES.get(key)
    if mm_per_unit is None:
        return None
    return DrawingUnit(mm_per_unit, key, "người dùng khai báo (drawing_unit)", True)


def _drawing_extent(doc) -> float:
    """Cạnh lớn nhất của khung bao bản vẽ, theo đơn vị bản vẽ. 0.0 nếu không xác định."""
    try:
        ext_min = doc.header.get("$EXTMIN", None)
        ext_max = doc.header.get("$EXTMAX", None)
        if ext_min is None or ext_max is None:
            return 0.0
        span = max(abs(ext_max[0] - ext_min[0]), abs(ext_max[1] - ext_min[1]))
        # Header của file chưa từng ZOOM EXTENTS có thể chứa giá trị sentinel khổng lồ.
        return span if 0.0 < span < 1e12 else 0.0
    except Exception:  # pragma: no cover - header dị dạng
        return 0.0


def guess_unit_from_extent(extent: float):
    """Suy đoán đơn vị từ độ lớn hình học khi bản vẽ khai Unitless.

    Trả về `DrawingUnit` (confident=False) hoặc None khi không đủ căn cứ — không đủ căn
    cứ thì phải để hàm gọi tự chọn mặc định và cảnh báo, chứ không đoán bừa.
    """
    if extent <= 0:
        return None
    for name, mm_per_unit in _UNITLESS_CANDIDATES:
        size_m = extent * mm_per_unit / 1000.0
        if _PLAUSIBLE_EXTENT_M[0] <= size_m <= _PLAUSIBLE_EXTENT_M[1]:
            return DrawingUnit(
                mm_per_unit, name,
                f"suy đoán từ kích thước bao bản vẽ (~{size_m:,.0f} m nếu là {name})",
                False,
            )
    return None


def detect_drawing_unit(doc, override: str = "") -> DrawingUnit:
    """Xác định đơn vị bản vẽ theo thứ tự ưu tiên: người dùng khai -> $INSUNITS -> suy đoán.

    Không bao giờ ném lỗi: trường hợp bí nhất vẫn trả về mm (thói quen vẽ MEPF ở Việt Nam)
    với `confident=False` để tool gọi cảnh báo.
    """
    forced = parse_unit_override(override)
    if forced:
        return forced

    try:
        insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    except Exception:  # pragma: no cover - header dị dạng
        insunits = 0

    if insunits in INSUNITS_TO_MM:
        return DrawingUnit(INSUNITS_TO_MM[insunits], INSUNITS_NAMES.get(insunits, str(insunits)),
                           f"header bản vẽ ($INSUNITS={insunits})", True)

    # Bản vẽ Unitless: giữ nguyên quy ước mm của hồ sơ MEPF Việt Nam và CẢNH BÁO, tuyệt
    # đối KHÔNG tự đổi hệ số theo suy đoán. Một suy đoán sai sẽ nhân/chia khối lượng cả
    # nghìn lần mà bảng Excel vẫn ra đủ dòng — nguy hiểm hơn hẳn con số cũ mà kỹ sư đã
    # quen kiểm tra. Suy đoán chỉ được dùng để NÓI cho kỹ sư biết nên nghi ngờ điều gì.
    guessed = guess_unit_from_extent(_drawing_extent(doc))
    suspected = ""
    if guessed and guessed.mm_per_unit != 1.0:
        suspected = f"{guessed.name} ({guessed.source})"

    return DrawingUnit(1.0, "Millimet (mm)",
                       "mặc định theo quy ước MEPF Việt Nam vì bản vẽ khai Unitless",
                       False, suspected=suspected)


def unit_warning(unit: DrawingUnit) -> str:
    """Cảnh báo đặt đầu báo cáo khi đơn vị KHÔNG chắc chắn. Chuỗi rỗng khi đã chắc chắn.

    Đơn vị chắc chắn thì không cần cảnh báo nữa: chiều dài đã được quy đổi ĐÚNG, khác hẳn
    hành vi cũ (cảnh báo suông nhưng vẫn xuất số sai gấp 1000 lần).
    """
    if unit.confident:
        return ""
    text = (
        f"[CẢNH BÁO NGHIÊM TRỌNG] Bản vẽ KHÔNG khai báo đơn vị ($INSUNITS=0). Hệ thống đang "
        f"tạm coi 1 đơn vị bản vẽ = {unit.name} ({unit.source}) và đã quy đổi toàn bộ chiều dài "
        f"theo giả định này. Nếu bản vẽ thực tế vẽ bằng đơn vị khác, MỌI khối lượng ống/dây bên "
        f"dưới sẽ sai theo đúng tỷ lệ chênh lệch."
    )
    if unit.suspected:
        text += (
            f" ĐÁNG NGỜ: kích thước hình học của bản vẽ gợi ý đơn vị thực tế là {unit.suspected} "
            f"— nếu đúng thì khối lượng bên dưới đang sai lệch rất lớn."
        )
    return text + (
        " Hãy xác nhận đơn vị với người vẽ rồi chạy lại tool với tham số `drawing_unit` "
        "(VD drawing_unit='m') trước khi dùng cho hồ sơ thầu."
    )
