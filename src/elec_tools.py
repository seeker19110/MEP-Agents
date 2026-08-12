from langchain_core.tools import tool
import json
import math
import logging

logger = logging.getLogger(__name__)

# Tiết diện ruột dẫn tiêu chuẩn (mm2) theo IEC 60228.
STANDARD_CABLE_SIZES = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300, 400]

# Điện trở suất đồng ở nhiệt độ làm việc ~70 độ C (Ohm.mm2/m).
RHO_COPPER = 0.0225

# Giới hạn sụt áp cho phép (%) theo TCVN 9206 / IEC 60364-5-52.
VOLTAGE_DROP_LIMIT_LIGHTING = 3.0   # mạch chiếu sáng
VOLTAGE_DROP_LIMIT_POWER = 5.0      # mạch động lực


def _voltage_drop_percent(current_a: float, length_m: float, section_mm2: float,
                          voltage: float, phase: int, cos_phi: float) -> float:
    """Sụt áp (%) trên một tuyến cáp đồng, bỏ qua thành phần cảm kháng.

    3 pha: dU = sqrt(3) * I * L * rho / S * cos_phi
    1 pha: dU = 2 * I * L * rho / S * cos_phi   (đi và về => nhân 2)
    """
    if section_mm2 <= 0 or length_m <= 0:
        return 0.0
    factor = math.sqrt(3) if phase == 3 else 2.0
    drop_v = factor * current_a * length_m * RHO_COPPER / section_mm2 * cos_phi
    return drop_v / voltage * 100.0


def _select_by_current(current_a: float) -> float:
    """Tiết diện nhỏ nhất đủ tải theo mật độ dòng ~4 A/mm2 (cáp Cu/XLPE đi trong ống)."""
    s_estimate = current_a / 4.0
    for c in STANDARD_CABLE_SIZES:
        if c >= s_estimate:
            return c
    return STANDARD_CABLE_SIZES[-1]


@tool
def calc_voltage_drop(current_a: float, length_m: float, section_mm2: float,
                      voltage: float = 380, phase: int = 3, cos_phi: float = 0.85,
                      circuit_type: str = "power") -> str:
    """Kiểm tra độ sụt áp (%) của một tuyến cáp đồng theo chiều dài thực tế.

    circuit_type: 'power' (động lực, giới hạn 5%) hoặc 'lighting' (chiếu sáng, 3%).
    """
    logger.info(f"Calculating Voltage Drop: I={current_a}A, L={length_m}m, S={section_mm2}mm2")
    try:
        if phase != 3:
            voltage = 220
        drop_pct = _voltage_drop_percent(current_a, length_m, section_mm2, voltage, phase, cos_phi)
        limit = VOLTAGE_DROP_LIMIT_LIGHTING if circuit_type.lower().startswith("light") else VOLTAGE_DROP_LIMIT_POWER
        verdict = "ĐẠT" if drop_pct <= limit else "KHÔNG ĐẠT - phải tăng tiết diện cáp"

        return (f"Kiểm tra sụt áp tuyến cáp (I = {current_a:.1f} A, L = {length_m} m, S = {section_mm2} mm2):\n"
                f"- Sụt áp tính toán: {drop_pct:.2f} %\n"
                f"- Giới hạn cho phép ({circuit_type}): {limit:.1f} % (TCVN 9206 / IEC 60364-5-52)\n"
                f"- Kết luận: {verdict}")
    except Exception as e:
        return f"Lỗi tính sụt áp: {e}"


