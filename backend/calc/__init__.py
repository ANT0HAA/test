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

__all__ = [
    "ProductionInput", "ProductionResult", "production_program",
    "DryerInput", "DryerResult", "dryer_calc",
]
