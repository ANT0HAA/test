"""Тесты энергобаланса печь→сушило (calc/energy.py)."""
import pytest
from calc import EnergyInput, energy_balance, build_spec


def test_energy_recovery_partial():
    # потребность = 1000 кг/ч × 700 = 700 000 ккал/ч; печь даёт 1 000 000 × 0.45 = 450 000
    r = energy_balance(EnergyInput(water_removed_kg_per_h=1000, kiln_heat_kcal_per_h=1_000_000,
                                   recovery_share=0.45))
    assert r.dryer_demand_kcal_per_h == 700_000
    assert r.kiln_recoverable_kcal_per_h == 450_000
    assert abs(r.coverage_pct - 64.3) < 0.5
    assert r.net_dryer_gas_m3_per_h > 0           # остаток покрывается топливом


def test_energy_full_cover():
    # печи хватает с избытком → покрытие 100%, догрев 0
    r = energy_balance(EnergyInput(water_removed_kg_per_h=100, kiln_heat_kcal_per_h=5_000_000,
                                   recovery_share=0.45))
    assert r.coverage_pct == 100.0
    assert r.net_dryer_gas_m3_per_h == 0.0


def test_energy_validation():
    with pytest.raises(ValueError):
        energy_balance(EnergyInput(water_removed_kg_per_h=-1, kiln_heat_kcal_per_h=1))


def test_build_spec_includes_energy():
    spec = build_spec({"product": "облицовочный кирпич", "capacity": "30000 шт/смену"})
    assert "energy" in spec and spec["energy"]["dryer_demand_kcal_per_h"] > 0
