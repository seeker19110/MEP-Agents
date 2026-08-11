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
def calc_cooling_load_detailed(
    area_m2: float,
    occupancy: int = 0,
    equipment_load_w: float = 0.0,
    lighting_w_m2: float = 12.0,
    window_area_m2: float = 0.0,
    wall_area_m2: float = 0.0,
    roof_area_m2: float = 0.0,
    orientation: str = "nam",
    outdoor_temp_c: float = 35.0,
    indoor_temp_c: float = 25.0,
    outdoor_rh: float = 75.0,
    indoor_rh: float = 55.0,
    fresh_air_lps: float = 0.0,
    safety_factor: float = 1.1,
) -> str:
    """
    Tính tải lạnh CHI TIẾT theo phương pháp thành phần (người/đèn/thiết bị/kết cấu bao che/
    nắng qua kính/gió tươi) — chính xác hơn `calc_cooling_load` (chỉ dùng 1 hệ số W/m2 cố định).
    Đây là phương pháp tính tay đơn giản hóa (không phải bảng tra CLTD/CLF đầy đủ của ASHRAE),
    phù hợp cho thiết kế sơ bộ/thiết kế cơ sở; với thiết kế thi công chi tiết cần đối chiếu
    phần mềm chuyên dụng (HAP, Elite CHVAC...).
    Tham số:
    - occupancy: Số người trong phòng.
    - equipment_load_w: Tổng công suất thiết bị tỏa nhiệt (W).
    - lighting_w_m2: Mật độ công suất chiếu sáng (W/m2, mặc định 12).
    - window_area_m2, wall_area_m2, roof_area_m2: Diện tích kính/tường/mái tiếp xúc ngoài trời (m2).
    - orientation: Hướng chính của kính - "dong", "tay", "nam", "bac" hoặc hướng góc (mặc định "nam").
    - outdoor_temp_c/indoor_temp_c, outdoor_rh/indoor_rh: Điều kiện thiết kế trong/ngoài nhà.
    - fresh_air_lps: Lưu lượng gió tươi cấp vào phòng (L/s).
    - safety_factor: Hệ số an toàn tổng (mặc định 1.1).
    """
    logger.info(f"Calculating Detailed Cooling Load: Area={area_m2}m2, Occ={occupancy}")
    try:
        # 1. Nhiệt hiện + ẩn do người tỏa ra (hoạt động văn phòng nhẹ, tham khảo ASHRAE: ~75W hiện + 55W ẩn/người)
        q_people_sensible = occupancy * 75.0
        q_people_latent = occupancy * 55.0

        # 2. Chiếu sáng (có hệ số ballast ~1.2) và thiết bị (toàn bộ là nhiệt hiện)
        q_lighting = lighting_w_m2 * area_m2 * 1.2
        q_equipment = equipment_load_w

        # 3. Dẫn nhiệt qua kết cấu bao che (tường/mái), hệ số truyền nhiệt U tham khảo trung bình
        delta_t_envelope = outdoor_temp_c - indoor_temp_c
        U_WALL, U_ROOF, U_WINDOW = 2.0, 1.5, 5.8  # W/m2K, giá trị tham khảo trung bình
        ROOF_SOLAR_ADD_C = 5.0  # cộng thêm chênh lệch nhiệt độ tương đương do mái hấp thụ nắng trực tiếp

        q_wall = U_WALL * wall_area_m2 * max(delta_t_envelope, 0)
        q_roof = U_ROOF * roof_area_m2 * max(delta_t_envelope + ROOF_SOLAR_ADD_C, 0)
        q_window_conduction = U_WINDOW * window_area_m2 * max(delta_t_envelope, 0)

        # 4. Bức xạ mặt trời qua kính - hệ số nhiệt đỉnh tham khảo theo hướng (W/m2), vùng nhiệt đới gần xích đạo
        solar_factor_by_orientation = {
            "dong": 470.0, "east": 470.0,
            "tay": 470.0, "west": 470.0,
            "nam": 220.0, "south": 220.0,
            "bac": 150.0, "north": 150.0,
            "dong_nam": 350.0, "southeast": 350.0,
            "tay_nam": 350.0, "southwest": 350.0,
            "dong_bac": 300.0, "northeast": 300.0,
            "tay_bac": 300.0, "northwest": 300.0,
        }
        SHGC = 0.6  # Hệ số hấp thụ nhiệt mặt trời tham khảo cho kính thường (chưa có phim cách nhiệt)
        orientation_key = orientation.lower().strip().replace(" ", "_")
        solar_factor = solar_factor_by_orientation.get(orientation_key, 300.0)
        q_window_solar = window_area_m2 * solar_factor * SHGC

        # 5. Tải nhiệt gió tươi: thành phần hiện tính theo công thức xấp xỉ, thành phần ẩn suy ra từ chênh lệch entanpi
        q_fresh_air_sensible = 1.23 * fresh_air_lps * max(outdoor_temp_c - indoor_temp_c, 0)
        q_fresh_air_latent = 0.0
        if fresh_air_lps > 0:
            P_atm = 101325
            h_out = HA.HAPropsSI('H', 'T', outdoor_temp_c + 273.15, 'P', P_atm, 'R', outdoor_rh / 100) / 1000
            h_in = HA.HAPropsSI('H', 'T', indoor_temp_c + 273.15, 'P', P_atm, 'R', indoor_rh / 100) / 1000
            air_density = 1.2  # kg/m3, xấp xỉ
            mass_flow_kg_s = (fresh_air_lps / 1000) * air_density
            fresh_air_total_w = mass_flow_kg_s * max(h_out - h_in, 0) * 1000
            q_fresh_air_latent = max(fresh_air_total_w - q_fresh_air_sensible, 0)

        total_sensible = (q_people_sensible + q_lighting + q_equipment + q_wall + q_roof
                           + q_window_conduction + q_window_solar + q_fresh_air_sensible)
        total_latent = q_people_latent + q_fresh_air_latent
        grand_total_w = (total_sensible + total_latent) * safety_factor
        grand_total_kw = grand_total_w / 1000

        return (
            f"TẢI LẠNH CHI TIẾT ({area_m2} m2, hướng kính: {orientation}):\n"
            f"- Người ({occupancy} người): {q_people_sensible:.0f} W hiện + {q_people_latent:.0f} W ẩn\n"
            f"- Chiếu sáng: {q_lighting:.0f} W | Thiết bị: {q_equipment:.0f} W\n"
            f"- Tường: {q_wall:.0f} W | Mái: {q_roof:.0f} W | Kính (dẫn nhiệt): {q_window_conduction:.0f} W\n"
            f"- Bức xạ mặt trời qua kính: {q_window_solar:.0f} W\n"
            f"- Gió tươi ({fresh_air_lps} L/s): {q_fresh_air_sensible:.0f} W hiện + {q_fresh_air_latent:.0f} W ẩn\n"
            f"- Tổng nhiệt hiện: {total_sensible:.0f} W | Tổng nhiệt ẩn: {total_latent:.0f} W\n"
            f"=> TỔNG TẢI LẠNH (đã nhân hệ số an toàn {safety_factor}): {grand_total_kw:.2f} kW "
            f"(~ {grand_total_kw * 3412 / 1000:.0f} kBtu/h, {grand_total_kw / 3.517:.1f} Ton)"
        )
    except Exception as e:
        return f"Lỗi tính tải lạnh chi tiết: {e}"

