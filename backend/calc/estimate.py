"""
Смета себестоимости (переменные затраты на сырьё/энергию).

Цены за единицу — из проектного документа заказчика «Расчёт себестоимости».
Проверка: себестоимость на 1000 шт по нормам и ценам документа = 2255.5 руб.
"""
from pydantic import BaseModel, Field

# Цены за единицу ресурса, руб (из документа заказчика)
UNIT_PRICES = {
    "clay_main_t": 150.0,
    "clay_kaolin_t": 600.0,
    "sand_t": 300.0,
    "water_m3": 15.0,
    "diesel_l": 26.0,
    "oil_l": 56.0,
    "electricity_kwh": 4.0,
    "gas_m3": 3.7,
    "packaging_pcs": 100.0,
}

_LABELS = {
    "clay_main_t": "Глина основная, т", "clay_kaolin_t": "Глина каолиновая, т",
    "sand_t": "Песок, т", "water_m3": "Вода, м³", "diesel_l": "Дизтопливо, л",
    "oil_l": "Масло, л", "electricity_kwh": "Электроэнергия, кВт·ч",
    "gas_m3": "Газ, м³", "packaging_pcs": "Упаковка, шт",
}


class EstimateInput(BaseModel):
    resources_per_year: dict[str, float] = Field(..., description="Потребность ресурсов в год")
    pieces_per_year: float = Field(..., description="Выпуск, шт/год")


class EstimateRow(BaseModel):
    item: str
    qty_per_year: float
    unit_price_rub: float
    cost_per_year_rub: float


class EstimateResult(BaseModel):
    rows: list[EstimateRow]
    total_per_year_rub: float
    cost_per_1000_rub: float
    notes: list[str] = []


def cost_estimate(inp: EstimateInput) -> EstimateResult:
    rows: list[EstimateRow] = []
    total = 0.0
    for key, qty in inp.resources_per_year.items():
        price = UNIT_PRICES.get(key)
        if price is None:
            continue
        cost = qty * price
        total += cost
        rows.append(EstimateRow(item=_LABELS.get(key, key), qty_per_year=round(qty, 1),
                                unit_price_rub=price, cost_per_year_rub=round(cost, 1)))
    per_1000 = total / (inp.pieces_per_year / 1000.0) if inp.pieces_per_year else 0.0
    return EstimateResult(
        rows=rows,
        total_per_year_rub=round(total, 1),
        cost_per_1000_rub=round(per_1000, 1),
        notes=["Цены за единицу — из документа заказчика «Расчёт себестоимости». "
               "Учтены переменные затраты (сырьё, энергия, упаковка); без ФОТ и амортизации."],
    )
