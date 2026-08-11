from langchain_core.tools import tool
import math
import logging

logger = logging.getLogger(__name__)

@tool
def calc_water_pipe(fixture_units: float, is_flush_valve: bool = False) -> str:
    """Tính toán lưu lượng (L/s) và cỡ ống (DN) từ Đương lượng thiết bị (FU)."""
    logger.info(f"Calculating Water Pipe: FU={fixture_units}")
    try:
        if is_flush_valve:
            flow_lps = 0.05 * math.pow(fixture_units, 0.65)
        else:
            flow_lps = 0.04 * math.pow(fixture_units, 0.65)
            
        if flow_lps < 0.1: flow_lps = 0.1
        
        v = 1.2
        area = (flow_lps / 1000) / v
        D_mm = math.sqrt(4 * area / math.pi) * 1000
        
        standard_dn = [15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150]
        dn_selected = standard_dn[-1]
        for dn in standard_dn:
            if dn >= D_mm:
                dn_selected = dn
                break
                
        return (f"Tính ống cấp nước (FU = {fixture_units}):\n"
                f"- Lưu lượng thiết kế: {flow_lps:.2f} L/s\n"
                f"- Cỡ ống đề xuất: DN{dn_selected}")
    except Exception as e:
        return f"Lỗi tính ống nước: {e}"

@tool
def calc_water_tank(population: int, liters_per_person: float = 200) -> str:
    """Tính dung tích bể nước ngầm/mái sinh hoạt."""
    logger.info(f"Calculating Water Tank: Pop={population}")
    try:
        daily_req_liters = population * liters_per_person
        daily_req_m3 = daily_req_liters / 1000
        
        underground_m3 = daily_req_m3 * 1.5
        roof_m3 = daily_req_m3 * 0.3
        
        return (f"Tính dung tích bể sinh hoạt (Số người: {population}, Tiêu chuẩn: {liters_per_person} L/người):\n"
                f"- Nhu cầu dùng nước: {daily_req_m3:.1f} m3/ngày\n"
                f"- Bể ngầm (1.5 ngày): {underground_m3:.1f} m3\n"
                f"- Bể mái (0.3 ngày): {roof_m3:.1f} m3")
    except Exception as e:
        return f"Lỗi tính bể nước: {e}"

@tool
def calc_plumbing_pump_head(building_height_m: float, longest_pipe_length_m: float) -> str:
    """Tính cột áp bơm cấp nước (Booster pump / Transfer pump)."""
    logger.info(f"Calculating Plumbing Pump Head")
    try:
        static_head = building_height_m
        friction_head = longest_pipe_length_m * 0.1
        residual_head = 15.0
        total_head = static_head + friction_head + residual_head

        return (f"Tính cột áp bơm cấp nước:\n"
                f"- Chiều cao đẩy tĩnh: {static_head} mH2O\n"
                f"- Tổn thất ma sát: {friction_head:.1f} mH2O\n"
                f"- Cột áp tổng yêu cầu: {total_head:.1f} mH2O (~ {(total_head/10):.1f} bar)")
    except Exception as e:
        return f"Lỗi tính cột áp bơm: {e}"