@tool
def calc_cable_size(power_kw: float, voltage: float = 380, cos_phi: float = 0.85, phase: int = 3,
                    length_m: float = 0, circuit_type: str = "power") -> str:
    """Chọn tiết diện cáp theo công suất phụ tải VÀ kiểm tra sụt áp theo chiều dài tuyến.

    `length_m` là chiều dài tuyến cáp từ tủ điện tới phụ tải (m). Nếu bỏ trống, tool chỉ
    chọn cáp theo dòng điện và cảnh báo rằng kết quả CHƯA kiểm tra sụt áp.
    """
    logger.info(f"Calculating Cable Size: P={power_kw}kW, L={length_m}m")
    try:
        if phase == 3:
            current_a = (power_kw * 1000) / (math.sqrt(3) * voltage * cos_phi)
        else:
            voltage = 220
            current_a = (power_kw * 1000) / (voltage * cos_phi)

        selected_cable = _select_by_current(current_a)
        report = [
            f"Tính cáp điện (P = {power_kw} kW, {phase} pha):",
            f"- Dòng điện tính toán (Ib): {current_a:.1f} A",
            f"- Tiết diện theo điều kiện phát nóng: {selected_cable} mm2",
        ]

        if not length_m or length_m <= 0:
            report.append(
                "- CẢNH BÁO: Chưa nhập chiều dài tuyến (length_m) nên CHƯA kiểm tra được sụt áp. "
                "TCVN 9206 bắt buộc kiểm tra %sụt áp; với tuyến dài, tiết diện trên có thể KHÔNG ĐỦ. "
                "Hãy hỏi lại chiều dài tuyến cáp rồi tính lại."
            )
            report.append(f"- Đề xuất cáp Cu/XLPE/PVC: {selected_cable} mm2 (chưa kiểm tra sụt áp)")
            return "\n".join(report)

        limit = VOLTAGE_DROP_LIMIT_LIGHTING if circuit_type.lower().startswith("light") else VOLTAGE_DROP_LIMIT_POWER
        drop_initial = _voltage_drop_percent(current_a, length_m, selected_cable, voltage, phase, cos_phi)

        # Tăng dần tiết diện cho tới khi sụt áp nằm trong giới hạn.
        final_cable = selected_cable
        for c in STANDARD_CABLE_SIZES:
            if c < selected_cable:
                continue
            if _voltage_drop_percent(current_a, length_m, c, voltage, phase, cos_phi) <= limit:
                final_cable = c
                break
        else:
            final_cable = STANDARD_CABLE_SIZES[-1]

        drop_final = _voltage_drop_percent(current_a, length_m, final_cable, voltage, phase, cos_phi)
        report.append(f"- Sụt áp nếu dùng {selected_cable} mm2 trên {length_m} m: {drop_initial:.2f} % "
                      f"(giới hạn {limit:.1f} %)")
        if final_cable > selected_cable:
            report.append(f"- PHẢI TĂNG TIẾT DIỆN do sụt áp vượt giới hạn.")
        report.append(f"- Đề xuất cáp Cu/XLPE/PVC: {final_cable} mm2 (sụt áp {drop_final:.2f} % - ĐẠT)")
        if drop_final > limit:
            report.append("- CẢNH BÁO: Ngay cả tiết diện lớn nhất vẫn vượt giới hạn sụt áp. "
                          "Cần chia tuyến, đặt tủ phân phối gần phụ tải hơn hoặc nâng cấp điện áp.")
        return "\n".join(report)
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


# --- Tổng hợp phụ tải & chọn nguồn ---

# Hệ số đồng thời (Ku x Ks) tham khảo theo loại phụ tải, TCVN 9206.
DIVERSITY_FACTORS = {
    "chieu_sang": 0.9,
    "o_cam": 0.5,
    "dieu_hoa": 0.8,
    "thang_may": 0.7,
    "bom_quat": 0.8,
    "bep": 0.6,
    "khac": 0.8,
}


