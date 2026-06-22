"""
Режим обжига кирпича в туннельной печи и расход топлива.

Детерминированный расчёт: зоны печи (подогрев/обжиг/охлаждение), температуры и
время по зонам, удельный расход тепла на обжиг и расход топлива (природный газ).
Коэффициенты — типовые (справочные), помечены как уточняемые по режимной карте
и теплотехническому расчёту печи конкретного завода.
"""
from pydantic import BaseModel, Field

# Низшая теплота сгорания природного газа, ккал/м³ (≈ 8000 ккал/нм³ = 33.5 МДж/нм³)
_GAS_LHV_KCAL = 8000.0


class FiringInput(BaseModel):
    pieces_per_hour: float = Field(..., description="Поток на обжиг, шт/ч")
    piece_mass_kg: float = Field(3.4, description="Масса обожжённого изделия, кг")
    max_temp_c: float = Field(1000.0, description="Максимальная температура обжига, °C")
    residence_h: float = Field(30.0, description="Полное время в печи, ч")
    specific_heat_kcal_kg: float = Field(450.0, description="Уд. расход тепла на обжиг, ккал/кг изделия")
    fuel: str = "природный газ"


class FiringZone(BaseModel):
    name: str
    temp_range_c: str
    share_pct: float        # доля длины/времени зоны
    time_h: float


class FiringResult(BaseModel):
    zones: list[FiringZone]
    max_temp_c: float
    residence_h: float
    product_tph: float
    heat_per_hour_kcal: float
    gas_m3_per_hour: float
    gas_m3_per_1000: float
    notes: list[str] = []


# Типовая разбивка туннельной печи по зонам (доли времени/длины)
_ZONES = [
    ("Зона подогрева", "20–{tmax} °C", 0.40),
    ("Зона обжига (взвар)", "{tmax} °C", 0.25),
    ("Зона закалки/охлаждения", "{tmax}–40 °C", 0.35),
]


def firing_calc(inp: FiringInput) -> FiringResult:
    if inp.pieces_per_hour <= 0 or inp.piece_mass_kg <= 0:
        raise ValueError("Поток и масса изделия должны быть > 0")
    if inp.residence_h <= 0:
        raise ValueError("Время обжига должно быть > 0")

    product_tph = inp.pieces_per_hour * inp.piece_mass_kg / 1000.0
    # Тепло на обжиг в час: уд. расход × масса продукции
    heat_per_hour = inp.specific_heat_kcal_kg * inp.pieces_per_hour * inp.piece_mass_kg
    gas_per_hour = heat_per_hour / _GAS_LHV_KCAL
    gas_per_1000 = gas_per_hour / inp.pieces_per_hour * 1000.0

    tmax = f"{inp.max_temp_c:g}"
    zones = [
        FiringZone(name=nm, temp_range_c=rng.format(tmax=tmax), share_pct=round(sh * 100),
                   time_h=round(inp.residence_h * sh, 1))
        for nm, rng, sh in _ZONES
    ]

    notes = [
        f"Макс. температура {inp.max_temp_c:g} °C, полное время {inp.residence_h:g} ч.",
        f"Уд. расход тепла {inp.specific_heat_kcal_kg:g} ккал/кг; "
        f"теплота сгорания газа {_GAS_LHV_KCAL:g} ккал/м³.",
        "Кривая обжига, уд. расход тепла и зоны — типовые, уточняются по режимной "
        "карте и теплотехническому расчёту печи (зависят от сырья и изделия).",
    ]
    return FiringResult(
        zones=zones, max_temp_c=inp.max_temp_c, residence_h=inp.residence_h,
        product_tph=round(product_tph, 2),
        heat_per_hour_kcal=round(heat_per_hour),
        gas_m3_per_hour=round(gas_per_hour, 1),
        gas_m3_per_1000=round(gas_per_1000, 1),
        notes=notes,
    )
