from langchain_core.tools import tool
import CoolProp.HumidAirProp as HA
import math
import logging

logger = logging.getLogger(__name__)

@tool
def calc_psychrometrics(T_drybulb: float, RH: float) -> str:
    """
    Tính toán trạng thái không khí ẩm (Psychrometrics) tại áp suất khí quyển chuẩn.
    Tham số:
    - T_drybulb: Nhiệt độ bầu khô (độ C)
    - RH: Độ ẩm tương đối (%, ví dụ: 50 cho 50%)
    Trả về: Entanpi (kJ/kg), Độ ẩm tuyệt đối (g/kg), Nhiệt độ đọng sương (Dew point).
    Rất cần thiết để tính công suất lạnh.
    """
    logger.info(f"Calculating Psychrometrics: T={T_drybulb}°C, RH={RH}%")
    try:
        T_K = T_drybulb + 273.15
        P_atm = 101325  # Pa
        
        h = HA.HAPropsSI('H', 'T', T_K, 'P', P_atm, 'R', RH/100) / 1000
        w = HA.HAPropsSI('W', 'T', T_K, 'P', P_atm, 'R', RH/100) * 1000
        tdpw = HA.HAPropsSI('D', 'T', T_K, 'P', P_atm, 'R', RH/100) - 273.15
        
        return f"Kết quả trạng thái không khí (T={T_drybulb}°C, RH={RH}%):\n- Entanpi: {h:.2f} kJ/kg\n- Độ ẩm tuyệt đối: {w:.2f} g/kg\n- Nhiệt độ đọng sương: {tdpw:.2f} °C"
    except Exception as e:
        return f"Lỗi tính toán Psychrometrics: {e}"

@tool
def calc_duct_size(airflow_lps: float, max_velocity: float = 8.0, max_friction: float = 1.0) -> str:
    """
    Nội suy kích thước ống gió. 
    Tham số:
    - airflow_lps: Lưu lượng gió (L/s).
    - max_velocity: Vận tốc gió tối đa (m/s).
    - max_friction: Tổn thất ma sát tối đa (Pa/m).
    Trả về đường kính ống tròn và các tùy chọn kích thước ống chữ nhật (W x H) khả thi.
    """
    logger.info(f"Calculating Duct Size: Q={airflow_lps} L/s")
    try:
        Q = airflow_lps / 1000.0  # m3/s
        if Q <= 0: return "Lưu lượng phải lớn hơn 0."
        
        area = Q / max_velocity
        D_vel = math.sqrt(4 * area / math.pi) * 1000 
        D_round = max(int(D_vel), 100)
        
        rect_options = []
        for H in [150, 200, 250, 300, 400, 500, 600, 800]:
            if H < D_round * 1.5:
                W = (area * 1e6) / H
                if W >= H and W <= H * 4: 
                    rect_options.append(f"{int(W)}x{H}")
                    
        res = f"Kích thước Ống gió cho Lưu lượng {airflow_lps} L/s (v={max_velocity}m/s):\n"
        res += f"- Ống tròn tối thiểu: Ø{D_round:.0f} mm\n"
        if rect_options:
            res += f"- Các ống chữ nhật gợi ý (W x H): " + " hoặc ".join(rect_options) + "\n"
        
        return res
    except Exception as e:
        return f"Lỗi nội suy ống gió: {e}"

@tool
def calc_cooling_load(area_m2: float, space_type: str = "van_phong") -> str:
    """
    Ước tính tải lạnh sơ bộ dựa trên diện tích.
    Tham số:
    - area_m2: Diện tích phòng (m2).
    - space_type: "van_phong", "hoi_truong", "nha_hang", "server_room".
    Trả về công suất lạnh.
    """
    logger.info(f"Calculating Cooling Load: {area_m2} m2, {space_type}")
    try:
        factors = {"van_phong": 200, "hoi_truong": 250, "nha_hang": 300, "server_room": 600}
        factor = factors.get(space_type.lower(), 200)
        load_W = area_m2 * factor
        load_kW = load_W / 1000
        load_Btu = load_W * 3.412
        load_hp = load_Btu / 9000
        
        return (f"Tải lạnh cho '{space_type}' ({area_m2} m2):\n"
                f"- Hệ số: {factor} W/m2 => Tổng: {load_kW:.2f} kW (~ {load_Btu:.0f} Btu/h, {load_hp:.1f} HP)")
    except Exception as e:
        return f"Lỗi tính tải lạnh: {e}"