@tool
def calc_total_load(loads_json: str, transformer_reserve: float = 1.25, cos_phi: float = 0.85) -> str:
    """Tổng hợp phụ tải toàn công trình có xét hệ số đồng thời để chọn máy biến áp/máy phát.

    loads_json: chuỗi JSON dạng [{"ten": "Chiếu sáng", "loai": "chieu_sang", "cong_suat_kw": 50}, ...].
    Trường `loai` nhận: chieu_sang, o_cam, dieu_hoa, thang_may, bom_quat, bep, khac.
    Cộng thẳng công suất đặt mà không xét hệ số đồng thời sẽ chọn máy biến áp thừa rất
    nhiều so với nhu cầu thực tế.
    """
    logger.info("Calculating total load with diversity factors")
    try:
        items = json.loads(loads_json)
        if not isinstance(items, list) or not items:
            return "Lỗi: `loads_json` phải là danh sách JSON các phụ tải, không được rỗng."

        rows, total_installed, total_calculated = [], 0.0, 0.0
        for item in items:
            name = item.get("ten", "Không tên")
            kind = str(item.get("loai", "khac")).lower().strip()
            power = float(item.get("cong_suat_kw", 0))
            factor = DIVERSITY_FACTORS.get(kind, DIVERSITY_FACTORS["khac"])
            calculated = power * factor
            total_installed += power
            total_calculated += calculated
            rows.append(f"  - {name} ({kind}): {power:.1f} kW x Kđt {factor} = {calculated:.1f} kW")

        apparent_kva = total_calculated / cos_phi if cos_phi else 0
        transformer_kva = apparent_kva * transformer_reserve
        standard_tx = [100, 160, 250, 400, 560, 630, 750, 800, 1000, 1250, 1600, 2000, 2500]
        selected_tx = next((t for t in standard_tx if t >= transformer_kva), standard_tx[-1])
        # Máy phát dự phòng thường phủ 60-80% phụ tải tính toán (chỉ tải ưu tiên).
        generator_kva = apparent_kva * 0.7

        report = [
            "TỔNG HỢP PHỤ TẢI (TCVN 9206):",
            *rows,
            "",
            f"- Tổng công suất ĐẶT: {total_installed:.1f} kW",
            f"- Tổng công suất TÍNH TOÁN (sau hệ số đồng thời): {total_calculated:.1f} kW "
            f"(bằng {total_calculated / total_installed * 100:.0f}% công suất đặt)" if total_installed else "",
            f"- Công suất biểu kiến (cos φ = {cos_phi}): {apparent_kva:.1f} kVA",
            f"- Yêu cầu máy biến áp (dự phòng {transformer_reserve:.2f}): {transformer_kva:.1f} kVA",
            f"=> CHỌN MÁY BIẾN ÁP: {selected_tx} kVA",
            f"=> Máy phát dự phòng (phủ ~70% tải ưu tiên): khoảng {generator_kva:.0f} kVA",
            "- Lưu ý: Hệ số đồng thời trên là giá trị tham khảo; dự án thực tế cần đối chiếu "
            "biểu đồ phụ tải và yêu cầu của đơn vị điện lực.",
        ]
        return "\n".join(line for line in report if line != "")
    except json.JSONDecodeError as e:
        return f"Lỗi đọc JSON phụ tải: {e}. Định dạng đúng: [{{\"ten\":\"...\",\"loai\":\"chieu_sang\",\"cong_suat_kw\":50}}]"
    except Exception as e:
        return f"Lỗi tổng hợp phụ tải: {e}"


