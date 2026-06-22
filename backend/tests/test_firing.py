"""Тесты режима обжига (calc/firing.py) — без внешних сервисов."""
import pytest
from calc import FiringInput, firing_calc, build_spec


def test_firing_zones_and_gas():
    r = firing_calc(FiringInput(pieces_per_hour=3750, piece_mass_kg=2.6,
                                max_temp_c=1000, residence_h=30, specific_heat_kcal_kg=450))
    # 3 зоны, доли в сумме 100%
    assert len(r.zones) == 3
    assert abs(sum(z.share_pct for z in r.zones) - 100) < 1
    assert abs(sum(z.time_h for z in r.zones) - 30) < 0.5
    # газ: тепло = 450 × 3750 × 2.6 = 4 387 500 ккал/ч ; /8000 = 548.4 м³/ч
    assert abs(r.gas_m3_per_hour - 548.4) < 1.0
    assert r.gas_m3_per_1000 > 0


def test_firing_scales_with_throughput():
    a = firing_calc(FiringInput(pieces_per_hour=2000))
    b = firing_calc(FiringInput(pieces_per_hour=4000))
    assert b.gas_m3_per_hour > a.gas_m3_per_hour
    # уд. расход на 1000 не зависит от потока (при той же массе)
    assert abs(a.gas_m3_per_1000 - b.gas_m3_per_1000) < 0.1


def test_firing_validation():
    with pytest.raises(ValueError):
        firing_calc(FiringInput(pieces_per_hour=0))


def test_build_spec_includes_firing():
    spec = build_spec({"product": "облицовочный кирпич", "capacity": "30000 шт/смену"})
    assert "firing" in spec and spec["firing"]["zones"]
    assert spec["firing"]["gas_m3_per_hour"] > 0