@tool
def calc_chw_pipe_size(cooling_load_kw: float, delta_t: float = 5.5, max_velocity: float = 1.5) -> str:
    """
    Tính lưu lượng và cỡ ống nước lạnh (Chilled Water Pipe) dựa trên công suất lạnh.
    Tham số:
    - cooling_load_kw: Công suất lạnh (kW).
    - delta_t: Chênh lệch nhiệt độ nước cấp/về (độ C, thường là 5.5).
    - max_velocity: Vận tốc nước tối đa (m/s, thường 1.2 - 2.5).
    Trả về lưu lượng (L/s, GPM) và kích thước ống danh định (DN).
    """
    logger.info(f"Calculating CHW Pipe: Load={cooling_load_kw}kW")
    try:
        flow_lps = cooling_load_kw / (4.18 * delta_t)
        flow_gpm = flow_lps * 15.85
        
        area_m2 = (flow_lps / 1000) / max_velocity
        diameter_mm = math.sqrt(4 * area_m2 / math.pi) * 1000
        
        standard_dn = [15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200, 250, 300, 350, 400, 500]
        dn_selected = standard_dn[-1]
        for dn in standard_dn:
            if dn >= diameter_mm:
                dn_selected = dn
                break
                
        actual_area = math.pi * (dn_selected/1000)**2 / 4
        actual_velocity = (flow_lps / 1000) / actual_area
        
        return (f"Kết quả tính ống nước lạnh (Tải {cooling_load_kw} kW, dT={delta_t}°C):\n"
                f"- Lưu lượng nước: {flow_lps:.2f} L/s ({flow_gpm:.1f} GPM)\n"
                f"- Cỡ ống đề xuất: DN{dn_selected}\n"
                f"- Vận tốc thực tế: {actual_velocity:.2f} m/s")
    except Exception as e:
        return f"Lỗi tính toán cỡ ống: {e}"

@tool
def calc_pump_fan_power(flow_rate_lps: float, pressure_drop_pa: float, efficiency: float = 0.7) -> str:
    """
    Tính công suất động cơ (Quạt / Bơm) dựa trên lưu lượng và trở lực.
    Tham số:
    - flow_rate_lps: Lưu lượng (L/s).
    - pressure_drop_pa: Cột áp / Trở lực (Pa).
    - efficiency: Hiệu suất tổng (0.1 đến 1.0, thường 0.6 - 0.8).
    Trả về công suất trục (kW) để kỹ sư Điện chọn cáp.
    """
    logger.info(f"Calculating Motor Power: Q={flow_rate_lps}L/s, H={pressure_drop_pa}Pa")
    try:
        Q_m3s = flow_rate_lps / 1000
        power_w = (Q_m3s * pressure_drop_pa) / efficiency
        power_kw = power_w / 1000
        
        return (f"Tính toán động cơ (Lưu lượng {flow_rate_lps} L/s, Cột áp {pressure_drop_pa} Pa):\n"
                f"- Hiệu suất: {efficiency*100}%\n"
                f"- Công suất cơ học yêu cầu: {power_kw:.2f} kW\n"
                f"- Đề xuất chọn motor chuẩn: Lớn hơn hoặc bằng {power_kw * 1.15:.2f} kW (Hệ số an toàn 1.15)")
    except Exception as e:
        return f"Lỗi tính toán công suất: {e}"

@tool
def calc_ventilation_rate(area_m2: float, height_m: float, ach: float) -> str:
    """
    Tính lưu lượng thông gió hoặc hút khói dựa trên bội số tuần hoàn (ACH).
    Tham số:
    - area_m2: Diện tích phòng (m2).
    - height_m: Chiều cao trần (m).
    - ach: Bội số tuần hoàn (Air Changes per Hour - Lần/giờ).
    Trả về lưu lượng yêu cầu (m3/h và L/s).
    """
    logger.info(f"Calculating Ventilation: V={area_m2 * height_m}m3, ACH={ach}")
    try:
        volume = area_m2 * height_m
        flow_m3h = volume * ach
        flow_lps = flow_m3h / 3.6
        
        return (f"Lưu lượng thông gió (Thể tích {volume:.1f} m3, ACH = {ach} lần/giờ):\n"
                f"- Lưu lượng yêu cầu: {flow_m3h:.0f} m3/h ({flow_lps:.1f} L/s)")
    except Exception as e:
        return f"Lỗi tính thông gió: {e}"
