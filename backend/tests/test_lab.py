"""
Тесты лабораторно-технологических расчётов (calc/lab.py).
Проверяют формулы и пороги стандартных методик (без внешних данных/сервисов).
"""
from calc import (
    plasticity_number, plasticity_group, sensitivity_group, ClaySource,
    average_blend, recommend_leaning, clay_yard, select_feeder, forming_guidance,
    LabInput, lab_report,
)


def test_plasticity_number_and_group():
    assert plasticity_number(38.0, 20.0) == 18.0
    assert plasticity_group(5) == "малопластичное"
    assert plasticity_group(10) == "умереннопластичное"
    assert plasticity_group(18) == "среднепластичное"
    assert plasticity_group(30) == "высокопластичное"


def test_sensitivity_group():
    assert sensitivity_group(0.5) == "малочувствительное"
    assert sensitivity_group(1.5) == "среднечувствительное"
    assert sensitivity_group(3.0) == "высокочувствительное"


def test_average_blend_equal_parts():
    clays = [ClaySource(name="A", plasticity=30), ClaySource(name="B", plasticity=12),
             ClaySource(name="C", plasticity=18)]
    ip, _ = average_blend(clays)
    assert ip == 20.0   # (30+12+18)/3


def test_average_blend_oxides_weighted():
    clays = [ClaySource(name="A", plasticity=20, fraction=40, oxides={"SiO2": 50}),
             ClaySource(name="B", plasticity=20, fraction=60, oxides={"SiO2": 80})]
    _, ox = average_blend(clays)
    assert abs(ox["SiO2"] - 68.0) < 0.01   # 0.4*50 + 0.6*80


def test_recommend_leaning_needed_for_high_plasticity():
    clays = [ClaySource(name="A", plasticity=28), ClaySource(name="B", plasticity=26)]
    r = recommend_leaning(clays, target_plasticity=12.0, sand_plasticity=0.0)
    assert r.need_leaning is True
    # x = (27-12)/(27-0) = 0.555 → ограничено 40%
    assert r.sand_fraction_pct == 40.0
    assert r.blended_group == "высокопластичное"


def test_recommend_leaning_not_needed():
    clays = [ClaySource(name="A", plasticity=11), ClaySource(name="B", plasticity=10)]
    r = recommend_leaning(clays, target_plasticity=12.0)
    assert r.need_leaning is False
    assert r.sand_fraction_pct == 0.0


def test_clay_yard_layers():
    y = clay_yard(annual_clay_t=33000, store_days=30, height_m=4.0, layer_thickness_m=0.3)
    assert y.layers == 13          # round(4/0.3)
    assert y.stockpile_t > 0 and y.area_m2 > 0


def test_select_feeder_caps_at_max():
    # 3 глины + добавка = 4 компонента, но при усреднении ≤ 3 питателей
    f = select_feeder(raw_tph=12.0, components=4, max_feeders=3, averaging=True)
    assert f.feeders_used == 3


def test_forming_guidance_methods():
    assert forming_guidance("пластическое")["method"] == "пластическое"
    assert forming_guidance("полусухое прессование")["method"] == "полусухое"
    # неизвестный способ → пластическое по умолчанию
    assert forming_guidance("непонятно")["method"] == "пластическое"


def test_lab_report_assembles():
    inp = LabInput(
        clays=[ClaySource(name="Глина-1", plasticity=28),
               ClaySource(name="Глина-2", plasticity=22),
               ClaySource(name="Глина-3", plasticity=18)],
        forming="пластическое", annual_clay_t=33000, raw_tph=12.0,
        sensitivity_coeff=2.5, max_feeders=3)
    r = lab_report(inp)
    assert r["has_data"] is True
    assert r["blend"]["clays"] == 3
    assert r["leaning"]["need_leaning"] is True       # средняя 22.7 > 12
    assert r["feeders"]["feeders_used"] == 3          # 3 глины + добавка, лимит 3
    assert r["sensitivity"]["group"] == "высокочувствительное"
    assert r["yard"]["layers"] >= 1
    assert len(r["control_points"]) >= 3