@tool
def calc_drainage_pipe(dfu: float, override_min_slope_percent: float = 0.0) -> str:
    """
    Tính cỡ ống thoát nước thải (Sanitary Drainage) theo Đương lượng thoát nước
    (DFU - Drainage Fixture Units), tương tự cách `calc_water_pipe` tính cấp nước theo FU.
    Tham số:
    - dfu: Tổng đương lượng thoát nước của các thiết bị vệ sinh trên tuyến (DFU).
    - override_min_slope_percent: Ghi đè độ dốc tối thiểu (%) nếu có yêu cầu riêng; để 0 để dùng
      quy tắc mặc định (DN<=100mm: 2%, DN>100mm: 1%).
    """
    logger.info(f"Calculating Drainage Pipe: DFU={dfu}")
    try:
        # Bảng tra khả năng thoát tối đa theo DN (mm) cho ống nhánh ngang, tham khảo phổ biến
        # trong các tiêu chuẩn thoát nước (dạng đơn giản hóa từ bảng DFU theo cỡ ống).
        standard_dn_capacity = [
            (50, 21), (75, 42), (100, 216), (125, 480), (150, 840), (200, 1920), (250, 3500),
        ]
        dn_selected, capacity = standard_dn_capacity[-1]
        for dn, cap in standard_dn_capacity:
            if cap >= dfu:
                dn_selected, capacity = dn, cap
                break

        min_slope = override_min_slope_percent if override_min_slope_percent > 0 else (2.0 if dn_selected <= 100 else 1.0)

        # Lưu lượng thiết kế xấp xỉ theo tương quan DFU (dạng Hunter's curve đơn giản hóa)
        flow_lps = 0.04 * math.pow(max(dfu, 1), 0.65)

        return (f"Tính ống thoát nước thải (DFU = {dfu}):\n"
                f"- Lưu lượng thiết kế ước tính: {flow_lps:.2f} L/s\n"
                f"- Cỡ ống đề xuất: DN{dn_selected} (khả năng thoát tham khảo: {capacity} DFU)\n"
                f"- Độ dốc tối thiểu: i = {min_slope:.1f}%")
    except Exception as e:
        return f"Lỗi tính ống thoát nước thải: {e}"

@tool
def calc_rainwater_drainage(
    roof_area_m2: float,
    rainfall_intensity_mm_h: float = 100.0,
    runoff_coefficient: float = 1.0,
    max_velocity: float = 1.5,
) -> str:
    """
    Tính lưu lượng và cỡ ống/máng thoát nước mưa mái theo phương pháp Rational (Q = C * i * A / 3600).
    Tham số:
    - roof_area_m2: Diện tích mái/sân thu nước (m2).
    - rainfall_intensity_mm_h: Cường độ mưa thiết kế của khu vực (mm/h, mặc định 100 - cần điều
      chỉnh theo số liệu mưa thực tế của địa phương, ví dụ TCVN 7957/QCVN).
    - runoff_coefficient: Hệ số dòng chảy (C, mặc định 1.0 cho mái không thấm nước).
    - max_velocity: Vận tốc thiết kế trong ống đứng thoát nước mưa (m/s, mặc định 1.5).
    """
    logger.info(f"Calculating Rainwater Drainage: Roof={roof_area_m2}m2, i={rainfall_intensity_mm_h}mm/h")
    try:
        flow_lps = runoff_coefficient * rainfall_intensity_mm_h * roof_area_m2 / 3600

        area_m2 = (flow_lps / 1000) / max_velocity
        diameter_mm = math.sqrt(4 * area_m2 / math.pi) * 1000

        standard_dn = [50, 65, 75, 90, 100, 125, 150, 200, 250, 300]
        dn_selected = standard_dn[-1]
        for dn in standard_dn:
            if dn >= diameter_mm:
                dn_selected = dn
                break

        return (f"Tính thoát nước mưa (Diện tích mái {roof_area_m2} m2, cường độ mưa {rainfall_intensity_mm_h} mm/h):\n"
                f"- Lưu lượng thiết kế: {flow_lps:.2f} L/s\n"
                f"- Cỡ ống đứng/máng thoát đề xuất: DN{dn_selected} (v thiết kế ≤ {max_velocity} m/s)")
    except Exception as e:
        return f"Lỗi tính thoát nước mưa: {e}"

