"""
Производственная программа и потребность в ресурсах.

Нормы расхода на 1000 шт кирпича взяты из проектного документа заказчика
(«Расчёт себестоимости», лист «Расчёт рентабельности»). Все величины масштабируются
от заданного объёма выпуска — никаких «придуманных» цифр.
"""
from pydantic import BaseModel, Field

# Нормы расхода на 1000 шт условного кирпича (из документа заказчика)
NORMS_PER_1000 = {
    "clay_main_t": 1.12,      # глина основная, т
    "clay_kaolin_t": 0.54,    # глина каолиновая, т
    "sand_t": 0.54,           # песок (гранитный отсев), т
    "water_m3": 0.10,         # вода промышленная, м³
    "diesel_l": 2.4,          # дизельное топливо, л
    "oil_l": 0.10,            # масло, л
    "electricity_kwh": 180.0, # электроэнергия, кВт·ч
    "gas_m3": 160.0,          # газ природный, м³
    "packaging_pcs": 2.2,     # упаковочные материалы, шт
}


class ProductionInput(BaseModel):
    """Исходные данные производственной программы."""
    pieces_per_shift: float | None = Field(None, description="Выпуск, шт/смену")
    pieces_per_year: float | None = Field(None, description="Выпуск, шт/год (если задан напрямую)")
    shifts_per_day: int = 2
    hours_per_shift: float = 8.0
    work_days_per_year: int = 250
    piece_mass_kg: float = 3.4  # масса 1 шт условного кирпича (1НФ ~3.3–3.5 кг)


class ProductionResult(BaseModel):
    pieces_per_year: float
    pieces_per_hour: float
    mass_per_year_t: float                 # масса готовой продукции, т/год
    resources_per_year: dict[str, float]   # потребность ресурсов в год
    resources_per_hour: dict[str, float]   # потребность ресурсов в час
    notes: list[str] = []


def production_program(inp: ProductionInput) -> ProductionResult:
    notes: list[str] = []

    operating_hours = inp.shifts_per_day * inp.hours_per_shift * inp.work_days_per_year
    if operating_hours <= 0:
        operating_hours = 1.0

    if inp.pieces_per_year:
        per_year = float(inp.pieces_per_year)
    elif inp.pieces_per_shift:
        per_year = inp.pieces_per_shift * inp.shifts_per_day * inp.work_days_per_year
    else:
        raise ValueError("Задайте pieces_per_shift или pieces_per_year")

    per_hour = per_year / operating_hours
    thousands = per_year / 1000.0

    res_year = {k: round(v * thousands, 2) for k, v in NORMS_PER_1000.items()}
    res_hour = {k: round(v / operating_hours, 4) for k, v in res_year.items()}

    notes.append(f"Фонд рабочего времени: {operating_hours:.0f} ч/год "
                 f"({inp.shifts_per_day} см × {inp.hours_per_shift:g} ч × {inp.work_days_per_year} сут)")
    notes.append("Нормы расхода на 1000 шт — из проектного документа заказчика.")

    return ProductionResult(
        pieces_per_year=round(per_year, 1),
        pieces_per_hour=round(per_hour, 1),
        mass_per_year_t=round(per_year * inp.piece_mass_kg / 1000.0, 1),
        resources_per_year=res_year,
        resources_per_hour=res_hour,
        notes=notes,
    )
