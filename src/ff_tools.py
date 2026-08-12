from langchain_core.tools import tool
import math
import logging

logger = logging.getLogger(__name__)

@tool
def calc_sprinkler_qty(area_m2: float, hazard_class: str = "light") -> str:
    """Tính số lượng đầu phun Sprinkler tối thiểu dựa trên diện tích."""
    logger.info(f"Calculating Sprinklers: Area={area_m2}, Hazard={hazard_class}")
    try:
        coverage = 12.0
        if hazard_class.lower() == "light":
            coverage = 12.0
        elif hazard_class.lower() == "ordinary":
            coverage = 9.0
        elif hazard_class.lower() == "extra":
            coverage = 6.0
            
        qty = math.ceil(area_m2 / coverage)
        return (f"Tính đầu phun Sprinkler ({area_m2} m2, Nguy cơ {hazard_class}):\n"
                f"- Diện tích bảo vệ mỗi đầu: {coverage} m2/đầu\n"
                f"- Số lượng tối thiểu: {qty} đầu")
    except Exception as e:
        return f"Lỗi tính sprinkler: {e}"

# Áp suất làm việc tối thiểu tại đầu phun bất lợi nhất (bar), TCVN 7336.
SPRINKLER_MIN_PRESSURE_BAR = 0.5
# Áp suất tối thiểu tại họng nước vách tường (bar), TCVN 3890.
HYDRANT_MIN_PRESSURE_BAR = 2.0


