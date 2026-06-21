"""
Теплотехнический расчёт туннельного сушила.

Формулы и обозначения — из проектного документа заказчика «Расчёт сушил»
(аналитический метод) и «Варианты расчёта сушил»:
  • Количество сухого воздуха на испарение 1 кг влаги:  l = 1000 / (d2 − d1)
  • Расход тепла на нагрев воздуха:  q = l·(0.24 + 0.00047·d0)·(t1 − t0)
  • Тепловой баланс:  q_total = l·(I2 − I0) − τ + Σq − q_доп
  • Расход теплоносителя:  G = W·k   (k — кг т/носителя на 1 кг влаги при t)
  • Объём теплоносителя:  V = G / ρ

Тест проверяет совпадение с числовым примером документа (l≈32.26, q≈758).
"""
from pydantic import BaseModel, Field


class DryerInput(BaseModel):
    """Исходные данные расчёта сушила (значения по умолчанию — из примера документа)."""
    d1: float = Field(17.0, description="Влагосодержание поступающего воздуха, г/кг")
    d2: float = Field(48.0, description="Влагосодержание отработанного воздуха, г/кг")
    d0: float = Field(17.0, description="Влагосодержание холодного воздуха, г/кг")
    t0: float = Field(25.0, description="Температура холодного воздуха, °C")
    t1: float = Field(120.0, description="Температура нагретого воздуха, °C")
    I0: float = Field(16.0, description="Теплосодержание холодного воздуха, ккал/кг")
    I2: float = Field(38.0, description="Теплосодержание отработанного воздуха, ккал/кг")
    tau: float = Field(40.0, description="Температура влаги (материала), °C")
    sum_losses: float = Field(140.0, description="Сумма тепловых потерь Σq, ккал/кг")
    q_extra: float = Field(50.0, description="Дополнительно сообщённое тепло q_доп, ккал/кг")
    moisture_kg_per_h: float | None = Field(
        None, description="Удаляемая влага, кг/ч (для расхода теплоносителя)")
    carrier_kg_per_kg: float = Field(49.5, description="Расход т/носителя на 1 кг влаги")
    carrier_density: float = Field(0.922, description="Плотность т/носителя, кг/м³")


class DryerResult(BaseModel):
    air_per_kg_moisture: float       # l, кг сухого воздуха на 1 кг влаги
    heat_per_kg_moisture: float      # q (нагрев воздуха), ккал/кг
    heat_balance_per_kg: float       # q_total (баланс), ккал/кг
    carrier_kg_per_h: float | None = None
    carrier_m3_per_h: float | None = None
    notes: list[str] = []


def dryer_calc(inp: DryerInput) -> DryerResult:
    if inp.d2 <= inp.d1:
        raise ValueError("d2 должно быть больше d1")

    l = 1000.0 / (inp.d2 - inp.d1)
    q = l * (0.24 + 0.00047 * inp.d0) * (inp.t1 - inp.t0)
    q_balance = l * (inp.I2 - inp.I0) - inp.tau + inp.sum_losses - inp.q_extra

    carrier_kg = carrier_m3 = None
    notes: list[str] = ["Формулы — из проектного документа «Расчёт сушил»."]
    if inp.moisture_kg_per_h:
        carrier_kg = inp.moisture_kg_per_h * inp.carrier_kg_per_kg
        carrier_m3 = carrier_kg / inp.carrier_density
        notes.append(f"Расход теплоносителя при удалении {inp.moisture_kg_per_h:g} кг/ч влаги.")

    return DryerResult(
        air_per_kg_moisture=round(l, 2),
        heat_per_kg_moisture=round(q, 1),
        heat_balance_per_kg=round(q_balance, 1),
        carrier_kg_per_h=round(carrier_kg, 1) if carrier_kg is not None else None,
        carrier_m3_per_h=round(carrier_m3, 1) if carrier_m3 is not None else None,
        notes=notes,
    )
