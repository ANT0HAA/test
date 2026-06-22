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
    # Для вагонеточного парка (типовые значения, уточняются по проекту)
    dryer_residence_h: float = Field(24.0, description="Время сушки, ч")
    kiln_residence_h: float = Field(30.0, description="Время обжига, ч")
    pieces_per_car: float = Field(2000.0, description="Вместимость вагонетки, шт")


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


# Типовые производительности машин массоподготовки, т/ч (плейсхолдер каталога)
_TPH_MACHINES = [
    ("Подготовка", "Камневыделительные вальцы", 25.0),
    ("Подготовка", "Вальцы грубого помола", 25.0),
    ("Подготовка", "Вальцы тонкого помола (1–2 мм)", 18.0),
    ("Подготовка", "Глиносмеситель с увлажнением", 30.0),
]
# Типовые производительности машин по штучному потоку, шт/ч
_PPH_MACHINES = [
    ("Резка", "Резательный автомат", 6000.0),
    ("Садка", "Автомат-садчик на сушильные вагонетки", 6000.0),
    ("Перестановка", "Автомат-перестановщик на печные вагонетки", 6000.0),
    ("Пакетирование", "Пакетоформирующий автомат", 6000.0),
]


def select_equipment(inp: EquipmentInput) -> EquipmentResult:
    product_tph = inp.pieces_per_hour * inp.piece_mass_kg / 1000.0
    raw_tph = product_tph * inp.reserve   # сырьё с запасом
    pph = inp.pieces_per_hour * inp.reserve

    items: list[EquipmentItem] = []

    # Массоподготовка (по т/ч сырья)
    for role, name, cap in _TPH_MACHINES:
        items.append(EquipmentItem(role=role, name=name, unit_capacity=f"{cap:g} т/ч",
                                   qty=max(1, math.ceil(raw_tph / cap))))

    # Пресс: наибольший типовой; меньший — если хватает
    press_name, press_cap = _PRESSES[-1]
    press_qty = max(1, math.ceil(raw_tph / press_cap))
    if raw_tph <= _PRESSES[0][1]:
        press_name, press_cap = _PRESSES[0]
        press_qty = 1
    items.append(EquipmentItem(role="Формование", name=f"Вакуумный шнековый пресс {press_name}",
                               unit_capacity=f"{press_cap:g} т/ч", qty=press_qty))

    # Резка — сразу после пресса (по штучному потоку)
    items.append(EquipmentItem(role="Резка", name="Резательный автомат",
                               unit_capacity="6000 шт/ч",
                               qty=max(1, math.ceil(pph / 6000.0))))
    items.append(EquipmentItem(role="Садка", name="Автомат-садчик на сушильные вагонетки",
                               unit_capacity="6000 шт/ч",
                               qty=max(1, math.ceil(pph / 6000.0))))

    # Сушило и печь (длины ~ производительности)
    kiln_len = max(80, round(raw_tph / 20.0 * 100 / 10) * 10)
    dryer_len = max(48, round(kiln_len * 0.8 / 12) * 12)
    items.append(EquipmentItem(role="Сушка", name="Туннельная сушилка",
                               unit_capacity=f"L≈{dryer_len} м", qty=1))
    items.append(EquipmentItem(role="Перестановка",
                               name="Автомат-перестановщик на печные вагонетки",
                               unit_capacity="6000 шт/ч",
                               qty=max(1, math.ceil(pph / 6000.0))))
    items.append(EquipmentItem(role="Обжиг", name="Туннельная печь",
                               unit_capacity=f"L≈{kiln_len} м", qty=1))
    items.append(EquipmentItem(role="Пакетирование", name="Пакетоформирующий автомат",
                               unit_capacity="6000 шт/ч",
                               qty=max(1, math.ceil(pph / 6000.0))))

    # Вагонеточный парк: N = время_в_аппарате × поток / вместимость, +10% резерв
    cap_car = inp.pieces_per_car or 2000.0
    dryer_cars = math.ceil(inp.dryer_residence_h * inp.pieces_per_hour / cap_car * 1.1)
    kiln_cars = math.ceil(inp.kiln_residence_h * inp.pieces_per_hour / cap_car * 1.1)
    items.append(EquipmentItem(role="Транспорт", name="Вагонетки сушильные",
                               unit_capacity=f"{cap_car:g} шт", qty=dryer_cars))
    items.append(EquipmentItem(role="Транспорт", name="Вагонетки печные",
                               unit_capacity=f"{cap_car:g} шт", qty=kiln_cars))

    notes = [f"Требуемая производительность по сырью ≈ {raw_tph:.1f} т/ч "
             f"(продукция {product_tph:.1f} т/ч × запас {inp.reserve:g}); поток {pph:.0f} шт/ч.",
             f"Вагонетки: сушильные {dryer_cars} (время сушки {inp.dryer_residence_h:g} ч), "
             f"печные {kiln_cars} (обжиг {inp.kiln_residence_h:g} ч), вместимость {cap_car:g} шт.",
             "Производительности машин и вместимость вагонеток — типовые, уточняются "
             "по каталогам и режимам завода."]
    return EquipmentResult(raw_throughput_tph=round(raw_tph, 1), items=items, notes=notes)
