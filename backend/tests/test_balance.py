"""
Тесты материального баланса по переделам (calc/balance.py).
Проверяют сохранение масс и масштабирование (без внешних сервисов).
"""
import pytest
from calc import BalanceInput, material_balance, build_spec


def test_balance_stages_and_finished_mass():
    r = material_balance(BalanceInput(pieces_per_year=15_000_000, piece_mass_kg=3.4))
    by = {s.name: s for s in r.stages}
    # Готовая продукция = шт × масса = 15e6 × 3.4 / 1000 = 51 000 т/год
    fin = next(s for s in r.stages if s.name.startswith("Готовая"))
    assert abs(fin.t_per_year - 51000) < 1
    # Масса убывает: сырьё(сухое) < формование(влажный) ; готовая < на обжиг
    assert by["Формование (брус, влажный)"].t_per_year > by["Сырьё (сухое: глина+отощитель)"].t_per_year
    assert by["После сушки (на обжиг)"].t_per_year > fin.t_per_year


def test_balance_conservation():
    # Скелет(сырьё сухое) ≈ готовая + ППП (на поступивших на обжиг — приближённо ≥ готовой)
    r = material_balance(BalanceInput(pieces_per_year=1_000_000, piece_mass_kg=3.4,
                                      loi_pct=6.0, firing_reject_pct=0, drying_reject_pct=0))
    fin = next(s for s in r.stages if s.name.startswith("Готовая")).t_per_year
    raw = r.raw_dry_t_per_year
    # без брака: сухое сырьё = готовая + ППП
    assert abs(raw - (fin + r.loi_removed_firing_t)) < 1.0
    assert r.forming_water_t_per_year > 0 and r.water_removed_drying_t > 0


def test_balance_rejects_increase_input():
    base = material_balance(BalanceInput(pieces_per_year=1_000_000, drying_reject_pct=0, firing_reject_pct=0))
    rej = material_balance(BalanceInput(pieces_per_year=1_000_000, drying_reject_pct=5, firing_reject_pct=5))
    # с браком сырья нужно больше
    assert rej.raw_dry_t_per_year > base.raw_dry_t_per_year


def test_balance_validation():
    with pytest.raises(ValueError):
        material_balance(BalanceInput(pieces_per_year=0))


def test_build_spec_includes_balance():
    spec = build_spec({"product": "облицовочный кирпич", "capacity": "30000 шт/смену"})
    assert "balance" in spec and spec["balance"]["stages"]
    assert any(s["name"].startswith("Готовая") for s in spec["balance"]["stages"])