@tool
def calc_septic_tank(
    population: int,
    wastewater_per_person_lpd: float = 150.0,
    retention_days: float = 2.0,
    sludge_accumulation_l_person_year: float = 40.0,
    desludging_interval_years: float = 2.0,
) -> str:
    """
    Tính dung tích bể tự hoại (Septic Tank) theo số người sử dụng, gồm ngăn chứa nước lưu
    và ngăn chứa bùn cặn tích lũy giữa các lần hút bùn định kỳ.
    Tham số:
    - population: Số người sử dụng.
    - wastewater_per_person_lpd: Lưu lượng nước thải mỗi người mỗi ngày (L/người/ngày, mặc định 150).
    - retention_days: Thời gian lưu nước trong bể (ngày, mặc định 2).
    - sludge_accumulation_l_person_year: Tốc độ tích lũy bùn mỗi người mỗi năm (L/người/năm, mặc định 40).
    - desludging_interval_years: Chu kỳ hút bùn định kỳ (năm, mặc định 2).
    """
    logger.info(f"Calculating Septic Tank: Pop={population}")
    try:
        daily_wastewater_m3 = population * wastewater_per_person_lpd / 1000
        v_water_m3 = daily_wastewater_m3 * retention_days
        v_sludge_m3 = population * sludge_accumulation_l_person_year * desludging_interval_years / 1000
        v_total_m3 = v_water_m3 + v_sludge_m3

        return (f"Tính dung tích bể tự hoại (Số người: {population}):\n"
                f"- Lưu lượng nước thải: {daily_wastewater_m3:.2f} m3/ngày\n"
                f"- Ngăn chứa nước (lưu {retention_days} ngày): {v_water_m3:.2f} m3\n"
                f"- Ngăn chứa bùn (chu kỳ hút {desludging_interval_years} năm): {v_sludge_m3:.2f} m3\n"
                f"=> DUNG TÍCH BỂ TỰ HOẠI ĐỀ XUẤT: {v_total_m3:.2f} m3")
    except Exception as e:
        return f"Lỗi tính bể tự hoại: {e}"

@tool
def calc_hot_water_system(
    population: int,
    liters_per_person_per_day: float = 40.0,
    usage_hours: float = 2.0,
    cold_water_temp_c: float = 25.0,
    hot_water_temp_c: float = 60.0,
) -> str:
    """
    Tính công suất bình đun/máy nước nóng trung tâm và dung tích bình chứa đề xuất, dựa trên
    tổng nhu cầu nước nóng trong ngày được dồn về giờ cao điểm sử dụng.
    Tham số:
    - population: Số người sử dụng.
    - liters_per_person_per_day: Nhu cầu nước nóng mỗi người mỗi ngày (L/người/ngày, mặc định 40).
    - usage_hours: Số giờ cao điểm dùng nước nóng cần đáp ứng (giờ, mặc định 2).
    - cold_water_temp_c/hot_water_temp_c: Nhiệt độ nước cấp vào/nước nóng yêu cầu (độ C).
    """
    logger.info(f"Calculating Hot Water System: Pop={population}")
    try:
        daily_demand_liters = population * liters_per_person_per_day
        delta_t = hot_water_temp_c - cold_water_temp_c
        if delta_t <= 0:
            return "Lỗi: Nhiệt độ nước nóng phải lớn hơn nhiệt độ nước cấp vào."

        # Giả định xấu nhất: toàn bộ nhu cầu trong ngày dồn vào khung giờ cao điểm để tính công suất đỉnh
        energy_kj = daily_demand_liters * 4.186 * delta_t
        power_kw = energy_kj / (usage_hours * 3600)

        return (f"Tính hệ thống nước nóng (Số người: {population}, ΔT = {delta_t}°C):\n"
                f"- Tổng nhu cầu nước nóng: {daily_demand_liters:.0f} L/ngày\n"
                f"- Công suất đun đề xuất (dồn trong {usage_hours} giờ cao điểm): {power_kw:.2f} kW\n"
                f"- Dung tích bình chứa đề xuất (hệ thống dạng bình trữ): ~{daily_demand_liters:.0f} L "
                f"(hoặc chọn máy đun tức thời công suất ≥ {power_kw:.2f} kW nếu không dùng bình trữ)")
    except Exception as e:
        return f"Lỗi tính hệ thống nước nóng: {e}"