@tool
def calc_short_circuit(transformer_kva: float, voltage: float = 380, impedance_percent: float = 4.0,
                       cable_length_m: float = 0, cable_section_mm2: float = 0) -> str:
    """Tính dòng ngắn mạch 3 pha và kiểm tra khả năng cắt (Icu) của aptomat.

    Chọn aptomat chỉ theo dòng làm việc mà bỏ qua dòng ngắn mạch là nguy hiểm: khi sự cố,
    thiết bị không cắt nổi sẽ phát nổ. Nếu nhập chiều dài và tiết diện cáp, tool tính thêm
    dòng ngắn mạch tại CUỐI tuyến (đã suy giảm do tổng trở cáp) để phối hợp bảo vệ.
    """
    logger.info(f"Calculating short circuit: S={transformer_kva}kVA, Uk={impedance_percent}%")
    try:
        if transformer_kva <= 0 or impedance_percent <= 0:
            return "Lỗi: Công suất máy biến áp và điện áp ngắn mạch (%) phải lớn hơn 0."

        # Dòng định mức và dòng ngắn mạch tại thanh cái hạ áp máy biến áp.
        rated_current = transformer_kva * 1000 / (math.sqrt(3) * voltage)
        isc_ka = rated_current / (impedance_percent / 100) / 1000

        standard_icu = [6, 10, 15, 18, 25, 36, 50, 65, 85, 100]
        selected_icu = next((i for i in standard_icu if i >= isc_ka), standard_icu[-1])

        report = [
            f"DÒNG NGẮN MẠCH (MBA {transformer_kva} kVA, Uk = {impedance_percent}%):",
            f"- Dòng định mức phía hạ áp: {rated_current:.0f} A",
            f"- Dòng ngắn mạch 3 pha tại thanh cái tổng (Isc): {isc_ka:.1f} kA",
            f"=> Aptomat tổng phải có khả năng cắt Icu >= {selected_icu} kA",
        ]

        if cable_length_m > 0 and cable_section_mm2 > 0:
            # Tổng trở cáp làm giảm dòng ngắn mạch ở cuối tuyến.
            z_cable = RHO_COPPER * cable_length_m / cable_section_mm2
            z_source = voltage / (math.sqrt(3) * isc_ka * 1000)
            isc_end_ka = voltage / (math.sqrt(3) * (z_source + z_cable)) / 1000
            selected_icu_end = next((i for i in standard_icu if i >= isc_end_ka), standard_icu[-1])
            report += [
                "",
                f"- Tại cuối tuyến cáp {cable_section_mm2} mm2 dài {cable_length_m} m:",
                f"  + Tổng trở cáp: {z_cable:.4f} Ohm",
                f"  + Dòng ngắn mạch cuối tuyến: {isc_end_ka:.1f} kA",
                f"  => Aptomat nhánh cần Icu >= {selected_icu_end} kA",
                "- PHỐI HỢP BẢO VỆ (selectivity): aptomat nhánh phải cắt trước aptomat tổng — "
                "chọn dòng định mức nhánh <= 0.5 lần aptomat tổng, hoặc dùng aptomat tổng có "
                "chỉnh trễ thời gian (loại selective/thời gian ngắn).",
            ]
        else:
            report.append("- Nhập thêm `cable_length_m` và `cable_section_mm2` để tính dòng ngắn mạch "
                          "tại cuối tuyến và kiểm tra phối hợp bảo vệ giữa các cấp aptomat.")

        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính ngắn mạch: {e}"


@tool
def calc_cable_tray_size(cables_json: str, fill_ratio: float = 0.4, spare_percent: float = 30.0) -> str:
    """Chọn kích thước máng cáp / ống luồn dây theo tổng tiết diện các sợi cáp đi trong đó.

    cables_json: [{"ten": "Cáp chiếu sáng", "duong_kinh_mm": 18, "so_luong": 4}, ...].
    fill_ratio: hệ số điền đầy cho phép (máng cáp 0.4; ống luồn dây theo IEC là 0.4 cho
    nhiều sợi, 0.53 cho một sợi). spare_percent: dự phòng mở rộng sau này (%).
    """
    logger.info("Calculating cable tray size")
    try:
        items = json.loads(cables_json)
        if not isinstance(items, list) or not items:
            return "Lỗi: `cables_json` phải là danh sách JSON các loại cáp, không được rỗng."

        total_area, rows = 0.0, []
        for item in items:
            name = item.get("ten", "Không tên")
            d = float(item.get("duong_kinh_mm", 0))
            qty = int(item.get("so_luong", 1))
            area = math.pi * (d / 2) ** 2 * qty
            total_area += area
            rows.append(f"  - {name}: Ø{d} mm x {qty} sợi = {area:.0f} mm2")

        design_area = total_area * (1 + spare_percent / 100)
        required_area = design_area / fill_ratio

        # Máng cáp tiêu chuẩn (rộng x cao, mm).
        standard_trays = [(100, 50), (150, 50), (200, 100), (300, 100), (400, 100),
                          (500, 100), (600, 150), (800, 150), (1000, 200)]
        selected = next(((w, h) for w, h in standard_trays if w * h >= required_area), standard_trays[-1])

        # Ống luồn dây tiêu chuẩn (đường kính trong, mm).
        standard_conduits = [16, 20, 25, 32, 40, 50, 63, 75, 90, 110]
        conduit_d = math.sqrt(4 * required_area / math.pi)
        selected_conduit = next((c for c in standard_conduits if c >= conduit_d), standard_conduits[-1])

        report = [
            "TÍNH MÁNG CÁP / ỐNG LUỒN DÂY:",
            *rows,
            "",
            f"- Tổng tiết diện cáp: {total_area:.0f} mm2",
            f"- Cộng dự phòng {spare_percent:.0f}%: {design_area:.0f} mm2",
            f"- Tiết diện máng yêu cầu (hệ số điền đầy {fill_ratio}): {required_area:.0f} mm2",
            f"=> CHỌN MÁNG CÁP: {selected[0]} x {selected[1]} mm "
            f"(tiết diện {selected[0] * selected[1]} mm2)",
            f"=> Hoặc ỐNG LUỒN DÂY: Ø{selected_conduit} mm",
            "- Lưu ý: Cáp động lực và cáp tín hiệu/điều khiển phải đi riêng máng hoặc có vách "
            "ngăn để tránh nhiễu. Máng đi đứng cần kẹp cáp theo khoảng cách quy định.",
        ]
        return "\n".join(report)
    except json.JSONDecodeError as e:
        return f"Lỗi đọc JSON cáp: {e}. Định dạng đúng: [{{\"ten\":\"...\",\"duong_kinh_mm\":18,\"so_luong\":4}}]"
    except Exception as e:
        return f"Lỗi tính máng cáp: {e}"


