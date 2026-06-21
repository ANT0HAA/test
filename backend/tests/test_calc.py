"""
Тесты расчётного ядра. Проверяют, что формулы воспроизводят числа из проектных
документов заказчика и корректно масштабируют нормы.
"""
from calc import (
    ProductionInput, production_program, DryerInput, dryer_calc,
    EquipmentInput, select_equipment, build_summary, parse_capacity,
    ElectricalInput, electrical_load, AreasInput, estimate_areas,
    EstimateInput, cost_estimate,
)


def test_dryer_matches_document_example():
    # Значения по умолчанию = пример из «Расчёт сушил.docx».
    # Документ округляет l до 32.2 в промежуточных шагах → допуск ~2 ккал/кг.
    r = dryer_calc(DryerInput())
    assert abs(r.air_per_kg_moisture - 32.26) < 0.05   # l = 1000/(48-17)
    assert abs(r.heat_per_kg_moisture - 758.6) < 2.5   # q ≈ 758,6 ккал/кг
    assert abs(r.heat_balance_per_kg - 758.4) < 2.5    # баланс ≈ 758


def test_dryer_carrier_flow():
    r = dryer_calc(DryerInput(moisture_kg_per_h=150.25))
    # G = 150.25 * 49.5 ≈ 7437,4 кг/ч ; V = G/0.922 ≈ 8066,6 м³/ч (из «Варианты расчёта сушил»)
    assert abs(r.carrier_kg_per_h - 7437.4) < 1.0
    assert abs(r.carrier_m3_per_h - 8066.6) < 2.0


def test_dryer_validation():
    import pytest
    with pytest.raises(ValueError):
        dryer_calc(DryerInput(d1=50, d2=40))


def test_production_scales_norms():
    # 1 000 000 шт/год → ресурсы = норма × 1000
    r = production_program(ProductionInput(pieces_per_year=1_000_000))
    assert r.resources_per_year["clay_main_t"] == 1120.0     # 1.12 × 1000
    assert r.resources_per_year["gas_m3"] == 160000.0        # 160 × 1000
    assert r.resources_per_year["electricity_kwh"] == 180000.0
    assert r.pieces_per_year == 1_000_000


def test_production_from_per_shift():
    r = production_program(ProductionInput(pieces_per_shift=30000, shifts_per_day=2,
                                           work_days_per_year=250))
    assert r.pieces_per_year == 30000 * 2 * 250              # 15 млн/год
    assert r.pieces_per_hour > 0
    assert r.mass_per_year_t > 0


def test_parse_capacity():
    assert parse_capacity("30000 шт/смену").pieces_per_shift == 30000
    assert parse_capacity("60 млн шт/год").pieces_per_year == 60_000_000
    assert parse_capacity("15000000 в год").pieces_per_year == 15_000_000
    assert parse_capacity("") is None


def test_equipment_selection_scales():
    small = select_equipment(EquipmentInput(pieces_per_hour=1000))   # ~3.4*1.2/1000... малая
    big = select_equipment(EquipmentInput(pieces_per_hour=10000))
    assert big.raw_throughput_tph > small.raw_throughput_tph
    assert any(i.role == "Обжиг" for i in big.items)
    assert all(i.qty >= 1 for i in big.items)


def test_estimate_matches_document_cost():
    # Себестоимость на 1000 шт по нормам и ценам документа = 2255.5 руб
    prog = production_program(ProductionInput(pieces_per_year=1_000_000))
    est = cost_estimate(EstimateInput(resources_per_year=prog.resources_per_year,
                                      pieces_per_year=prog.pieces_per_year))
    assert abs(est.cost_per_1000_rub - 2255.5) < 1.0


def test_electrical_and_areas():
    el = electrical_load(ElectricalInput(annual_kwh=2_700_000, operating_hours=4000))
    assert el.installed_power_kw > 0 and el.transformer_kva >= 250
    ar = estimate_areas(AreasInput(pieces_per_year=15_000_000))
    assert ar.total_m2 > 0 and "Обжигательный корпус" in ar.areas_m2


def test_build_summary_uses_inputs():
    s = build_summary({"product": "облицовочный кирпич", "capacity": "30000 шт/смену"})
    assert "Производственная программа" in s
    assert "Оборудование" in s
    assert "Электроснабжение" in s
    assert "Себестоимость" in s
    assert "Площади корпусов" in s
