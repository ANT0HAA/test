"""Тесты «завод в целом»: марки, склады, штат, экономика, экология (calc/plant.py)."""
from calc import quality_grades, warehouses, staffing, ecology, CapexInput, capex_estimate, build_spec


def test_quality_grades_by_product():
    assert "М300" in quality_grades("клинкерный кирпич")["strength"]
    assert quality_grades("облицовочный кирпич")["frost"].startswith("F50")
    # неизвестный продукт → дефолтные марки
    assert quality_grades("нечто")["strength"]
    assert quality_grades("рядовой")["standard"].startswith("ГОСТ 530")


def test_warehouses_scale():
    w = warehouses(annual_clay_t=33000, pieces_per_year=15_000_000, piece_mass_kg=2.6)
    assert w["raw_store_t"] > 0 and w["fg_pallets"] > 0 and w["fg_area_m2"] > 0


def test_staffing_shifts():
    one = staffing(shifts_per_day=1)
    two = staffing(shifts_per_day=2)
    assert two["workers_total"] == 2 * one["workers_total"]
    assert two["headcount"] > two["workers_total"]   # + ИТР/АУП


def test_ecology_co2():
    e = ecology(gas_m3_per_year=2_400_000)
    assert abs(e["co2_t_per_year"] - 4560) < 5      # 2.4e6 × 1.9 / 1000
    assert e["measures"]


def test_capex_and_payback():
    # без цены продажи — окупаемость не считается
    c0 = capex_estimate(CapexInput(total_area_m2=9576, cost_per_1000_rub=2255))
    assert c0["total_rub"] > 0 and c0["payback_years"] is None
    # с ценой выше себестоимости — окупаемость есть
    c1 = capex_estimate(CapexInput(total_area_m2=9576, pieces_per_year=15_000_000,
                                   cost_per_1000_rub=2255, sell_price_per_1000_rub=12000))
    assert c1["payback_years"] and c1["payback_years"] > 0


def test_build_spec_includes_plant():
    s = build_spec({"product": "облицовочный кирпич", "capacity": "30000 шт/смену"})
    for key in ("grades", "warehouses", "staffing", "ecology", "capex"):
        assert key in s, key