@tool
def calc_lightning_protection(length_m: float, width_m: float, height_m: float,
                              protection_level: str = "III", soil_resistivity: float = 100.0,
                              rod_length_m: float = 2.4) -> str:
    """Thiết kế chống sét & tiếp địa: bán kính bảo vệ kim thu sét và số cọc tiếp địa cần đóng.

    - protection_level: cấp bảo vệ I/II/III/IV theo TCVN 9385 (I nghiêm ngặt nhất).
    - soil_resistivity: điện trở suất đất (Ohm.m) — đất sét ~50, đất pha cát ~200, đá ~1000.
    - rod_length_m: chiều dài một cọc tiếp địa (m).
    """
    logger.info(f"Calculating lightning protection: {length_m}x{width_m}x{height_m}m, level={protection_level}")
    try:
        # Bán kính quả cầu lăn theo cấp bảo vệ (TCVN 9385 / IEC 62305).
        rolling_sphere = {"I": 20, "II": 30, "III": 45, "IV": 60}
        level = (protection_level or "III").upper().strip()
        R = rolling_sphere.get(level, 45)
        if level not in rolling_sphere:
            level = "III (mặc định, không nhận diện được cấp nhập vào)"

        # Bán kính bảo vệ của kim thu sét theo phương pháp quả cầu lăn.
        if height_m >= R:
            protection_radius = R
        else:
            protection_radius = math.sqrt(2 * R * height_m - height_m ** 2)

        # Số kim cần thiết để phủ hết mái (bố trí lưới).
        area = length_m * width_m
        coverage = math.pi * protection_radius ** 2
        num_rods = max(1, math.ceil(area / coverage)) if coverage > 0 else 1

        # Điện trở tiếp địa của một cọc thẳng đứng (công thức Dwight rút gọn).
        d = 0.016  # đường kính cọc thép mạ đồng phổ biến D16
        r_single = (soil_resistivity / (2 * math.pi * rod_length_m)) * math.log(4 * rod_length_m / d)

        # Điện trở nối đất yêu cầu: <= 10 Ohm cho chống sét công trình thường (TCVN 9385).
        target = 10.0
        # Hệ số sử dụng khi ghép nhiều cọc song song (~0.75 với khoảng cách 2 lần chiều dài cọc).
        utilisation = 0.75
        num_ground_rods = max(1, math.ceil(r_single / (target * utilisation)))
        r_final = r_single / (num_ground_rods * utilisation)

        return "\n".join([
            f"CHỐNG SÉT & TIẾP ĐỊA (công trình {length_m}x{width_m}m, cao {height_m}m, cấp {level}):",
            f"- Bán kính quả cầu lăn: R = {R} m (TCVN 9385 / IEC 62305)",
            f"- Bán kính bảo vệ của một kim thu sét ở cao độ {height_m} m: {protection_radius:.1f} m",
            f"- Diện tích mái cần bảo vệ: {area:.0f} m2",
            f"=> Số kim thu sét tối thiểu: {num_rods} kim (bố trí lưới đều trên mái, "
            f"kết hợp dây dẫn sét dọc mép mái)",
            "",
            f"TIẾP ĐỊA (điện trở suất đất {soil_resistivity} Ohm.m, cọc dài {rod_length_m} m):",
            f"- Điện trở một cọc: {r_single:.1f} Ohm",
            f"- Yêu cầu: điện trở nối đất <= {target:.0f} Ohm",
            f"=> Số cọc tiếp địa cần đóng: {num_ground_rods} cọc "
            f"(khoảng cách giữa các cọc >= {2 * rod_length_m:.1f} m)",
            f"- Điện trở dự kiến sau khi ghép: {r_final:.1f} Ohm",
            "- Lưu ý: Phải ĐO điện trở nối đất thực tế sau thi công; nếu chưa đạt thì tăng số cọc, "
            "khoan giếng tiếp địa hoặc dùng hóa chất giảm điện trở. Hệ tiếp địa chống sét và "
            "tiếp địa an toàn điện phải được liên kết đẳng thế theo TCVN 9385.",
        ])
    except Exception as e:
        return f"Lỗi tính chống sét/tiếp địa: {e}"


