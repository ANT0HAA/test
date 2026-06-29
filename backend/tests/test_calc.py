"""
Тесты расчётного ядра. Проверяют, что формулы воспроизводят числа из проектных
документов заказчика и корректно масштабируют нормы.
"""
from calc import (
    ProductionInput, production_program, DryerInput, dryer_calc,
    EquipmentInput, select_equipment, build_summary, parse_capacity,
    ElectricalInput, electrical_load, AreasInput, estimate_areas, buildings_from_areas,
    EstimateInput, cost_estimate,
    Component, ShihtaInput, shihta_calc,
    build_spec,
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
    # разговорное «15м» = 15 млн (не 15 штук); «смену» не трогаем
    assert parse_capacity("15м в год").pieces_per_year == 15_000_000
    assert parse_capacity("15 м/год").pieces_per_year == 15_000_000
    assert parse_capacity("30000 шт/смену").pieces_per_shift == 30000


def test_build_spec_robust_to_degenerate_input():
    from calc import build_spec
    # крайне малый объём → расчёты обжига/баланса вырождены, но спецификация НЕ падает
    s = build_spec({"product": "рядовой кирпич", "capacity": "5 в год"})
    assert s["has_data"] is True
    assert "production" in s and "cost" in s        # ядро на месте
    assert "firing" not in s                        # вырожденный раздел опущен, без 500


def test_equipment_selection_scales():
    small = select_equipment(EquipmentInput(pieces_per_hour=1000))   # ~3.4*1.2/1000... малая
    big = select_equipment(EquipmentInput(pieces_per_hour=10000))
    assert big.raw_throughput_tph > small.raw_throughput_tph
    assert any(i.role == "Обжиг" for i in big.items)
    assert all(i.qty >= 1 for i in big.items)


def test_equipment_full_line_and_cars():
    r = select_equipment(EquipmentInput(pieces_per_hour=3750, piece_mass_kg=2.6))
    roles = {i.role for i in r.items}
    # сквозная линия — все ключевые переделы присутствуют
    for role in ("Подготовка", "Формование", "Резка", "Садка", "Сушка", "Обжиг",
                 "Пакетирование", "Транспорт"):
        assert role in roles, role
    # вагонеточный парк рассчитан и масштабируется со временем обжига
    cars = {i.name: i.qty for i in r.items if i.role == "Транспорт"}
    assert cars["Вагонетки печные"] > 0 and cars["Вагонетки сушильные"] > 0
    more = select_equipment(EquipmentInput(pieces_per_hour=3750, piece_mass_kg=2.6,
                                           kiln_residence_h=60))
    kiln_more = next(i.qty for i in more.items if i.name == "Вагонетки печные")
    assert kiln_more > cars["Вагонетки печные"]   # дольше обжиг → больше вагонеток


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


def test_buildings_from_areas():
    # При 15 млн шт/год габариты совпадают с базовыми корпусами генплана
    b = {x["name"]: x for x in buildings_from_areas(15_000_000)}
    assert b["Обжигательный корпус"]["width_m"] == 18 and b["Обжигательный корпус"]["length_m"] == 120
    assert b["Формовочный цех"]["width_m"] == 24
    # При большем объёме корпуса крупнее
    big = {x["name"]: x for x in buildings_from_areas(40_000_000)}
    assert big["Обжигательный корпус"]["length_m"] > 120


def test_shihta_matches_document():
    # Глина 31.9% при SiO2 52.43% даёт 16.72% SiO2 (число из «Расчёт состава шихты»).
    # Остальные компоненты без оксидов (суммируем до 100%).
    inp = ShihtaInput(components=[
        Component(name="глина огнеупорная", fraction=31.9, oxides={"SiO2": 52.43, "Al2O3": 32.21}),
        Component(name="прочее", fraction=68.1, oxides={}),
    ])
    r = shihta_calc(inp)
    assert abs(r.composition["SiO2"] - 16.72) < 0.05
    assert abs(r.composition["Al2O3"] - 10.27) < 0.05


def test_shihta_normalizes():
    r = shihta_calc(ShihtaInput(components=[
        Component(name="A", fraction=40, oxides={"SiO2": 50}),
        Component(name="B", fraction=60, oxides={"SiO2": 80}),
    ]))
    assert abs(r.composition["SiO2"] - 68.0) < 0.01   # 40*50/100 + 60*80/100
    assert r.normalized_fractions["A"] == 40.0


def test_build_spec_structured():
    spec = build_spec({"product": "облицовочный кирпич", "capacity": "30000 шт/смену"})
    assert spec["has_data"] is True
    assert spec["production"]["pieces_per_year"] == 15_000_000
    assert spec["cost"]["cost_per_1000_rub"] > 0
    assert spec["electrical"]["transformer_kva"] >= 250
    assert any(b["name"] == "Обжигательный корпус" for b in spec["buildings"])
    assert spec["areas"]["total_m2"] > 0


def test_build_spec_no_capacity():
    spec = build_spec({"product": "кирпич"})
    assert spec["has_data"] is False
    assert spec["inputs"]["product"] == "кирпич"


def test_build_summary_uses_inputs():
    s = build_summary({"product": "облицовочный кирпич", "capacity": "30000 шт/смену"})
    assert "Производственная программа" in s
    assert "Оборудование" in s
    assert "Электроснабжение" in s
    assert "Себестоимость" in s
    assert "Площади корпусов" in s