@tool
def calc_fire_pump(hazard_class: str = "ordinary", static_head_m: float = 0,
                   pipe_length_m: float = 0, has_hydrant: bool = False,
                   friction_loss_per_100m: float = 5.0) -> str:
    """Chọn bơm chữa cháy: tính CẢ lưu lượng Q và cột áp H (đủ dữ liệu để chọn bơm thật).

    - static_head_m: chiều cao hình học từ bể/hút bơm tới đầu phun bất lợi nhất (m).
    - pipe_length_m: tổng chiều dài tuyến ống tới điểm bất lợi nhất (m).
    - has_hydrant: có họng nước vách tường hay không (quyết định áp yêu cầu tại đầu ra).
    - friction_loss_per_100m: tổn thất ma sát đường ống (m cột nước / 100 m ống).
    """
    logger.info(f"Calculating Fire Pump: Hazard={hazard_class}, H_static={static_head_m}m")
    try:
        if hazard_class.lower() == "light":
            flow_gpm = 500
        elif hazard_class.lower() == "ordinary":
            flow_gpm = 1000
        else:
            flow_gpm = 1500

        flow_lps = flow_gpm * 0.06309
        flow_m3h = flow_lps * 3.6

        report = [
            f"Chọn Cụm bơm PCCC (Nguy cơ {hazard_class}):",
            f"- Lưu lượng Q: {flow_gpm} GPM (~ {flow_lps:.1f} L/s ~ {flow_m3h:.1f} m3/h)",
        ]

        if static_head_m <= 0 and pipe_length_m <= 0:
            report.append(
                "- CẢNH BÁO: Chưa có chiều cao hình học (static_head_m) và chiều dài tuyến ống "
                "(pipe_length_m) nên CHƯA tính được cột áp H. Thiếu H thì KHÔNG thể chọn bơm thực tế "
                "— hãy hỏi lại hai thông số này rồi tính lại."
            )
            return "\n".join(report)

        # H = cột áp hình học + tổn thất ma sát (+ tổn thất cục bộ 20%) + áp yêu cầu tại đầu ra
        friction_m = pipe_length_m * friction_loss_per_100m / 100.0
        local_loss_m = friction_m * 0.20
        required_bar = HYDRANT_MIN_PRESSURE_BAR if has_hydrant else SPRINKLER_MIN_PRESSURE_BAR
        required_m = required_bar * 10.2
        total_head_m = static_head_m + friction_m + local_loss_m + required_m

        report += [
            f"- Cột áp hình học (Hhh): {static_head_m:.1f} m",
            f"- Tổn thất ma sát đường ống ({pipe_length_m:.0f} m x {friction_loss_per_100m} m/100m): {friction_m:.1f} m",
            f"- Tổn thất cục bộ (co, tê, van - lấy 20% ma sát): {local_loss_m:.1f} m",
            f"- Áp yêu cầu tại điểm bất lợi nhất: {required_bar:.1f} bar (~ {required_m:.1f} m) "
            f"[{'họng vách tường, TCVN 3890' if has_hydrant else 'đầu phun sprinkler, TCVN 7336'}]",
            f"- CỘT ÁP BƠM YÊU CẦU (H): {total_head_m:.1f} m",
            f"=> Chọn bơm chữa cháy: Q ~ {flow_m3h:.1f} m3/h, H ~ {total_head_m:.1f} m "
            f"(chọn bơm catalog có điểm làm việc bao trùm điểm này).",
            "- Ghi chú: Cần bơm bù áp (jockey) và bơm dự phòng động cơ diesel theo TCVN 3890.",
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính bơm PCCC: {e}"

@tool
def calc_extinguisher_qty(area_m2: float) -> str:
    """Bố trí số lượng bình chữa cháy xách tay."""
    logger.info(f"Calculating Extinguishers: Area={area_m2}")
    try:
        qty = math.ceil(area_m2 / 50.0)
        return (f"Bố trí bình chữa cháy ({area_m2} m2):\n"
                f"- Tiêu chuẩn: 50 m2/bình\n"
                f"- Số lượng: {qty} bình (kết hợp bình bột ABC và khí CO2)")
    except Exception as e:
        return f"Lỗi tính bình chữa cháy: {e}"


# --- Thủy lực mạng sprinkler ---

# Cường độ phun và diện tích tính toán theo TCVN 7336 (nhóm nguy cơ cháy).
SPRINKLER_DESIGN_DENSITY = {
    "light": (0.08, 120),      # l/s/m2, diện tích tính toán m2
    "ordinary": (0.12, 240),
    "extra": (0.24, 360),
}

# Hệ số lưu lượng K của đầu phun (l/min/bar^0.5) — K80 là loại phổ biến nhất.
SPRINKLER_K_FACTOR = 80.0


@tool
def calc_sprinkler_hydraulics(hazard_class: str = "ordinary", num_sprinklers: int = 0,
                              pipe_length_m: float = 50.0, pipe_diameter_mm: float = 50.0,
                              k_factor: float = SPRINKLER_K_FACTOR,
                              start_pressure_bar: float = SPRINKLER_MIN_PRESSURE_BAR) -> str:
    """Tính THỦY LỰC mạng đầu phun sprinkler: lưu lượng và áp suất tại từng đầu theo đường ống.

    Khác với `calc_sprinkler_qty` (chỉ ước tính số đầu theo diện tích bao phủ), tool này
    tính lưu lượng thật của mạng: đầu phun ở xa nhất chịu áp thấp nhất, các đầu gần bơm
    hơn có áp cao hơn nên phun nhiều nước hơn — tổng lưu lượng vì thế lớn hơn phép nhân
    đơn giản (số đầu x lưu lượng một đầu).

    - num_sprinklers: số đầu phun trong diện tích tính toán; để 0 thì tự suy từ TCVN 7336.
    - pipe_diameter_mm: đường kính ống nhánh nối các đầu phun.
    - start_pressure_bar: áp tại đầu phun bất lợi nhất (xa nhất).
    """
    logger.info(f"Calculating sprinkler hydraulics: hazard={hazard_class}, n={num_sprinklers}")
    try:
        key = hazard_class.lower().strip()
        density, design_area = SPRINKLER_DESIGN_DENSITY.get(key, SPRINKLER_DESIGN_DENSITY["ordinary"])

        coverage_per_head = {"light": 12.0, "ordinary": 9.0, "extra": 6.0}.get(key, 9.0)
        if num_sprinklers <= 0:
            num_sprinklers = math.ceil(design_area / coverage_per_head)

        if pipe_diameter_mm <= 0:
            return "Lỗi: Đường kính ống phải lớn hơn 0."

        # Duyệt từ đầu phun XA NHẤT về phía nguồn: mỗi đoạn ống làm tăng áp cho đầu kế tiếp.
        spacing = pipe_length_m / max(1, num_sprinklers)
        pressure_bar = start_pressure_bar
        cumulative_flow_lpm = 0.0
        rows = []
        for i in range(1, num_sprinklers + 1):
            flow_lpm = k_factor * math.sqrt(max(pressure_bar, 0.01))
            cumulative_flow_lpm += flow_lpm
            rows.append((i, pressure_bar, flow_lpm, cumulative_flow_lpm))

            # Tổn thất ma sát Hazen-Williams cho đoạn tới đầu kế tiếp, C = 120 (thép đen).
            q_m3s = cumulative_flow_lpm / 60000.0
            d_m = pipe_diameter_mm / 1000.0
            head_loss_m = (10.67 * spacing * (q_m3s ** 1.852)) / ((120 ** 1.852) * (d_m ** 4.87))
            pressure_bar += head_loss_m / 10.2

        total_flow_lps = cumulative_flow_lpm / 60.0
        required_flow_lps = density * design_area

        report = [
            f"THỦY LỰC MẠNG SPRINKLER (nguy cơ {hazard_class}, TCVN 7336):",
            f"- Cường độ phun yêu cầu: {density} l/s/m2 trên diện tích tính toán {design_area} m2",
            f"- Số đầu phun trong diện tích tính toán: {num_sprinklers} đầu (K={k_factor})",
            f"- Áp tại đầu phun bất lợi nhất: {start_pressure_bar} bar",
            "",
            "PHÂN BỐ ÁP SUẤT / LƯU LƯỢNG (từ đầu xa nhất về nguồn):",
        ]
        for i, p, q, cum in rows[:10]:
            report.append(f"  Đầu {i}: áp {p:.2f} bar, lưu lượng {q:.1f} l/ph, cộng dồn {cum:.1f} l/ph")
        if len(rows) > 10:
            report.append(f"  ... và {len(rows) - 10} đầu khác.")

        report += [
            "",
            f"- Áp yêu cầu tại đầu vào mạng: {pressure_bar:.2f} bar",
            f"- TỔNG LƯU LƯỢNG mạng: {cumulative_flow_lpm:.0f} l/ph = {total_flow_lps:.1f} l/s",
            f"- Lưu lượng tối thiểu theo cường độ phun: {required_flow_lps:.1f} l/s",
        ]
        if total_flow_lps >= required_flow_lps:
            report.append("- Kết luận: ĐẠT cường độ phun yêu cầu.")
        else:
            report.append("- Kết luận: KHÔNG ĐẠT — cần tăng áp tại đầu phun bất lợi nhất, "
                          "tăng đường kính ống hoặc dùng đầu phun hệ số K lớn hơn.")
        report.append(f"- Dùng Q = {total_flow_lps:.1f} l/s và áp đầu mạng {pressure_bar:.2f} bar làm "
                      f"đầu vào cho `calc_fire_pump` để chọn bơm.")
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính thủy lực sprinkler: {e}"


@tool
def calc_standpipe(num_floors: int, floor_height_m: float = 3.5, num_hydrants_per_floor: int = 2,
                   flow_per_hydrant_lps: float = 2.5, simultaneous_hydrants: int = 2,
                   pipe_length_m: float = 0) -> str:
    """Tính hệ họng nước vách tường / ống đứng chữa cháy (standpipe) theo TCVN 3890.

    Trả về lưu lượng tính toán, cột áp yêu cầu và đường kính ống đứng.
    - simultaneous_hydrants: số họng hoạt động đồng thời (TCVN thường lấy 2 cho nhà dân dụng).
    """
    logger.info(f"Calculating standpipe: {num_floors} floors")
    try:
        if num_floors <= 0:
            return "Lỗi: Số tầng phải lớn hơn 0."

        building_height = num_floors * floor_height_m
        total_hydrants = num_floors * num_hydrants_per_floor
        design_flow_lps = simultaneous_hydrants * flow_per_hydrant_lps
        design_flow_m3h = design_flow_lps * 3.6

        # Đường kính ống đứng theo vận tốc cho phép 2.5 m/s.
        velocity = 2.5
        d_m = math.sqrt(4 * (design_flow_lps / 1000) / (math.pi * velocity))
        standard_dn = [50, 65, 80, 100, 125, 150, 200]
        selected_dn = next((d for d in standard_dn if d >= d_m * 1000), standard_dn[-1])

        length = pipe_length_m if pipe_length_m > 0 else building_height * 1.3
        friction_m = length * 5.0 / 100.0
        required_m = HYDRANT_MIN_PRESSURE_BAR * 10.2
        total_head = building_height + friction_m + friction_m * 0.2 + required_m

        return "\n".join([
            f"HỆ HỌNG NƯỚC VÁCH TƯỜNG / ỐNG ĐỨNG ({num_floors} tầng, cao {building_height:.1f} m):",
            f"- Tổng số họng: {total_hydrants} họng ({num_hydrants_per_floor} họng/tầng)",
            f"- Số họng tính toán hoạt động đồng thời: {simultaneous_hydrants} họng",
            f"- Lưu lượng tính toán: {design_flow_lps:.1f} l/s ({design_flow_m3h:.1f} m3/h)",
            f"- Đường kính ống đứng (vận tốc {velocity} m/s): DN{selected_dn}",
            "",
            "CỘT ÁP YÊU CẦU:",
            f"- Cột áp hình học (chiều cao nhà): {building_height:.1f} m",
            f"- Tổn thất ma sát + cục bộ trên {length:.0f} m ống: {friction_m * 1.2:.1f} m",
            f"- Áp tại đầu lăng phun: {HYDRANT_MIN_PRESSURE_BAR} bar ({required_m:.1f} m)",
            f"=> CỘT ÁP YÊU CẦU: {total_head:.1f} m",
            f"=> Chọn bơm: Q ~ {design_flow_m3h:.1f} m3/h, H ~ {total_head:.1f} m",
            "- Lưu ý: Nhà trên 10 tầng cần chia vùng áp lực (áp tại họng thấp nhất không vượt "
            "4 bar theo TCVN 3890, nếu vượt phải lắp van giảm áp). Ống đứng phải có họng tiếp "
            "nước cho xe chữa cháy ở tầng trệt.",
        ])
    except Exception as e:
        return f"Lỗi tính họng nước vách tường: {e}"


@tool
def calc_smoke_control(area_m2: float, height_m: float, system_type: str = "hut_khoi",
                       num_doors: int = 2, door_area_m2: float = 1.6) -> str:
    """Tính quạt TĂNG ÁP cầu thang hoặc quạt HÚT KHÓI hành lang theo QCVN 06:2022/BXD.

    - system_type: 'tang_ap' (tăng áp buồng thang/giếng thang) hoặc 'hut_khoi' (hút khói
      hành lang, tầng hầm).
    - num_doors / door_area_m2: dùng cho hệ tăng áp — số cửa mở đồng thời khi thoát nạn.
    """
    logger.info(f"Calculating smoke control: type={system_type}, area={area_m2}")
    try:
        kind = (system_type or "hut_khoi").lower().strip()

        if kind.startswith("tang_ap"):
            # Tăng áp: giữ chênh áp 20-50 Pa, cấp đủ gió cho cửa mở với vận tốc 1.3 m/s.
            target_pressure = 50.0
            door_velocity = 1.3
            flow_open_doors = num_doors * door_area_m2 * door_velocity      # m3/s
            leakage_area = area_m2 * 0.0002                                  # hệ số rò rỉ khe cửa
            flow_leakage = 0.83 * leakage_area * math.sqrt(target_pressure)  # m3/s
            total_flow = (flow_open_doors + flow_leakage) * 1.2              # dự phòng 20%
            total_m3h = total_flow * 3600

            return "\n".join([
                "QUẠT TĂNG ÁP BUỒNG THANG (QCVN 06:2022/BXD):",
                f"- Chênh áp yêu cầu: 20 - {target_pressure:.0f} Pa so với khu vực kề cận",
                f"- Lưu lượng qua {num_doors} cửa mở ({door_area_m2} m2/cửa, v = {door_velocity} m/s): "
                f"{flow_open_doors:.2f} m3/s",
                f"- Lưu lượng bù rò rỉ khe cửa: {flow_leakage:.2f} m3/s",
                f"=> LƯU LƯỢNG QUẠT TĂNG ÁP: {total_flow:.2f} m3/s = {total_m3h:.0f} m3/h (đã cộng 20% dự phòng)",
                "- Phải có van xả áp (relief damper) để chênh áp không vượt 50 Pa, nếu vượt thì "
                "lực mở cửa quá lớn, người thoát nạn không mở nổi cửa.",
                "- Quạt tăng áp phải cấp nguồn điện ưu tiên và tự khởi động khi có tín hiệu báo cháy.",
            ])

        # Hút khói: bội số trao đổi không khí theo QCVN 06 (thường 6-10 ACH cho hành lang).
        volume = area_m2 * height_m
        ach = 10.0
        flow_m3h = volume * ach
        smoke_velocity = 1.0
        duct_area = (flow_m3h / 3600) / smoke_velocity if smoke_velocity else 0
        make_up_m3h = flow_m3h * 0.8   # gió bù tối thiểu 80% lưu lượng hút

        return "\n".join([
            f"QUẠT HÚT KHÓI (QCVN 06:2022/BXD) — khu vực {area_m2} m2, cao {height_m} m:",
            f"- Thể tích khu vực: {volume:.0f} m3",
            f"- Bội số hút khói: {ach:.0f} lần/giờ",
            f"=> LƯU LƯỢNG QUẠT HÚT KHÓI: {flow_m3h:.0f} m3/h",
            f"- Tiết diện ống hút (vận tốc {smoke_velocity} m/s): {duct_area:.2f} m2",
            f"- Lưu lượng GIÓ BÙ tối thiểu: {make_up_m3h:.0f} m3/h (thiếu gió bù thì quạt hút "
            f"không đạt lưu lượng thiết kế)",
            "- Quạt hút khói phải chịu được 400°C trong 60 phút (hoặc 300°C/60 phút tùy hạng mục), "
            "ống gió hút khói phải có giới hạn chịu lửa theo QCVN 06.",
            "- Van ngăn cháy trên tuyến phải tự đóng khi có cháy ở khu vực không thuộc vùng hút.",
        ])
    except Exception as e:
        return f"Lỗi tính hệ thống kiểm soát khói: {e}"


@tool
def calc_fire_detector_qty(area_m2: float, height_m: float = 3.0, detector_type: str = "khoi",
                           room_shape: str = "thuong") -> str:
    """Tính số lượng đầu báo khói/nhiệt và khoảng cách bố trí theo TCVN 5738.

    - detector_type: 'khoi' (đầu báo khói) hoặc 'nhiet' (đầu báo nhiệt).
    - height_m: chiều cao trần — trần càng cao thì diện tích bảo vệ mỗi đầu càng giảm.
    """
    logger.info(f"Calculating fire detectors: area={area_m2}, h={height_m}, type={detector_type}")
    try:
        is_smoke = (detector_type or "khoi").lower().strip().startswith("kh")

        # Diện tích bảo vệ một đầu báo theo chiều cao trần (TCVN 5738).
        if is_smoke:
            if height_m <= 3.5:
                coverage, spacing = 85.0, 9.0
            elif height_m <= 6.0:
                coverage, spacing = 70.0, 8.5
            elif height_m <= 10.0:
                coverage, spacing = 65.0, 8.0
            else:
                coverage, spacing = 55.0, 7.5
            label = "đầu báo KHÓI"
        else:
            if height_m <= 3.5:
                coverage, spacing = 25.0, 5.0
            elif height_m <= 6.0:
                coverage, spacing = 20.0, 4.5
            else:
                coverage, spacing = 15.0, 4.0
            label = "đầu báo NHIỆT"

        qty = max(1, math.ceil(area_m2 / coverage))
        wall_distance = spacing / 2

        report = [
            f"BỐ TRÍ {label} (TCVN 5738) — diện tích {area_m2} m2, trần cao {height_m} m:",
            f"- Diện tích bảo vệ một đầu: {coverage:.0f} m2",
            f"- SỐ LƯỢNG CẦN THIẾT: {qty} đầu",
            f"- Khoảng cách giữa các đầu: tối đa {spacing:.1f} m",
            f"- Khoảng cách từ đầu báo tới tường: tối đa {wall_distance:.1f} m",
            "- Khoảng cách tối thiểu tới miệng gió điều hòa: 1.0 m (gió thổi làm loãng khói, "
            "đầu báo chậm tác động)",
        ]
        if height_m > 12 and is_smoke:
            report.append("- CẢNH BÁO: Trần cao trên 12 m thì đầu báo khói điểm không còn hiệu quả — "
                          "phải dùng đầu báo khói kiểu hút (aspirating) hoặc báo cháy tia chiếu (beam).")
        if (room_shape or "").lower().startswith("hanh"):
            report.append("- Hành lang hẹp (rộng dưới 3 m): bố trí theo hàng dọc, khoảng cách giữa các "
                          "đầu tối đa 15 m với đầu báo khói.")
        report.append("- Mỗi phòng riêng biệt phải có tối thiểu 1 đầu báo, kể cả phòng rất nhỏ.")
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính đầu báo cháy: {e}"


# Nồng độ thiết kế tối thiểu (%) và hệ số thể tích riêng hơi bão hòa s = s0 + k*T (m3/kg) theo
# NFPA 2001, tại nhiệt độ thiết kế T (°C). Đơn giản hóa cho 2 loại khí sạch phổ biến nhất.
GAS_AGENT_DATA = {
    "fm200": {"design_conc": 7.0, "s0": 0.1373, "k": 0.0006, "label": "FM-200 (HFC-227ea)"},
    "novec1230": {"design_conc": 4.7, "s0": 0.0664, "k": 0.000274, "label": "Novec 1230"},
}
# CO2 dùng bảng hệ số ngập tràn (flooding factor, kg/m3) theo NFPA 12 — đơn giản hóa 1 mức trung
# bình cho không gian kín (phòng máy chủ/phòng điện), thực tế còn phụ thuộc thể tích/tỷ lệ diện
# tích mở nên cần tra bảng chi tiết khi thiết kế chính thức.
CO2_FLOODING_FACTOR_KG_M3 = 1.0


@tool
def calc_gas_suppression(room_volume_m3: float, agent_type: str = "fm200",
                         design_temp_c: float = 20.0) -> str:
    """
    Tính lượng khí chữa cháy sạch (Clean Agent) cần thiết cho hệ thống chữa cháy khí tổng
    ngập (Total Flooding) — dùng cho phòng máy chủ, phòng điện, phòng UPS, kho lưu trữ dữ
    liệu... nơi KHÔNG thể dùng nước (sprinkler làm hỏng thiết bị điện tử). Đây là hạng mục
    hay bị bỏ sót khi PCCC chỉ thiết kế sprinkler/hydrant mà quên các phòng kỹ thuật đặc thù
    bắt buộc dùng khí sạch theo NFPA 2001/TCVN 7161.
    Tham số:
    - room_volume_m3: Thể tích phòng cần bảo vệ (m3).
    - agent_type: 'fm200', 'novec1230', hoặc 'co2'. CO2 gây ngạt chết người ở nồng độ chữa
      cháy nên chỉ dùng cho không gian không có người thường trực, có quy trình sơ tán/khóa
      liên động nghiêm ngặt.
    - design_temp_c: Nhiệt độ thiết kế trong phòng (°C, mặc định 20).
    """
    logger.info(f"Calculating Gas Suppression: V={room_volume_m3}m3, agent={agent_type}")
    try:
        if room_volume_m3 <= 0:
            return "Lỗi: Thể tích phòng phải lớn hơn 0."

        key = (agent_type or "fm200").lower().strip()
        report = [f"HỆ CHỮA CHÁY KHÍ TỔNG NGẬP (Total Flooding) — thể tích phòng {room_volume_m3} m3:"]

        if key == "co2":
            weight_kg = room_volume_m3 * CO2_FLOODING_FACTOR_KG_M3
            report += [
                f"- Chất chữa cháy: CO2 (nồng độ thiết kế tham khảo ~34%, hệ số ngập tràn đơn giản "
                f"hóa {CO2_FLOODING_FACTOR_KG_M3} kg/m3 theo NFPA 12)",
                f"=> KHỐI LƯỢNG CO2 CẦN THIẾT: {weight_kg:.1f} kg",
                "- CẢNH BÁO AN TOÀN: CO2 ở nồng độ chữa cháy GÂY NGẠT CHẾT NGƯỜI. Bắt buộc có chuông/"
                "đèn cảnh báo trước xả (time delay 20-60s), khóa liên động ngừng thông gió/đóng van "
                "gió, và quy trình sơ tán toàn bộ nhân sự trước khi khí xả — TCVN 7161-1/NFPA 12.",
            ]
        else:
            agent = GAS_AGENT_DATA.get(key, GAS_AGENT_DATA["fm200"])
            s = agent["s0"] + agent["k"] * design_temp_c
            conc = agent["design_conc"]
            weight_kg = (room_volume_m3 / s) * (conc / (100.0 - conc))
            report += [
                f"- Chất chữa cháy: {agent['label']} (nồng độ thiết kế {conc}%, thể tích riêng hơi "
                f"s = {s:.4f} m3/kg tại {design_temp_c}°C)",
                f"=> KHỐI LƯỢNG {agent['label'].upper()} CẦN THIẾT: {weight_kg:.1f} kg",
                "- Thời gian xả khí: TỐI ĐA 10 giây (halocarbon agent) để đạt nồng độ thiết kế trước "
                "khi cháy lan rộng — NFPA 2001.",
                "- BẮT BUỘC kiểm tra độ kín phòng (door fan test) sau thi công để đảm bảo nồng độ "
                "khí duy trì đủ thời gian giữ (hold time) tối thiểu 10 phút, tránh rò rỉ qua khe hở "
                "cửa/sàn nâng/trần giả.",
            ]

        report += [
            "- Hệ khí sạch KHÔNG thay thế đầu báo cháy — vẫn cần đầu báo khói độ nhạy cao "
            "(`calc_fire_detector_qty`) để kích hoạt xả khí tự động.",
            "- Với phòng có người thường trực, ưu tiên FM-200/Novec 1230 (an toàn với người ở nồng "
            "độ thiết kế) thay vì CO2.",
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính hệ chữa cháy khí: {e}"


# Thời gian dự trữ nước chữa cháy tối thiểu (giờ) theo nhóm nguy cơ, tham khảo NFPA 13/TCVN 3890
# (giá trị đơn giản hóa — công trình có yêu cầu pháp lý cụ thể cần đối chiếu hồ sơ thẩm duyệt PCCC).
FIRE_WATER_DURATION_HOURS = {"light": 1.0, "ordinary": 1.5, "extra": 2.0}


@tool
def calc_fire_water_tank(hazard_class: str = "ordinary", sprinkler_flow_lps: float = 0.0,
                         hydrant_flow_lps: float = 0.0, duration_hours: float = 0.0) -> str:
    """
    Tính dung tích bể/bồn dự trữ nước chữa cháy — hạng mục hay bị bỏ sót khi đã tính bơm PCCC
    (`calc_fire_pump`/`calc_standpipe`) nhưng quên tính LƯỢNG NƯỚC dự trữ đủ cho thời gian
    chữa cháy yêu cầu (bơm đủ công suất nhưng bể cạn nước sau vài phút thì vô nghĩa).
    Tham số:
    - hazard_class: 'light', 'ordinary', hoặc 'extra' — quyết định thời gian dự trữ mặc định
      nếu không truyền duration_hours.
    - sprinkler_flow_lps: Lưu lượng thiết kế hệ sprinkler (L/s) — lấy từ `calc_sprinkler_hydraulics`.
    - hydrant_flow_lps: Lưu lượng thiết kế hệ họng nước vách tường (L/s) — lấy từ `calc_standpipe`.
    - duration_hours: Ghi đè thời gian dự trữ (giờ) nếu có yêu cầu riêng từ hồ sơ thẩm duyệt
      PCCC; để 0 dùng mặc định theo hazard_class.
    """
    logger.info(f"Calculating Fire Water Tank: hazard={hazard_class}")
    try:
        if sprinkler_flow_lps <= 0 and hydrant_flow_lps <= 0:
            return ("Lỗi: Cần ít nhất một trong hai lưu lượng (sprinkler_flow_lps hoặc "
                    "hydrant_flow_lps) để tính dung tích bể — lấy từ `calc_sprinkler_hydraulics` "
                    "hoặc `calc_standpipe` trước.")

        duration = duration_hours if duration_hours > 0 else FIRE_WATER_DURATION_HOURS.get(
            (hazard_class or "ordinary").lower().strip(), 1.5)
        total_flow_lps = sprinkler_flow_lps + hydrant_flow_lps
        volume_m3 = total_flow_lps * 3600 * duration / 1000.0

        lines = [f"Tính dung tích bể dự trữ nước chữa cháy (nguy cơ {hazard_class}):"]
        if sprinkler_flow_lps > 0:
            lines.append(f"- Lưu lượng sprinkler: {sprinkler_flow_lps:.1f} L/s")
        if hydrant_flow_lps > 0:
            lines.append(f"- Lưu lượng họng nước vách tường: {hydrant_flow_lps:.1f} L/s")

        return "\n".join(lines + [
            f"- Tổng lưu lượng thiết kế: {total_flow_lps:.1f} L/s",
            f"- Thời gian dự trữ yêu cầu: {duration:.1f} giờ",
            f"=> DUNG TÍCH BỂ NƯỚC CHỮA CHÁY ĐỀ XUẤT: {volume_m3:.1f} m3",
            "- Bể nước chữa cháy PHẢI TÁCH RIÊNG khỏi bể nước sinh hoạt (hoặc dùng ngăn riêng có "
            "van một chiều/ống hút riêng), không được để nước sinh hoạt tiêu hao làm cạn phần dự "
            "trữ chữa cháy — đây là lỗi hay gặp khi dùng chung một bể cho cả hai mục đích.",
            "- Vị trí đặt bơm PCCC phải đảm bảo cột hút dương (bể luôn cao hơn hoặc bằng miệng hút "
            "bơm) — nếu bể ngầm sâu hơn bơm, cần bơm mồi hoặc bố trí bơm chìm.",
        ])
    except Exception as e:
        return f"Lỗi tính bể nước chữa cháy: {e}"
