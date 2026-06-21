"""
Сводка расчётов по исходным данным проекта.

Парсит введённый пользователем объём выпуска и собирает детерминированную сводку
(производственная программа, потребность ресурсов, подбор оборудования) для
подмеса в контекст агентов — чтобы они опирались на точные цифры.
"""
import re

from .production import ProductionInput, production_program
from .equipment import EquipmentInput, select_equipment
from .electrical import ElectricalInput, electrical_load
from .areas import AreasInput, estimate_areas
from .estimate import EstimateInput, cost_estimate

# Ориентировочная масса 1 шт по виду продукции, кг
_PIECE_MASS = {
    "поризован": 2.6, "облицов": 2.6, "клинкер": 3.6, "рядов": 3.4,
}


def parse_capacity(text: str) -> ProductionInput | None:
    """Из свободного текста объёма («30000 шт/смену», «60 млн шт/год») → ProductionInput."""
    if not text:
        return None
    low = text.lower().replace("\xa0", " ")
    num = re.search(r"(\d[\d\s.,]*)", low)
    if not num:
        return None
    val = float(num.group(1).replace(" ", "").replace(",", "."))
    if "млн" in low:
        val *= 1_000_000
    if "смен" in low:
        return ProductionInput(pieces_per_shift=val)
    # «в год» / «/год» / по умолчанию — годовой объём
    return ProductionInput(pieces_per_year=val)


def _piece_mass(product: str) -> float:
    p = (product or "").lower()
    for key, mass in _PIECE_MASS.items():
        if key in p:
            return mass
    return 3.4


def build_summary(values: dict) -> str:
    """Текстовая сводка расчётов по исходным данным (для контекста агентов)."""
    capacity_text = values.get("capacity") or values.get("pieces_per_year") or ""
    prod_in = parse_capacity(str(capacity_text))
    if not prod_in:
        return ""

    prod_in.piece_mass_kg = _piece_mass(values.get("product", ""))
    prog = production_program(prod_in)

    lines = [
        "Производственная программа:",
        f"  • выпуск: {prog.pieces_per_year:,.0f} шт/год, {prog.pieces_per_hour:,.0f} шт/ч",
        f"  • масса продукции: {prog.mass_per_year_t:,.0f} т/год",
        "Потребность ресурсов (год):",
        f"  • глина основная {prog.resources_per_year['clay_main_t']:,.0f} т, "
        f"каолиновая {prog.resources_per_year['clay_kaolin_t']:,.0f} т, "
        f"песок {prog.resources_per_year['sand_t']:,.0f} т",
        f"  • газ {prog.resources_per_year['gas_m3']:,.0f} м³, "
        f"электроэнергия {prog.resources_per_year['electricity_kwh']:,.0f} кВт·ч, "
        f"вода {prog.resources_per_year['water_m3']:,.0f} м³",
    ]

    eq = select_equipment(EquipmentInput(pieces_per_hour=prog.pieces_per_hour,
                                         piece_mass_kg=prod_in.piece_mass_kg))
    lines.append(f"Оборудование (≈{eq.raw_throughput_tph:.1f} т/ч по сырью):")
    for it in eq.items:
        lines.append(f"  • {it.role}: {it.name} — {it.unit_capacity} × {it.qty}")

    el = electrical_load(ElectricalInput(
        annual_kwh=prog.resources_per_year["electricity_kwh"],
        operating_hours=prog.operating_hours_per_year))
    lines.append(f"Электроснабжение: установл. мощность ≈ {el.installed_power_kw:.0f} кВт, "
                 f"КТП {el.transformer_kva} кВА, {el.category}.")

    ar = estimate_areas(AreasInput(pieces_per_year=prog.pieces_per_year))
    lines.append(f"Площади корпусов (всего ≈ {ar.total_m2:.0f} м²): "
                 + ", ".join(f"{k} {v:.0f} м²" for k, v in ar.areas_m2.items()))

    est = cost_estimate(EstimateInput(resources_per_year=prog.resources_per_year,
                                      pieces_per_year=prog.pieces_per_year))
    lines.append(f"Себестоимость (переменные): {est.cost_per_1000_rub:.0f} руб/1000 шт, "
                 f"{est.total_per_year_rub:,.0f} руб/год.")

    return "\n".join(lines).replace(",", " ")  # пробел как разделитель тысяч
