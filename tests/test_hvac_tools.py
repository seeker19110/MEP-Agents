from src.hvac_tools import (
    calc_psychrometrics,
    calc_duct_size,
    calc_cooling_load,
    calc_chw_pipe_size,
    calc_pump_fan_power,
    calc_ventilation_rate,
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
