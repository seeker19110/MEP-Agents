from src.elec_tools import calc_cable_size, calc_breaker_size, calc_lighting_qty


def test_calc_cable_size_three_phase():
    result = calc_cable_size.invoke({"power_kw": 10, "voltage": 380, "cos_phi": 0.85, "phase": 3})
    assert "mm2" in result
    assert "Dòng điện tính toán" in result


def test_calc_cable_size_single_phase_forces_220v():
    result = calc_cable_size.invoke({"power_kw": 2, "phase": 1})
    assert "mm2" in result


def test_calc_breaker_size_picks_standard_rating():
    result = calc_breaker_size.invoke({"power_kw": 15, "phase": 3})
    assert "Chọn MCCB/MCB định mức" in result


def test_calc_lighting_qty_rounds_up():
    result = calc_lighting_qty.invoke({"area_m2": 20, "required_lux": 300, "lumen_per_lamp": 3000})
    assert "bộ đèn" in result
