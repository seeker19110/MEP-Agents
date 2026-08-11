from src.plumb_tools import (
    calc_water_pipe,
    calc_water_tank,
    calc_plumbing_pump_head,
    calc_drainage_pipe,
    calc_rainwater_drainage,
    calc_septic_tank,
    calc_hot_water_system,
)


def test_calc_water_pipe_returns_dn():
    result = calc_water_pipe.invoke({"fixture_units": 10})
    assert "DN" in result


def test_calc_water_tank_computes_underground_and_roof():
    result = calc_water_tank.invoke({"population": 100, "liters_per_person": 200})
    assert "Bể ngầm" in result
    assert "Bể mái" in result


def test_calc_plumbing_pump_head_includes_residual_head():
    result = calc_plumbing_pump_head.invoke({"building_height_m": 30, "longest_pipe_length_m": 50})
    # total_head = 30 + 50*0.1 + 15 = 50.0
    assert "50.0 mH2O" in result


def test_calc_drainage_pipe_selects_standard_dn_and_slope():
    result = calc_drainage_pipe.invoke({"dfu": 100})
    assert "DN" in result
    assert "Độ dốc tối thiểu" in result


def test_calc_drainage_pipe_uses_lower_slope_for_large_dn():
    # dfu=1000 -> needs DN200 (>100mm) -> slope should default to 1.0%
    result = calc_drainage_pipe.invoke({"dfu": 1000})
    assert "i = 1.0%" in result


def test_calc_drainage_pipe_uses_higher_slope_for_small_dn():
    # dfu=10 -> fits DN50 (<=100mm) -> slope should default to 2.0%
    result = calc_drainage_pipe.invoke({"dfu": 10})
    assert "i = 2.0%" in result


def test_calc_rainwater_drainage_computes_flow_and_dn():
    result = calc_rainwater_drainage.invoke({"roof_area_m2": 200, "rainfall_intensity_mm_h": 100})
    # Q = 1.0 * 100 * 200 / 3600 = 5.56 L/s
    assert "5.56 L/s" in result
    assert "DN" in result


def test_calc_septic_tank_sums_water_and_sludge_volume():
    result = calc_septic_tank.invoke({"population": 50})
    assert "DUNG TÍCH BỂ TỰ HOẠI ĐỀ XUẤT" in result


def test_calc_hot_water_system_computes_power():
    result = calc_hot_water_system.invoke({"population": 20, "liters_per_person_per_day": 40, "usage_hours": 2})
    assert "Công suất đun đề xuất" in result


def test_calc_hot_water_system_rejects_invalid_temperatures():
    result = calc_hot_water_system.invoke({
        "population": 10, "cold_water_temp_c": 60, "hot_water_temp_c": 60,
    })
    assert "Lỗi" in result
