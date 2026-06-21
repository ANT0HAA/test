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
from .areas import AreasInput, AreasResult, estimate_areas
from .estimate import EstimateInput, EstimateResult, cost_estimate
from .summary import build_summary, parse_capacity

__all__ = [
    "ProductionInput", "ProductionResult", "production_program",
    "DryerInput", "DryerResult", "dryer_calc",
    "EquipmentInput", "EquipmentResult", "select_equipment",
    "ElectricalInput", "ElectricalResult", "electrical_load",
    "AreasInput", "AreasResult", "estimate_areas",
    "EstimateInput", "EstimateResult", "cost_estimate",
    "build_summary", "parse_capacity",
]
