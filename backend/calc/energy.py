"""
Энергобаланс «печь → сушило» и рекуперация тепла.

Тепло зоны охлаждения туннельной печи частично передаётся в сушило (типовое
решение кирпичных заводов). Считаем потребность сушила на испарение влаги,
рекуперируемое тепло печи и долю покрытия, остаток покрывается топливом.
Коэффициенты — типовые, уточняются по теплотехническому расчёту.
"""
from pydantic import BaseModel, Field

_GAS_LHV_KCAL = 8000.0           # теплота сгорания природного газа, ккал/м³
# Уд. тепло на испарение + подогрев влаги в сушиле, ккал/кг влаги (типовое)
_EVAP_KCAL_PER_KG = 700.0


class EnergyInput(BaseModel):
    water_removed_kg_per_h: float = Field(..., description="Удаляемая в сушиле влага, кг/ч")
    kiln_heat_kcal_per_h: float = Field(..., description="Тепло, подводимое в печь, ккал/ч")
    recovery_share: float = Field(0.45, description="Доля тепла печи, рекуперируемого в сушило")


class EnergyResult(BaseModel):
    dryer_demand_kcal_per_h: float
    kiln_recoverable_kcal_per_h: float
    covered_kcal_per_h: float
    coverage_pct: float                  # доля потребности сушила, покрытая теплом печи
    net_dryer_fuel_kcal_per_h: float     # остаток, покрываемый топливом
    net_dryer_gas_m3_per_h: float
    notes: list[str] = []


def energy_balance(inp: EnergyInput) -> EnergyResult:
    if inp.water_removed_kg_per_h < 0 or inp.kiln_heat_kcal_per_h < 0:
        raise ValueError("Расходы тепла/влаги не могут быть отрицательными")
    demand = inp.water_removed_kg_per_h * _EVAP_KCAL_PER_KG
    recoverable = inp.kiln_heat_kcal_per_h * max(0.0, min(1.0, inp.recovery_share))
    covered = min(demand, recoverable)
    coverage = (covered / demand * 100.0) if demand > 0 else 0.0
    net = max(0.0, demand - covered)
    notes = [
        f"Потребность сушила {demand:,.0f} ккал/ч при уд. {_EVAP_KCAL_PER_KG:g} ккал/кг влаги."
        .replace(",", " "),
        f"Рекуперация {inp.recovery_share*100:g}% тепла печи покрывает {coverage:.0f}% "
        f"потребности сушила.",
        "Доля рекуперации и уд. тепло — типовые, уточняются теплотехническим расчётом.",
    ]
    return EnergyResult(
        dryer_demand_kcal_per_h=round(demand),
        kiln_recoverable_kcal_per_h=round(recoverable),
        covered_kcal_per_h=round(covered),
        coverage_pct=round(coverage, 1),
        net_dryer_fuel_kcal_per_h=round(net),
        net_dryer_gas_m3_per_h=round(net / _GAS_LHV_KCAL, 1),
        notes=notes,
    )
