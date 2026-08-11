from src.plumb_tools import calc_water_pipe, calc_water_tank, calc_plumbing_pump_head


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
