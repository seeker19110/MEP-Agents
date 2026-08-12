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
        if Q <= 0:
            return "Lưu lượng phải lớn hơn 0."
        
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
            res += "- Các ống chữ nhật gợi ý (W x H): " + " hoặc ".join(rect_options) + "\n"
        
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

# --- Tiếng ồn (NC - Noise Criteria) ---

# Mức NC khuyến nghị theo loại phòng (ASHRAE Handbook - Applications, chương Sound & Vibration).
NC_RECOMMENDED = {
    "phong_ngu": (25, 30, "Phòng ngủ, khách sạn, bệnh viện"),
    "phong_hop": (25, 30, "Phòng họp, phòng hội thảo"),
    "studio": (15, 20, "Studio thu âm, phòng bá âm"),
    "van_phong_rieng": (30, 35, "Văn phòng riêng, phòng làm việc nhỏ"),
    "van_phong_chung": (35, 40, "Văn phòng không gian mở"),
    "lop_hoc": (25, 30, "Lớp học, giảng đường"),
    "nha_hang": (40, 45, "Nhà hàng, khu ăn uống"),
    "sanh": (40, 45, "Sảnh, hành lang, khu công cộng"),
    "xuong": (50, 60, "Xưởng sản xuất, khu kỹ thuật"),
}


@tool
def calc_nc_level(sound_power_lw: float, room_volume_m3: float, space_type: str = "van_phong_chung",
                  distance_m: float = 1.5, num_sources: int = 1, duct_attenuation_db: float = 0.0) -> str:
    """Kiểm tra mức ồn NC (Noise Criteria) do miệng gió/quạt gây ra trong phòng.

    Bắt buộc với phòng yêu cầu yên tĩnh (phòng ngủ, phòng họp, studio, lớp học).
    Tham số:
    - sound_power_lw: Mức công suất âm Lw của thiết bị theo catalog (dB).
    - room_volume_m3: Thể tích phòng (m3).
    - space_type: Loại phòng (phong_ngu, phong_hop, studio, van_phong_rieng,
      van_phong_chung, lop_hoc, nha_hang, sanh, xuong).
    - distance_m: Khoảng cách từ nguồn ồn tới vị trí người nghe (m).
    - num_sources: Số miệng gió/nguồn ồn giống nhau trong phòng.
    - duct_attenuation_db: Độ suy giảm của tiêu âm/ống gió trên đường truyền (dB).
    """
    logger.info(f"Calculating NC level: Lw={sound_power_lw}dB, V={room_volume_m3}m3, type={space_type}")
    try:
        if room_volume_m3 <= 0 or distance_m <= 0:
            return "Lỗi: Thể tích phòng và khoảng cách phải lớn hơn 0."

        # Cộng nguồn ồn giống nhau: mỗi lần gấp đôi số nguồn thì tăng 3 dB.
        lw_total = sound_power_lw + 10 * math.log10(max(1, num_sources))

        # Chuyển Lw -> Lp theo công thức phòng (ASHRAE): Lp = Lw - 5*log10(V) - 3*log10(f)
        # - 10*log10(r) + 12. Lấy f = 1000 Hz làm dải tần tham chiếu để kiểm tra sơ bộ.
        lp = (lw_total - 5 * math.log10(room_volume_m3) - 3 * math.log10(1000)
              - 10 * math.log10(distance_m) + 12)
        lp -= duct_attenuation_db

        # NC xấp xỉ dBA - 7 (quy đổi kinh nghiệm dùng trong thiết kế sơ bộ).
        nc_estimated = lp - 7

        key = (space_type or "").lower().strip()
        nc_min, nc_max, label = NC_RECOMMENDED.get(key, NC_RECOMMENDED["van_phong_chung"])
        if key not in NC_RECOMMENDED:
            label += " (không nhận diện được space_type, dùng mặc định)"

        report = [
            f"Kiểm tra tiếng ồn NC ({label}):",
            f"- Mức công suất âm nguồn Lw: {sound_power_lw:.1f} dB x {num_sources} nguồn = {lw_total:.1f} dB",
            f"- Suy giảm do tiêu âm/ống gió: {duct_attenuation_db:.1f} dB",
            f"- Mức áp suất âm tại vị trí nghe (cách {distance_m} m): {lp:.1f} dB",
            f"- NC ước tính: NC-{nc_estimated:.0f}",
            f"- NC cho phép theo ASHRAE: NC-{nc_min} đến NC-{nc_max}",
        ]

        if nc_estimated <= nc_max:
            report.append("- Kết luận: ĐẠT yêu cầu tiếng ồn.")
        else:
            excess = nc_estimated - nc_max
            report.append(f"- Kết luận: KHÔNG ĐẠT, vượt {excess:.0f} dB so với giới hạn NC-{nc_max}.")
            report.append("- Biện pháp: giảm vận tốc gió tại miệng (dưới 2.5 m/s cho phòng yên tĩnh), "
                          "lắp hộp tiêu âm/ống mềm tiêu âm, tăng kích thước miệng gió, hoặc đặt "
                          "quạt/AHU xa phòng và bọc cách âm.")
        report.append("- Lưu ý: Đây là kiểm tra SƠ BỘ ở dải tần tham chiếu 1000 Hz. Phòng đặc biệt "
                      "yên tĩnh (studio, phòng mổ) cần phân tích đủ 8 dải octave theo catalog thiết bị.")
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính NC: {e}"


