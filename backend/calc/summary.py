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
from .areas import AreasInput, estimate_areas, buildings_from_areas
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


def build_spec(values: dict) -> dict:
    """
    Структурированная спецификация проекта (единый источник истины).

    Те же детерминированные расчёты, что и в build_summary, но в виде словаря —
    для отображения/редактирования в UI и сборки документов. Если объём выпуска
    не задан, возвращает {"has_data": False, "inputs": ...}.
    """
    capacity_text = values.get("capacity") or values.get("pieces_per_year") or ""
    prod_in = parse_capacity(str(capacity_text))
    if not prod_in:
        return {"has_data": False, "inputs": dict(values)}

    prod_in.piece_mass_kg = _piece_mass(values.get("product", ""))
    prog = production_program(prod_in)
    eq = select_equipment(EquipmentInput(pieces_per_hour=prog.pieces_per_hour,
                                         piece_mass_kg=prod_in.piece_mass_kg))
    el = electrical_load(ElectricalInput(
        annual_kwh=prog.resources_per_year["electricity_kwh"],
        operating_hours=prog.operating_hours_per_year))
    ar = estimate_areas(AreasInput(pieces_per_year=prog.pieces_per_year))
    est = cost_estimate(EstimateInput(resources_per_year=prog.resources_per_year,
                                      pieces_per_year=prog.pieces_per_year))
    from .balance import BalanceInput, material_balance
    bal = material_balance(BalanceInput(
        pieces_per_year=prog.pieces_per_year, piece_mass_kg=prod_in.piece_mass_kg,
        operating_hours_per_year=prog.operating_hours_per_year))
    from .firing import FiringInput, firing_calc
    fir = firing_calc(FiringInput(pieces_per_hour=prog.pieces_per_hour,
                                  piece_mass_kg=prod_in.piece_mass_kg))
    from .energy import EnergyInput, energy_balance
    _hours = prog.operating_hours_per_year or 7920.0
    water_kg_h = bal.water_removed_drying_t * 1000.0 / _hours
    en = energy_balance(EnergyInput(water_removed_kg_per_h=water_kg_h,
                                    kiln_heat_kcal_per_h=fir.heat_per_hour_kcal))
    from .plant import quality_grades, warehouses, staffing, ecology, CapexInput, capex_estimate
    grades = quality_grades(values.get("product", ""))
    annual_clay = prog.resources_per_year.get("clay_main_t", 0) + prog.resources_per_year.get("clay_kaolin_t", 0)
    wh = warehouses(annual_clay, prog.pieces_per_year, prod_in.piece_mass_kg)
    stf = staffing(shifts_per_day=int(getattr(prod_in, "shifts_per_day", 2) or 2))
    eco = ecology(prog.resources_per_year.get("gas_m3", 0))
    cap = capex_estimate(CapexInput(total_area_m2=ar.total_m2, pieces_per_year=prog.pieces_per_year,
                                    cost_per_1000_rub=est.cost_per_1000_rub))

    return {
        "has_data": True,
        "inputs": dict(values),
        "production": {
            "pieces_per_year": round(prog.pieces_per_year),
            "pieces_per_hour": round(prog.pieces_per_hour),
            "mass_per_year_t": round(prog.mass_per_year_t),
            "piece_mass_kg": prod_in.piece_mass_kg,
        },
        "resources": {k: round(v, 1) for k, v in prog.resources_per_year.items()},
        "equipment": {
            "throughput_tph": round(eq.raw_throughput_tph, 1),
            "items": [
                {"role": it.role, "name": it.name,
                 "unit_capacity": it.unit_capacity, "qty": it.qty}
                for it in eq.items
            ],
        },
        "electrical": {
            "installed_power_kw": round(el.installed_power_kw),
            "transformer_kva": el.transformer_kva,
            "category": el.category,
        },
        "areas": {
            "total_m2": round(ar.total_m2),
            "items": {k: round(v) for k, v in ar.areas_m2.items()},
        },
        "buildings": buildings_from_areas(prog.pieces_per_year),
        "cost": {
            "cost_per_1000_rub": round(est.cost_per_1000_rub, 1),
            "total_per_year_rub": round(est.total_per_year_rub),
        },
        "balance": {
            "stages": [
                {"name": s.name, "t_per_year": round(s.t_per_year),
                 "t_per_hour": round(s.t_per_hour, 1)}
                for s in bal.stages
            ],
            "raw_dry_t_per_year": bal.raw_dry_t_per_year,
            "forming_water_t_per_year": bal.forming_water_t_per_year,
            "water_removed_drying_t": bal.water_removed_drying_t,
            "loi_removed_firing_t": bal.loi_removed_firing_t,
            "reject_drying_t": bal.reject_drying_t,
            "reject_firing_t": bal.reject_firing_t,
        },
        "firing": {
            "max_temp_c": fir.max_temp_c,
            "residence_h": fir.residence_h,
            "gas_m3_per_hour": fir.gas_m3_per_hour,
            "gas_m3_per_1000": fir.gas_m3_per_1000,
            "zones": [{"name": z.name, "temp_range_c": z.temp_range_c,
                       "share_pct": z.share_pct, "time_h": z.time_h} for z in fir.zones],
        },
        "energy": {
            "dryer_demand_kcal_per_h": en.dryer_demand_kcal_per_h,
            "kiln_recoverable_kcal_per_h": en.kiln_recoverable_kcal_per_h,
            "coverage_pct": en.coverage_pct,
            "net_dryer_gas_m3_per_h": en.net_dryer_gas_m3_per_h,
        },
        "grades": grades,
        "warehouses": wh,
        "staffing": stf,
        "ecology": eco,
        "capex": cap,
    }