@tool
def calc_emergency_lighting(corridor_length_m: float, open_area_m2: float = 0.0,
                            luminaire_spacing_m: float = 15.0, exit_sign_spacing_m: float = 20.0) -> str:
    """
    Tính số lượng đèn chiếu sáng sự cố và đèn EXIT/chỉ dẫn thoát nạn theo TCVN 3890/QCVN 06 —
    khác hoàn toàn `calc_lighting_qty` (chiếu sáng làm việc bình thường), hay bị nhầm lẫn hoặc
    bỏ sót khi chỉ tính chiếu sáng thường mà quên hệ chiếu sáng sự cố độc lập.
    Tham số:
    - corridor_length_m: Tổng chiều dài hành lang/lối thoát nạn cần chiếu sáng sự cố (m).
    - open_area_m2: Diện tích khu vực mở (sảnh, phòng lớn) cần chiếu sáng sự cố (m2, tùy chọn).
    - luminaire_spacing_m: Khoảng cách tối đa giữa các đèn sự cố dọc lối thoát nạn (m, mặc định 15).
    - exit_sign_spacing_m: Khoảng cách tối đa giữa các đèn EXIT/chỉ dẫn hướng thoát (m, mặc định 20).
    """
    logger.info(f"Calculating Emergency Lighting: corridor={corridor_length_m}m")
    try:
        if corridor_length_m <= 0 and open_area_m2 <= 0:
            return "Lỗi: Phải cung cấp chiều dài hành lang hoặc diện tích khu vực mở."

        qty_corridor = math.ceil(corridor_length_m / luminaire_spacing_m) + 1 if corridor_length_m > 0 else 0
        qty_exit_sign = math.ceil(corridor_length_m / exit_sign_spacing_m) + 1 if corridor_length_m > 0 else 0
        # Đèn sự cố khu vực mở: mật độ tối thiểu để đạt độ rọi 0.5 lux, ước tính 1 đèn/40m2.
        qty_open_area = math.ceil(open_area_m2 / 40.0) if open_area_m2 > 0 else 0

        report = [
            "CHIẾU SÁNG SỰ CỐ & CHỈ DẪN THOÁT NẠN (TCVN 3890 / QCVN 06:2022/BXD):",
        ]
        if corridor_length_m > 0:
            report += [
                f"- Đèn chiếu sáng sự cố dọc hành lang ({corridor_length_m} m, khoảng cách tối đa "
                f"{luminaire_spacing_m} m/đèn): {qty_corridor} đèn",
                f"- Đèn EXIT/chỉ dẫn hướng thoát (khoảng cách tối đa {exit_sign_spacing_m} m, bắt buộc "
                f"tại mọi cửa thoát nạn và điểm đổi hướng): {qty_exit_sign} đèn",
            ]
        if open_area_m2 > 0:
            report.append(f"- Đèn chiếu sáng sự cố khu vực mở ({open_area_m2} m2): {qty_open_area} đèn")

        report += [
            "- Độ rọi tối thiểu: 1 lux dọc tâm lối thoát nạn, 0.5 lux tại khu vực mở (TCVN 3890).",
            "- Thời gian duy trì hoạt động khi mất điện lưới: TỐI THIỂU 120 phút (ắc quy dự phòng "
            "tích hợp hoặc cấp nguồn ưu tiên từ máy phát).",
            "- Đèn EXIT BẮT BUỘC tại mọi cửa thoát nạn, đầu và cuối hành lang, mỗi điểm đổi hướng, "
            "và tại các nút giao hành lang — đây là hạng mục hay bị bỏ sót khi chỉ vẽ đèn chiếu "
            "sáng thường mà không tách riêng mạch chiếu sáng sự cố có nguồn ưu tiên.",
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Lỗi tính chiếu sáng sự cố: {e}"


# Bước tụ bù tiêu chuẩn (kVAr) phổ biến trên thị trường.
STANDARD_CAPACITOR_STEPS_KVAR = [2.5, 5, 7.5, 10, 12.5, 15, 20, 25, 30, 40, 50, 60, 75, 100]


@tool
def calc_power_factor_correction(active_power_kw: float, current_cos_phi: float,
                                 target_cos_phi: float = 0.95) -> str:
    """
    Tính dung lượng tụ bù công suất phản kháng (kVAr) cần thiết để nâng hệ số công suất
    (cos φ) hiện tại lên mức yêu cầu — hạng mục hay bị bỏ sót khi lập hồ sơ thiết kế tủ điện
    tổng, dù hầu hết công trình đều bị phạt tiền điện nếu cos φ dưới 0.9 (theo quy định EVN).
    Tham số:
    - active_power_kw: Công suất tác dụng (kW) tại điểm đặt tụ bù (thường tại tủ điện tổng).
    - current_cos_phi: Hệ số công suất hiện tại (chưa bù), VD 0.75.
    - target_cos_phi: Hệ số công suất mục tiêu sau khi bù (mặc định 0.95, tối thiểu EVN yêu
      cầu thường là 0.9).
    """
    logger.info(f"Calculating Power Factor Correction: P={active_power_kw}kW, cos1={current_cos_phi}")
    try:
        if not (0 < current_cos_phi <= 1) or not (0 < target_cos_phi <= 1):
            return "Lỗi: Hệ số công suất phải trong khoảng (0, 1]."
        if target_cos_phi <= current_cos_phi:
            return "Lỗi: Hệ số công suất mục tiêu phải LỚN HƠN hệ số công suất hiện tại."

        tan_phi1 = math.tan(math.acos(current_cos_phi))
        tan_phi2 = math.tan(math.acos(target_cos_phi))
        q_required_kvar = active_power_kw * (tan_phi1 - tan_phi2)

        selected_kvar = STANDARD_CAPACITOR_STEPS_KVAR[-1]
        for step in STANDARD_CAPACITOR_STEPS_KVAR:
            if step >= q_required_kvar:
                selected_kvar = step
                break

        # Dòng điện giảm được sau khi bù (tại cùng công suất tác dụng, điện áp 380V 3 pha).
        current_before = active_power_kw * 1000 / (math.sqrt(3) * 380 * current_cos_phi)
        current_after = active_power_kw * 1000 / (math.sqrt(3) * 380 * target_cos_phi)
        current_reduction_pct = (1 - current_after / current_before) * 100 if current_before > 0 else 0

        return "\n".join([
            f"Tính tụ bù công suất phản kháng (P = {active_power_kw} kW, cos φ: {current_cos_phi} "
            f"-> {target_cos_phi}):",
            f"- Công suất phản kháng cần bù (Qc): {q_required_kvar:.1f} kVAr",
            f"=> CHỌN TỦ BÙ TIÊU CHUẨN: {selected_kvar} kVAr (nên chia nhiều cấp/bước bù tự động "
            f"theo tải thực tế thay vì bù cố định một cấp nếu tải biến động lớn)",
            f"- Dòng điện giảm sau khi bù: {current_before:.1f} A -> {current_after:.1f} A "
            f"(giảm {current_reduction_pct:.1f} %)",
            "- Tụ bù nên đặt gần trung tâm phụ tải (tủ điện tổng hoặc tủ phân phối tầng có tải "
            "cảm kháng lớn: động cơ, máy biến áp) để giảm tổn thất trên đường dây phía trước.",
            "- BẮT BUỘC có bộ điều khiển bù tự động (relay cos φ) nếu tải biến động theo thời gian, "
            "tránh bù dư gây quá áp khi tải thấp.",
        ])
    except Exception as e:
        return f"Lỗi tính tụ bù công suất: {e}"
