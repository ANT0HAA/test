"""
Оценка электрических нагрузок и подбор трансформатора.

От годового потребления электроэнергии (из производственной программы) к
установленной мощности и КТП. Метод укрупнённый, по коэффициенту спроса.
"""
import math
from pydantic import BaseModel, Field

# Типовой ряд мощностей трансформаторов КТП, кВА
_KTP = [250, 400, 630, 1000, 1600, 2500]


class ElectricalInput(BaseModel):
    annual_kwh: float = Field(..., description="Годовое потребление электроэнергии, кВт·ч")
    operating_hours: float = Field(4000.0, description="Фонд рабочего времени, ч/год")
    demand_factor: float = Field(0.7, description="Коэффициент спроса (Кс)")
    power_factor: float = Field(0.85, description="cos φ")


class ElectricalResult(BaseModel):
    avg_power_kw: float          # средняя нагрузка
    installed_power_kw: float    # установленная мощность (оценка)
    apparent_kva: float          # полная мощность
    transformer_kva: int         # рекомендуемый КТП
    category: str
    notes: list[str] = []


def electrical_load(inp: ElectricalInput) -> ElectricalResult:
    oh = max(inp.operating_hours, 1.0)
    avg = inp.annual_kwh / oh
    installed = avg / max(inp.demand_factor, 0.1)        # P_уст ≈ P_ср / Кс
    apparent = installed / max(inp.power_factor, 0.1)    # S = P / cosφ
    transformer = next((k for k in _KTP if k >= apparent / 0.8), _KTP[-1])
    return ElectricalResult(
        avg_power_kw=round(avg, 1),
        installed_power_kw=round(installed, 1),
        apparent_kva=round(apparent, 1),
        transformer_kva=transformer,
        category="II категория электроснабжения (производственное здание)",
        notes=[f"Установленная мощность ≈ {installed:.0f} кВт (Кс={inp.demand_factor:g}); "
               f"КТП {transformer} кВА с резервом."],
    )
