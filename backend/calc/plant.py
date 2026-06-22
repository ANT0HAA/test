"""
Завод в целом: марки/качество (ГОСТ 530), склады, штат, экономика, экология.

Детерминированные ориентировочные расчёты по типовым нормам и справочным
коэффициентам. ВСЕ цифры (цены, нормы обслуживания, удельные показатели) —
типовые, помечены как уточняемые по проекту/КП поставщиков/нормам предприятия.
"""
from pydantic import BaseModel, Field


# ─── Марки и контроль качества (ГОСТ 530-2012) ─────────────────────────

_GRADES = {
    "клинкер":   {"strength": "М300–М500", "frost": "F75–F100", "water": "≤ 6%"},
    "облицов":   {"strength": "М150–М250", "frost": "F50–F100", "water": "6–14% (лицевой)"},
    "лицев":     {"strength": "М150–М250", "frost": "F50–F100", "water": "6–14% (лицевой)"},
    "поризов":   {"strength": "М100–М150", "frost": "F25–F50",  "water": "≤ 16%"},
    "рядов":     {"strength": "М100–М150", "frost": "F25–F50",  "water": "8–16%"},
}
_GRADES_DEFAULT = {"strength": "М125–М150", "frost": "F35–F50", "water": "8–14%"}


def quality_grades(product: str) -> dict:
    """Ориентировочные марки и контролируемые показатели по ГОСТ 530-2012."""
    p = (product or "").lower()
    g = next((v for k, v in _GRADES.items() if k in p), _GRADES_DEFAULT)
    return {
        **g,
        "control": [
            "Предел прочности при сжатии и изгибе (марка М).",
            "Морозостойкость (число циклов F).",
            "Водопоглощение, %.",
            "Отклонения размеров и формы; отсутствие известковых «дутиков».",
        ],
        "standard": "ГОСТ 530-2012 «Кирпич и камень керамические»",
    }


# ─── Склады сырья и готовой продукции ──────────────────────────────────

def warehouses(annual_clay_t: float, pieces_per_year: float, piece_mass_kg: float = 3.4,
               raw_store_days: int = 10, fg_store_days: int = 12,
               pieces_per_pallet: int = 480) -> dict:
    """Складские запасы: сырьё (т) и готовая продукция (шт/поддоны/площадь)."""
    daily_clay = annual_clay_t / 330.0 if annual_clay_t else 0.0
    raw_store_t = daily_clay * raw_store_days
    daily_pieces = pieces_per_year / 330.0 if pieces_per_year else 0.0
    fg_pieces = daily_pieces * fg_store_days
    pallets = fg_pieces / pieces_per_pallet if pieces_per_pallet else 0.0
    # поддон ~1 м²; складирование в 2 яруса, проходы ×2 → площадь ≈ pallets/2*2
    fg_area = pallets  # м² (ориентировочно: 1 поддон ≈ 1 м² с учётом ярусов и проходов)
    return {
        "raw_store_days": raw_store_days, "raw_store_t": round(raw_store_t),
        "fg_store_days": fg_store_days, "fg_pieces": round(fg_pieces),
        "fg_pallets": round(pallets), "fg_area_m2": round(fg_area),
        "notes": ["Нормы запаса (сут) и вместимость поддона — типовые, уточняются по логистике."],
    }


# ─── Штат (ориентировочно) ─────────────────────────────────────────────

# Рабочих в смену по переделам (типовая норма обслуживания линии)
_CREW_PER_SHIFT = {
    "Массоподготовка": 2, "Формование и резка": 2, "Садка/автоматы": 2,
    "Сушка и обжиг": 2, "Сортировка и пакетирование": 3, "Лаборатория/ОТК": 1,
    "Ремонт и обслуживание": 2,
}


def staffing(shifts_per_day: int = 2, admin_share: float = 0.2) -> dict:
    """Ориентировочный штат: рабочие по переделам × смены + ИТР/АУП."""
    per_shift = sum(_CREW_PER_SHIFT.values())
    workers = per_shift * max(1, shifts_per_day)
    admin = round(workers * admin_share)
    return {
        "per_shift": per_shift, "shifts_per_day": shifts_per_day,
        "workers_total": workers, "admin": admin, "headcount": workers + admin,
        "by_area": _CREW_PER_SHIFT,
        "notes": ["Нормы обслуживания и доля ИТР/АУП — ориентировочные, уточняются "
                  "штатным расписанием."],
    }


# ─── Экология (укрупнённо) ─────────────────────────────────────────────

# Удельный выброс CO2 при сжигании природного газа, кг/м³ (≈1.9)
_CO2_PER_M3_GAS = 1.9


def ecology(gas_m3_per_year: float) -> dict:
    """Укрупнённая экологическая оценка: выбросы CO2 от сжигания газа, аспирация."""
    co2_t = gas_m3_per_year * _CO2_PER_M3_GAS / 1000.0 if gas_m3_per_year else 0.0
    return {
        "co2_t_per_year": round(co2_t),
        "measures": [
            "Аспирация и пылеочистка на массоподготовке, резке, сортировке.",
            "Дымоочистка/рассеивание продуктов сгорания печи.",
            "Оборотное водоснабжение; сбор и возврат брака сырца в производство.",
        ],
        "notes": [f"CO2 оценён по {_CO2_PER_M3_GAS:g} кг/м³ газа; требуется проект ПДВ/ОВОС."],
    }


# ─── Капзатраты (ориентировочно) ───────────────────────────────────────

class CapexInput(BaseModel):
    total_area_m2: float = Field(..., description="Суммарная площадь корпусов, м²")
    pieces_per_year: float = 0.0
    cost_per_1000_rub: float = 0.0          # переменная себестоимость 1000 шт
    sell_price_per_1000_rub: float = 0.0    # цена продажи 1000 шт (если задана — срок окупаемости)
    building_cost_rub_m2: float = 30000.0   # типовая стоимость строительства, руб/м²
    equipment_cost_rub: float = 0.0         # стоимость оборудования по КП (если известна)


def capex_estimate(inp: CapexInput) -> dict:
    """Ориентировочные капзатраты и (при заданной цене) простой срок окупаемости."""
    buildings = inp.total_area_m2 * inp.building_cost_rub_m2
    equipment = inp.equipment_cost_rub  # 0, если не заданы КП
    engineering = (buildings + equipment) * 0.15   # инженерные сети/монтаж ≈ 15%
    total = buildings + equipment + engineering
    payback = None
    if inp.sell_price_per_1000_rub > inp.cost_per_1000_rub > 0 and inp.pieces_per_year > 0:
        margin_per_1000 = inp.sell_price_per_1000_rub - inp.cost_per_1000_rub
        annual_profit = margin_per_1000 * inp.pieces_per_year / 1000.0
        if annual_profit > 0:
            payback = round(total / annual_profit, 1)
    notes = ["Стоимость строительства руб/м² и доля инженерии — ориентировочные.",
             "Оборудование — по КП поставщиков (если не задано, в сумму не включено)."]
    if payback is None:
        notes.append("Срок окупаемости считается при заданной цене продажи (sell_price_per_1000_rub).")
    return {
        "buildings_rub": round(buildings), "equipment_rub": round(equipment),
        "engineering_rub": round(engineering), "total_rub": round(total),
        "payback_years": payback, "notes": notes,
    }
