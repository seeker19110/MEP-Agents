import math
from src.ff_tools import calc_sprinkler_qty, calc_fire_pump, calc_extinguisher_qty


def test_calc_sprinkler_qty_light_hazard():
    result = calc_sprinkler_qty.invoke({"area_m2": 120, "hazard_class": "light"})
    expected_qty = math.ceil(120 / 12.0)
    assert f"{expected_qty} đầu" in result


def test_calc_sprinkler_qty_extra_hazard_smaller_coverage():
    result = calc_sprinkler_qty.invoke({"area_m2": 60, "hazard_class": "extra"})
    expected_qty = math.ceil(60 / 6.0)
    assert f"{expected_qty} đầu" in result


def test_calc_fire_pump_ordinary():
    result = calc_fire_pump.invoke({"hazard_class": "ordinary"})
    assert "1000 GPM" in result


def test_calc_extinguisher_qty():
    result = calc_extinguisher_qty.invoke({"area_m2": 500})
    expected_qty = math.ceil(500 / 50.0)
    assert f"{expected_qty} bình" in result