@tool
def calc_duct_total_pressure_loss(
    duct_length_m: float,
    velocity_ms: float,
    friction_rate_pa_m: float = 1.0,
    elbow_90_qty: int = 0,
    tee_branch_qty: int = 0,
    damper_qty: int = 0,
    diffuser_qty: int = 0,
    equipment_pressure_drop_pa: float = 0.0,
    safety_factor: float = 1.15,
) -> str:
    """
    Tính TỔNG tổn thất áp suất toàn tuyến ống gió (ma sát + cục bộ) để chọn cột áp quạt (FSP/TSP),
    khác với `calc_duct_size` (chỉ tính kích thước 1 đoạn ống đơn lẻ).
    Tham số:
    - duct_length_m: Tổng chiều dài tuyến ống thẳng (m).
    - velocity_ms: Vận tốc gió thiết kế trong ống (m/s), dùng để tính áp suất động.
    - friction_rate_pa_m: Tổn thất ma sát trên mỗi mét ống (Pa/m), lấy từ biểu đồ ma sát hoặc `calc_duct_size`.
    - elbow_90_qty, tee_branch_qty, damper_qty, diffuser_qty: Số lượng phụ kiện trên tuyến
      (co 90°, tê nhánh, van điều chỉnh, miệng gió).
    - equipment_pressure_drop_pa: Tổn thất qua thiết bị trên tuyến (lọc gió, coil...) nếu có (Pa).
    - safety_factor: Hệ số an toàn tổng (mặc định 1.15).
    """
    logger.info(f"Calculating Duct Total Pressure Loss: L={duct_length_m}m, v={velocity_ms}m/s")
    try:
        AIR_DENSITY = 1.2  # kg/m3
        dynamic_pressure_pa = 0.5 * AIR_DENSITY * velocity_ms ** 2

        # Hệ số tổn thất cục bộ (K) tham khảo cho từng loại phụ kiện phổ biến
        K_ELBOW_90, K_TEE_BRANCH, K_DAMPER, K_DIFFUSER = 0.3, 1.0, 0.2, 1.0

        friction_loss_pa = duct_length_m * friction_rate_pa_m
        local_loss_pa = (
            elbow_90_qty * K_ELBOW_90 + tee_branch_qty * K_TEE_BRANCH
            + damper_qty * K_DAMPER + diffuser_qty * K_DIFFUSER
        ) * dynamic_pressure_pa

        total_pa = (friction_loss_pa + local_loss_pa + equipment_pressure_drop_pa) * safety_factor

        return (
            f"TỔN THẤT ÁP SUẤT TOÀN TUYẾN ỐNG GIÓ (L={duct_length_m}m, v={velocity_ms}m/s):\n"
            f"- Tổn thất ma sát: {friction_loss_pa:.1f} Pa\n"
            f"- Tổn thất cục bộ (co {elbow_90_qty}, tê {tee_branch_qty}, van {damper_qty}, "
            f"miệng gió {diffuser_qty}): {local_loss_pa:.1f} Pa\n"
            f"- Tổn thất qua thiết bị (lọc gió/coil...): {equipment_pressure_drop_pa:.1f} Pa\n"
            f"=> TỔNG CỘT ÁP QUẠT CẦN CHỌN (đã nhân hệ số an toàn {safety_factor}): "
            f"{total_pa:.0f} Pa ({total_pa / 1000:.3f} kPa)"
        )
    except Exception as e:
        return f"Lỗi tính tổn thất áp suất ống gió: {e}"

