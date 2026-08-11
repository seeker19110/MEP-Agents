from langchain_core.tools import tool
import math
import logging

logger = logging.getLogger(__name__)

@tool
def calc_cable_size(power_kw: float, voltage: float = 380, cos_phi: float = 0.85, phase: int = 3) -> str:
    """Tính tiết diện cáp dẫn điện dựa trên công suất phụ tải."""
    logger.info(f"Calculating Cable Size: P={power_kw}kW")
    try:
        if phase == 3:
            current_a = (power_kw * 1000) / (math.sqrt(3) * voltage * cos_phi)
        else:
            voltage = 220
            current_a = (power_kw * 1000) / (voltage * cos_phi)
            
        S_estimate = current_a / 4.0
        standard_cables = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300, 400]
        selected_cable = standard_cables[-1]
        for c in standard_cables:
            if c >= S_estimate:
                selected_cable = c
                break
                
        return (f"Tính cáp điện (P = {power_kw} kW, {phase} pha):\n"
                f"- Dòng điện tính toán (Ib): {current_a:.1f} A\n"
                f"- Đề xuất cáp Cu/XLPE/PVC: {selected_cable} mm2")
    except Exception as e:
        return f"Lỗi tính cáp: {e}"

@tool
def calc_breaker_size(power_kw: float, phase: int = 3) -> str:
    """Tính chọn dòng định mức cho Aptomat (MCB/MCCB) dựa trên công suất."""
    logger.info(f"Calculating Breaker: P={power_kw}kW")
    try:
        cos_phi = 0.85
        voltage = 380 if phase == 3 else 220
        if phase == 3:
            current_a = (power_kw * 1000) / (math.sqrt(3) * voltage * cos_phi)
        else:
            current_a = (power_kw * 1000) / (voltage * cos_phi)
            
        design_current = current_a * 1.25
        standard_breakers = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 320, 400, 500, 630, 800, 1000]
        selected_breaker = standard_breakers[-1]
        for b in standard_breakers:
            if b >= design_current:
                selected_breaker = b
                break
                
        return (f"Tính Aptomat (P = {power_kw} kW):\n"
                f"- Dòng làm việc: {current_a:.1f} A\n"
                f"- Chọn MCCB/MCB định mức: {selected_breaker} A")
    except Exception as e:
        return f"Lỗi tính aptomat: {e}"

@tool
def calc_lighting_qty(area_m2: float, required_lux: float, lumen_per_lamp: float = 3000) -> str:
    """Tính số lượng đèn chiếu sáng bằng phương pháp quang thông."""
    logger.info(f"Calculating Lighting: Area={area_m2}, Lux={required_lux}")
    try:
        UF = 0.6  
        MF = 0.8  
        N = (required_lux * area_m2) / (lumen_per_lamp * UF * MF)
        
        return (f"Tính chiếu sáng (Diện tích {area_m2}m2, Yêu cầu {required_lux} Lux):\n"
                f"- Dùng đèn có quang thông {lumen_per_lamp} Lm\n"
                f"- Số lượng tối thiểu cần thiết: {math.ceil(N)} bộ đèn")
    except Exception as e:
        return f"Lỗi tính đèn: {e}"
