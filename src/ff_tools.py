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

@tool
def calc_fire_pump(hazard_class: str = "ordinary") -> str:
    """Tính lưu lượng bơm PCCC sơ bộ."""
    logger.info(f"Calculating Fire Pump: Hazard={hazard_class}")
    try:
        if hazard_class.lower() == "light":
            flow_gpm = 500
        elif hazard_class.lower() == "ordinary":
            flow_gpm = 1000
        else:
            flow_gpm = 1500
            
        flow_lps = flow_gpm * 0.06309
        
        return (f"Tính Cụm bơm PCCC (Nguy cơ {hazard_class}):\n"
                f"- Lưu lượng đề xuất: {flow_gpm} GPM (~ {flow_lps:.1f} L/s)\n"
                f"- Ghi chú: Cần cộng thêm lưu lượng họng vách tường theo TCVN 3890 nếu có.")
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