@tool
def calc_cooling_tower(condenser_heat_rejection_kw: float, wet_bulb_c: float = 28.0,
                       approach_c: float = 5.0, range_c: float = 5.0) -> str:
    """
    Chọn tháp giải nhiệt (Cooling Tower) cho hệ chiller giải nhiệt nước — hạng mục hay bị bỏ
    sót khi chuỗi tính toán chỉ dừng ở chọn chiller (`calc_chiller_ahu_selection`) mà quên
    tính tháp giải nhiệt kèm theo cho chiller giải nhiệt nước (water-cooled).
    Tham số:
    - condenser_heat_rejection_kw: Nhiệt thải bình ngưng cần giải nhiệt (kW) — thường ước
      tính bằng công suất lạnh chiller x 1.2÷1.25 (cộng thêm nhiệt tương đương công máy nén).
    - wet_bulb_c: Nhiệt độ bầu ướt thiết kế ngoài trời (°C, mặc định 28 — cần lấy số liệu khí
      hậu thực tế của địa phương).
    - approach_c: Độ chênh Approach — hiệu số giữa nhiệt độ nước lạnh ra tháp và bầu ướt (°C,
      mặc định 5, thông thường 4-6).
    - range_c: Độ chênh Range — hiệu số nhiệt độ nước vào/ra tháp (°C, mặc định 5).
    """
    logger.info(f"Calculating Cooling Tower: Q={condenser_heat_rejection_kw}kW")
    try:
        if condenser_heat_rejection_kw <= 0:
            return "Lỗi: Nhiệt thải bình ngưng phải lớn hơn 0."

        cold_water_temp_c = wet_bulb_c + approach_c
        hot_water_temp_c = cold_water_temp_c + range_c

        # Lưu lượng nước giải nhiệt: Q(kW) = m_dot(kg/s) * cp(4.186) * range(°C)
        flow_kg_s = condenser_heat_rejection_kw / (4.186 * range_c)
        flow_m3h = flow_kg_s * 3.6

        # Công suất tháp quy đổi ra "tấn tháp" (tower ton, ~3.9 kW/tấn — bao gồm cả nhiệt nén,
        # lớn hơn 1 tấn lạnh refrigeration ton 3.517 kW).
        tower_tons = condenser_heat_rejection_kw / 3.9

        return "\n".join([
            f"Chọn Tháp giải nhiệt (Cooling Tower) — nhiệt thải bình ngưng {condenser_heat_rejection_kw} kW:",
            f"- Nhiệt độ bầu ướt thiết kế: {wet_bulb_c}°C",
            f"- Nhiệt độ nước lạnh ra tháp (vào bình ngưng): {cold_water_temp_c:.1f}°C "
            f"(Approach {approach_c}°C)",
            f"- Nhiệt độ nước nóng vào tháp (ra bình ngưng): {hot_water_temp_c:.1f}°C "
            f"(Range {range_c}°C)",
            f"- Lưu lượng nước giải nhiệt tuần hoàn: {flow_m3h:.1f} m3/h",
            f"=> CÔNG SUẤT THÁP GIẢI NHIỆT: ~{tower_tons:.1f} tấn tháp (tower ton)",
            "- Approach càng nhỏ (tháp càng lớn/hiệu quả) thì chiller chạy COP cao hơn nhưng chi "
            "phí đầu tư tháp tăng — cân đối theo bài toán vòng đời (LCC), Approach 4-6°C phổ biến.",
            "- Cần tính thêm bơm nước giải nhiệt (dùng `calc_pump_fan_power` với lưu lượng "
            f"{flow_m3h:.1f} m3/h) và xử lý nước tuần hoàn (chống đóng cặn/rêu tảo) cho tháp hở.",
        ])
    except Exception as e:
        return f"Lỗi tính tháp giải nhiệt: {e}"