@tool
def calc_chiller_ahu_selection(cooling_load_kw: float, equipment_type: str = "chiller", safety_factor: float = 1.1) -> str:
    """
    Đề xuất công suất danh định tiêu chuẩn của Chiller/AHU/FCU theo bước công suất catalog phổ biến
    trên thị trường, nối tiếp bước `calc_cooling_load` / `calc_cooling_load_detailed`.
    Tham số:
    - cooling_load_kw: Tải lạnh cần đáp ứng (kW).
    - equipment_type: 'chiller' (cụm máy lạnh trung tâm), 'ahu' (Air Handling Unit), 'fcu' (Fan Coil Unit).
    - safety_factor: Hệ số dự phòng (mặc định 1.1).
    Lưu ý: Bước công suất là giá trị tham khảo chung nhiều hãng, cần đối chiếu catalog chính hãng
    khi chốt thiết bị thi công.
    """
    logger.info(f"Selecting {equipment_type} for load={cooling_load_kw}kW")
    try:
        standard_steps = {
            "chiller": [30, 50, 70, 105, 140, 175, 210, 280, 350, 420, 528, 700, 880, 1050, 1400],
            "ahu": [7, 10, 14, 18, 25, 35, 50, 70, 90, 120, 150],
            "fcu": [2.2, 2.8, 3.6, 4.5, 5.6, 7.1, 9.0, 11.2, 14.0, 16.0, 22.0, 28.0],
        }
        eq_key = equipment_type.lower().strip()
        steps = standard_steps.get(eq_key)
        if not steps:
            return f"Lỗi: equipment_type phải là 'chiller', 'ahu' hoặc 'fcu' (nhận được '{equipment_type}')."

        required_kw = cooling_load_kw * safety_factor
        max_step = steps[-1]

        if required_kw <= max_step:
            selected = next(s for s in steps if s >= required_kw)
            return (
                f"ĐỀ XUẤT {eq_key.upper()} (Tải {cooling_load_kw} kW x hệ số {safety_factor} = {required_kw:.1f} kW):\n"
                f"- Chọn 1 cụm công suất danh định: {selected} kW"
            )
        else:
            qty = math.ceil(required_kw / max_step)
            return (
                f"ĐỀ XUẤT {eq_key.upper()} (Tải {cooling_load_kw} kW x hệ số {safety_factor} = {required_kw:.1f} kW):\n"
                f"- Tải vượt quá 1 cụm lớn nhất trong catalog tham khảo ({max_step} kW)\n"
                f"- Đề xuất lắp {qty} cụm song song, mỗi cụm {max_step} kW "
                f"(tổng {qty * max_step} kW, cần kiểm tra lại theo catalog chính hãng)"
            )
    except Exception as e:
        return f"Lỗi chọn thiết bị: {e}"

