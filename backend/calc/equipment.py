"""
Подбор основного технологического оборудования по производительности.

Типовые единицы и их производительность — из проектных документов/каталогов
заказчика. Количество подбирается под часовую производительность с запасом.
"""
import math
from pydantic import BaseModel, Field


class EquipmentInput(BaseModel):
    pieces_per_hour: float = Field(..., description="Часовая производительность, шт/ч")
    piece_mass_kg: float = 3.4
    reserve: float = Field(1.2, description="Коэффициент запаса производительности")


class EquipmentItem(BaseModel):
    role: str          # назначение (формование, обжиг, сушка, …)
    name: str          # тип/марка
    unit_capacity: str # производительность единицы
    qty: int


class EquipmentResult(BaseModel):
    raw_throughput_tph: float           # требуемая производительность по сырью, т/ч
    items: list[EquipmentItem]
    notes: list[str] = []


# Типовые прессы (марка, производительность, т/ч)
_PRESSES = [("СМК-133", 20.0), ("ПВШ-36", 36.0)]


def select_equipment(inp: EquipmentInput) -> EquipmentResult:
    product_tph = inp.pieces_per_hour * inp.piece_mass_kg / 1000.0
    raw_tph = product_tph * inp.reserve   # сырьё с запасом

    # Пресс: берём наибольший типовой, считаем количество
    press_name, press_cap = _PRESSES[-1]
    press_qty = max(1, math.ceil(raw_tph / press_cap))
    # Если хватает одного меньшего пресса — берём меньший
    if raw_tph <= _PRESSES[0][1]:
        press_name, press_cap = _PRESSES[0]
        press_qty = 1

    # Туннельная печь: длина грубо пропорциональна производительности (≈100 м на 20 т/ч)
    kiln_len = max(80, round(raw_tph / 20.0 * 100 / 10) * 10)
    # Сушилка: длина ~ 0.8 от печи
    dryer_len = max(48, round(kiln_len * 0.8 / 12) * 12)

    items = [
        EquipmentItem(role="Формование", name=f"Вакуумный шнековый пресс {press_name}",
                      unit_capacity=f"{press_cap:g} т/ч", qty=press_qty),
        EquipmentItem(role="Обжиг", name="Туннельная печь",
                      unit_capacity=f"L≈{kiln_len} м", qty=1),
        EquipmentItem(role="Сушка", name="Туннельная сушилка",
                      unit_capacity=f"L≈{dryer_len} м", qty=1),
    ]
    notes = [f"Требуемая производительность по сырью ≈ {raw_tph:.1f} т/ч "
             f"(продукция {product_tph:.1f} т/ч × запас {inp.reserve:g}).",
             "Марки прессов — из данных заказчика; уточняются по составу сырья."]
    return EquipmentResult(raw_throughput_tph=round(raw_tph, 1), items=items, notes=notes)