# Lưu lượng gió tươi tối thiểu theo loại phòng (ASHRAE 62.1, Ventilation Rate Procedure).
# Rp: L/s trên mỗi người; Ra: L/s trên mỗi m2 diện tích sàn.
ASHRAE_622_TABLE = {
    "office": {"Rp": 2.5, "Ra": 0.3, "label": "Văn phòng"},
    "classroom": {"Rp": 3.8, "Ra": 0.9, "label": "Phòng học"},
    "conference": {"Rp": 2.5, "Ra": 0.3, "label": "Phòng họp"},
    "retail": {"Rp": 3.8, "Ra": 0.6, "label": "Bán lẻ/siêu thị"},
    "restaurant": {"Rp": 3.8, "Ra": 0.9, "label": "Nhà hàng (khu ăn)"},
    "lobby": {"Rp": 2.5, "Ra": 0.3, "label": "Sảnh/hành lang"},
    "gym": {"Rp": 10.0, "Ra": 0.3, "label": "Phòng tập gym"},
}


@tool
def calc_fresh_air_ashrae(occupants: int, area_m2: float, room_type: str = "office") -> str:
    """
    Tính lưu lượng gió tươi tối thiểu (khí tươi cấp cho phòng có người) theo phương pháp
    Ventilation Rate Procedure của ASHRAE 62.1 — tính đủ CẢ hai thành phần (theo số người VÀ
    theo diện tích sàn), chuẩn xác hơn `calc_ventilation_rate` (chỉ dùng bội số trao đổi khí
    ACH cố định, không phân biệt loại phòng theo tiêu chuẩn quốc tế).
    Tham số:
    - occupants: Số người dự kiến trong phòng.
    - area_m2: Diện tích sàn phòng (m2).
    - room_type: Loại phòng — 'office', 'classroom', 'conference', 'retail', 'restaurant',
      'lobby', 'gym'. Không khớp loại nào thì dùng bảng của 'office'.
    """
    logger.info(f"Calculating Fresh Air ASHRAE 62.1: occ={occupants}, area={area_m2}, type={room_type}")
    try:
        if occupants < 0 or area_m2 <= 0:
            return "Lỗi: Diện tích phải lớn hơn 0 và số người không được âm."

        key = (room_type or "office").lower().strip()
        data = ASHRAE_622_TABLE.get(key, ASHRAE_622_TABLE["office"])
        matched = key in ASHRAE_622_TABLE

        vbz_people_lps = data["Rp"] * occupants
        vbz_area_lps = data["Ra"] * area_m2
        vbz_total_lps = vbz_people_lps + vbz_area_lps
        vbz_total_m3h = vbz_total_lps * 3.6

        room_type_note = "" if matched else "  (mặc định office - không nhận diện được room_type)"
        report = [
            f"Tính gió tươi theo ASHRAE 62.1 ({data['label']}{room_type_note}) — "
            f"{occupants} người, {area_m2} m2:",
            f"- Thành phần theo người (Rp = {data['Rp']} L/s/người): {vbz_people_lps:.1f} L/s",
            f"- Thành phần theo diện tích (Ra = {data['Ra']} L/s/m2): {vbz_area_lps:.1f} L/s",
            f"=> LƯU LƯỢNG GIÓ TƯƠI TỐI THIỂU (Vbz): {vbz_total_lps:.1f} L/s = {vbz_total_m3h:.0f} m3/h",
            "- Đây là lưu lượng gió tươi CẤP VÀO phòng (outdoor air), không phải tổng lưu lượng gió "
            "tuần hoàn của AHU/FCU — dùng giá trị này làm đầu vào chọn AHU có bộ trộn gió tươi hoặc "
            "hệ thu hồi nhiệt (ERV/HRV) riêng.",
            "- Với phòng đông người biến động (hội trường, rạp chiếu), cân nhắc điều khiển gió tươi "
            "theo nồng độ CO2 (Demand Control Ventilation) thay vì cấp cố định theo thiết kế đỉnh.",
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính gió tươi ASHRAE 62.1: {e}"


@tool
def calc_vrv_outdoor_unit(total_indoor_capacity_kw: float, diversity_factor: float = 0.8,
                          max_connection_ratio_percent: float = 130.0) -> str:
    """
    Chọn công suất dàn nóng (Outdoor Unit) hệ VRV/VRF từ tổng công suất các dàn lạnh (Indoor
    Units) đã bố trí — hạng mục hay bị bỏ sót khi chuỗi tính toán VRV chỉ dừng ở chọn cỡ ống
    gas (`calc_refrigerant_pipe_size`) mà quên bước chọn dàn nóng theo hệ số đồng thời thực tế
    (không phải mọi dàn lạnh đều chạy full tải cùng lúc).
    Tham số:
    - total_indoor_capacity_kw: Tổng công suất lạnh danh định của TẤT CẢ dàn lạnh nối vào cùng
      một dàn nóng/hệ (kW).
    - diversity_factor: Hệ số đồng thời sử dụng (mặc định 0.8 — 80% dàn lạnh hoạt động full tải
      cùng lúc là giả định thiết kế phổ biến; công trình có giờ dùng lệch nhau lớn có thể hạ thấp
      hơn, VD 0.6-0.7).
    - max_connection_ratio_percent: Tỷ lệ kết nối tối đa cho phép của hãng (dàn lạnh/dàn nóng,
      mặc định 130% — cần đối chiếu catalog hãng cụ thể vì một số dòng cho phép tới 150-200%).
    """
    logger.info(f"Calculating VRV Outdoor Unit: total_indoor={total_indoor_capacity_kw}kW")
    try:
        if total_indoor_capacity_kw <= 0:
            return "Lỗi: Tổng công suất dàn lạnh phải lớn hơn 0."
        if not (0 < diversity_factor <= 1.5):
            return "Lỗi: Hệ số đồng thời phải trong khoảng hợp lý (0, 1.5]."

        outdoor_required_kw = total_indoor_capacity_kw * diversity_factor
        connection_ratio_pct = (total_indoor_capacity_kw / outdoor_required_kw) * 100.0 if outdoor_required_kw > 0 else 0

        report = [
            f"Chọn Dàn nóng VRV/VRF — tổng công suất dàn lạnh {total_indoor_capacity_kw} kW, "
            f"hệ số đồng thời {diversity_factor}:",
            f"=> CÔNG SUẤT DÀN NÓNG TỐI THIỂU CẦN CHỌN: {outdoor_required_kw:.1f} kW "
            f"(chọn model catalog gần nhất, không thấp hơn giá trị này)",
            f"- Tỷ lệ kết nối (Connection Ratio) tương ứng: {connection_ratio_pct:.0f}%",
        ]

        if connection_ratio_pct > max_connection_ratio_percent:
            report.append(f"- CẢNH BÁO: Tỷ lệ kết nối {connection_ratio_pct:.0f}% VƯỢT giới hạn cho "
                          f"phép {max_connection_ratio_percent:.0f}% — cần chọn dàn nóng công suất lớn "
                          f"hơn hoặc giảm hệ số đồng thời (kiểm tra lại giả định vận hành thực tế).")
        else:
            report.append(f"- Tỷ lệ kết nối trong giới hạn cho phép ({max_connection_ratio_percent:.0f}%).")

        report += [
            "- BẮT BUỘC đối chiếu công suất dàn nóng vừa tính với catalog model thật của hãng "
            "(Daikin/Mitsubishi/LG...) — công suất danh định thường suy giảm theo chiều dài ống gas "
            "và chênh cao độ dàn nóng/dàn lạnh, cần hiệu chỉnh theo bảng correction factor của hãng.",
            "- Không vượt quá số lượng dàn lạnh tối đa cho phép trên một hệ (thường 40-64 dàn tùy "
            "dòng sản phẩm) dù công suất còn dư tỷ lệ kết nối.",
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính dàn nóng VRV: {e}"
