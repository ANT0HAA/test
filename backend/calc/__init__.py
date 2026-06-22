"""
Расчётное ядро бюро — детерминированные инженерные расчёты.

В отличие от текстовых ответов модели, эти функции дают проверяемые цифры по
методикам из проектных документов. Агенты опираются на них (а не «придумывают»).

Модули:
  • production — производственная программа и потребность ресурсов
  • dryer      — теплотехнический расчёт сушила (расход воздуха/теплоносителя)
"""
from .production import ProductionInput, ProductionResult, production_program
from .dryer import DryerInput, DryerResult, dryer_calc
from .equipment import EquipmentInput, EquipmentResult, select_equipment
from .electrical import ElectricalInput, ElectricalResult, electrical_load
from .areas import AreasInput, AreasResult, estimate_areas, buildings_from_areas
from .estimate import EstimateInput, EstimateResult, cost_estimate
from .shihta import Component, ShihtaInput, ShihtaResult, shihta_calc
from .summary import build_summary, build_spec, parse_capacity
from .balance import BalanceInput, BalanceStage, BalanceResult, material_balance
from .firing import FiringInput, FiringZone, FiringResult, firing_calc
from .energy import EnergyInput, EnergyResult, energy_balance
from .lab import (
    plasticity_number, plasticity_group, recommended_target_plasticity,
    sensitivity_group, ClaySource,
    average_blend, recommend_leaning, LeaningResult, clay_yard, YardResult,
    quarry_output, QuarryResult,
    select_feeder, FeederResult, forming_guidance, LabInput, lab_report,
)

__all__ = [
    "ProductionInput", "ProductionResult", "production_program",
    "DryerInput", "DryerResult", "dryer_calc",
    "EquipmentInput", "EquipmentResult", "select_equipment",
    "ElectricalInput", "ElectricalResult", "electrical_load",
    "AreasInput", "AreasResult", "estimate_areas", "buildings_from_areas",
    "EstimateInput", "EstimateResult", "cost_estimate",
    "Component", "ShihtaInput", "ShihtaResult", "shihta_calc",
    "build_summary", "build_spec", "parse_capacity",
    "BalanceInput", "BalanceStage", "BalanceResult", "material_balance",
    "FiringInput", "FiringZone", "FiringResult", "firing_calc",
    "EnergyInput", "EnergyResult", "energy_balance",
    "plasticity_number", "plasticity_group", "recommended_target_plasticity",
    "sensitivity_group", "ClaySource",
    "average_blend", "recommend_leaning", "LeaningResult", "clay_yard", "YardResult",
    "quarry_output", "QuarryResult",
    "select_feeder", "FeederResult", "forming_guidance", "LabInput", "lab_report",
]