@tool
def calc_refrigerant_pipe_size(capacity_kw: float, pipe_line: str = "gas", hp_conversion_kw: float = 2.8) -> str:
    """
    Tính (sơ bộ) cỡ ống đồng dẫn gas lạnh cho hệ VRV/VRF theo công suất lạnh.
    Tham số:
    - capacity_kw: Công suất lạnh của dàn/tuyến cần cấp gas (kW).
    - pipe_line: 'gas' (đường ống hơi/gas - tiết diện lớn hơn) hoặc 'liquid' (đường ống lỏng).
    - hp_conversion_kw: Hệ số quy đổi kW sang HP danh định VRV (mặc định 2.8 kW/HP, tham khảo).
    Lưu ý: Đây là bảng tra tham khảo chung (không thay thế catalog chính hãng
    Daikin/Mitsubishi/Toshiba...), cần đối chiếu lại khi thiết kế thi công.
    """
    logger.info(f"Calculating Refrigerant Pipe: Capacity={capacity_kw}kW, Line={pipe_line}")
    try:
        hp = capacity_kw / hp_conversion_kw

        # Đường kính ngoài ống đồng tham khảo (mm) theo dải công suất HP, đường lỏng nhỏ hơn đường gas cùng HP
        liquid_steps = [(2, 6.35), (5, 9.52), (10, 12.7), (20, 15.88), (30, 19.05), (float("inf"), 22.2)]
        gas_steps = [(2, 12.7), (5, 15.88), (10, 19.05), (20, 22.2), (30, 28.58), (float("inf"), 34.93)]

        line_key = pipe_line.lower().strip()
        if line_key == "liquid":
            steps = liquid_steps
        elif line_key == "gas":
            steps = gas_steps
        else:
            return f"Lỗi: pipe_line phải là 'gas' hoặc 'liquid' (nhận được '{pipe_line}')."

        od_mm = next(od for limit, od in steps if hp <= limit)

        return (
            f"CỠ ỐNG GAS LẠNH VRV/VRF (Công suất {capacity_kw} kW ≈ {hp:.1f} HP, đường {line_key}):\n"
            f"- Đường kính ngoài (OD) tham khảo: Ø{od_mm} mm\n"
            f"- Ghi chú: Đối chiếu lại catalog chính hãng trước khi thi công, đặc biệt với tuyến dài "
            f"có chênh cao lớn hoặc nhiều rẽ nhánh."
        )
    except Exception as e:
        return f"Lỗi tính ống gas lạnh: {e}"

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
