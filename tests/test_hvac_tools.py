from src.hvac_tools import (
    calc_psychrometrics,
    calc_duct_size,
    calc_cooling_load,
    calc_chw_pipe_size,
    calc_pump_fan_power,
    calc_ventilation_rate,
    calc_cooling_load_detailed,
    calc_duct_total_pressure_loss,
    calc_chiller_ahu_selection,
    calc_refrigerant_pipe_size,
)


def test_calc_psychrometrics_returns_enthalpy_and_dewpoint():
    result = calc_psychrometrics.invoke({"T_drybulb": 25, "RH": 50})
    assert "Entanpi" in result
    assert "Nhiệt độ đọng sương" in result


def test_calc_duct_size_returns_round_and_rect_options():
    result = calc_duct_size.invoke({"airflow_lps": 500, "max_velocity": 8.0})
    assert "Ống tròn tối thiểu" in result


def test_calc_duct_size_rejects_zero_airflow():
    result = calc_duct_size.invoke({"airflow_lps": 0})
    assert "lớn hơn 0" in result


def test_calc_cooling_load_office():
    result = calc_cooling_load.invoke({"area_m2": 50, "space_type": "van_phong"})
    assert "10.00 kW" in result


def test_calc_chw_pipe_size_selects_standard_dn():
    result = calc_chw_pipe_size.invoke({"cooling_load_kw": 100, "delta_t": 5.5})
    assert "DN" in result


def test_calc_pump_fan_power_applies_safety_factor():
    result = calc_pump_fan_power.invoke({"flow_rate_lps": 50, "pressure_drop_pa": 500, "efficiency": 0.7})
    assert "Hệ số an toàn 1.15" in result


def test_calc_ventilation_rate():
    result = calc_ventilation_rate.invoke({"area_m2": 100, "height_m": 3, "ach": 6})
    # volume = 300 m3, flow = 1800 m3/h
    assert "1800" in result


def test_calc_cooling_load_detailed_breaks_down_components():
    result = calc_cooling_load_detailed.invoke({
        "area_m2": 30, "occupancy": 5, "equipment_load_w": 500,
        "window_area_m2": 8, "wall_area_m2": 15, "roof_area_m2": 0,
        "orientation": "tay", "fresh_air_lps": 50,
    })
    assert "TỔNG TẢI LẠNH" in result
    assert "Tổng nhiệt hiện" in result
    assert "Tổng nhiệt ẩn" in result


def test_calc_cooling_load_detailed_zero_occupancy_no_people_load():
    result = calc_cooling_load_detailed.invoke({"area_m2": 10, "occupancy": 0})
    assert "0 W hiện + 0 W ẩn" in result


def test_calc_duct_total_pressure_loss_sums_friction_and_local():
    result = calc_duct_total_pressure_loss.invoke({
        "duct_length_m": 50, "velocity_ms": 6, "friction_rate_pa_m": 1.0,
        "elbow_90_qty": 3, "tee_branch_qty": 1, "damper_qty": 1, "diffuser_qty": 2,
    })
    assert "TỔNG CỘT ÁP QUẠT CẦN CHỌN" in result
    assert "Pa" in result


def test_calc_chiller_ahu_selection_single_unit():
    result = calc_chiller_ahu_selection.invoke({"cooling_load_kw": 25, "equipment_type": "chiller"})
    assert "Chọn 1 cụm công suất danh định" in result


def test_calc_chiller_ahu_selection_multiple_units_for_large_load():
    result = calc_chiller_ahu_selection.invoke({"cooling_load_kw": 2000, "equipment_type": "chiller"})
    assert "lắp" in result and "cụm song song" in result


def test_calc_chiller_ahu_selection_rejects_unknown_type():
    result = calc_chiller_ahu_selection.invoke({"cooling_load_kw": 10, "equipment_type": "boiler"})
    assert "Lỗi" in result


def test_calc_refrigerant_pipe_size_gas_larger_than_liquid():
    gas_result = calc_refrigerant_pipe_size.invoke({"capacity_kw": 14, "pipe_line": "gas"})
    liquid_result = calc_refrigerant_pipe_size.invoke({"capacity_kw": 14, "pipe_line": "liquid"})
    assert "Ø" in gas_result and "Ø" in liquid_result


def test_calc_refrigerant_pipe_size_rejects_invalid_line():
    result = calc_refrigerant_pipe_size.invoke({"capacity_kw": 10, "pipe_line": "vapor"})
    assert "Lỗi" in result
