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
