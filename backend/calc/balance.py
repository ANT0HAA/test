"""
Материальный баланс производства кирпича по переделам (пластический способ).

Сквозной баланс масс: сырьё → формование → сушка → обжиг → готовая продукция,
с учётом формовочной влажности, остаточной влажности сырца, потерь при
прокаливании (ППП) и брака сушки/обжига. Коэффициенты — типовые (справочные),
помечены как уточняемые по документам заказчика.

Обозначения масс на 1 изделие:
  • скелет (абс. сухое тело) m_s = m_обож / (1 − ППП)
  • свежесформованный (W_ф)   m_ф = m_s / (1 − W_ф)
  • высушенный сырец (W_ост)  m_в = m_s / (1 − W_ост)
Число изделий на формовании: N_ф = N_годн / ((1−брак_суш)(1−брак_обж)).
"""
from pydantic import BaseModel, Field


class BalanceInput(BaseModel):
    pieces_per_year: float = Field(..., description="Годной продукции, шт/год")
    piece_mass_kg: float = Field(3.4, description="Масса ГОТОВОГО (обожжённого) изделия, кг")
    forming_moisture_pct: float = Field(20.0, description="Формовочная влажность, % (отн. влажной массы)")
    residual_moisture_pct: float = Field(5.0, description="Остаточная влажность сырца перед обжигом, %")
    loi_pct: float = Field(6.0, description="Потери при прокаливании (ППП), % сухой массы")
    drying_reject_pct: float = Field(3.0, description="Брак сушки, %")
    firing_reject_pct: float = Field(3.0, description="Брак обжига, %")
    operating_hours_per_year: float = Field(7920.0, description="Рабочих часов в году (330 сут × 24 ч)")


class BalanceStage(BaseModel):
    name: str
    pieces_per_year: float
    t_per_year: float
    t_per_hour: float


class BalanceResult(BaseModel):
    stages: list[BalanceStage]
    raw_dry_t_per_year: float          # сухое сырьё (глина+отощитель)
    forming_water_t_per_year: float    # вода на затворение
    water_removed_drying_t: float      # удалено влаги при сушке
    loi_removed_firing_t: float        # удалено при обжиге (ППП)
    reject_drying_t: float             # брак сушки (масса сырца)
    reject_firing_t: float             # брак обжига (масса сырца)
    notes: list[str] = []


def material_balance(inp: BalanceInput) -> BalanceResult:
    if inp.pieces_per_year <= 0 or inp.piece_mass_kg <= 0:
        raise ValueError("Объём выпуска и масса изделия должны быть > 0")
    loi = inp.loi_pct / 100.0
    wf = inp.forming_moisture_pct / 100.0
    wr = inp.residual_moisture_pct / 100.0
    bd = inp.drying_reject_pct / 100.0
    bf = inp.firing_reject_pct / 100.0
    for v, nm in [(loi, "ППП"), (wf, "формовочная влажность"), (wr, "остаточная влажность")]:
        if not 0 <= v < 1:
            raise ValueError(f"{nm} должна быть в диапазоне 0…100%")

    h = inp.operating_hours_per_year or 7920.0

    # Массы на 1 изделие, кг
    m_fired = inp.piece_mass_kg
    m_skeleton = m_fired / (1 - loi)            # абс. сухое тело
    m_formed = m_skeleton / (1 - wf)            # свежесформованный (с влагой затворения)
    m_dried = m_skeleton / (1 - wr)             # высушенный сырец (остаточная влага)

    # Число изделий по переделам, шт/год
    n_good = inp.pieces_per_year
    n_to_fire = n_good / (1 - bf)               # поступает на обжиг
    n_formed = n_to_fire / (1 - bd)             # формуется (с запасом на брак сушки)
    n_reject_dry = n_formed - n_to_fire
    n_reject_fire = n_to_fire - n_good

    def t_year(pieces: float, mass_kg: float) -> float:
        return pieces * mass_kg / 1000.0

    stages = [
        BalanceStage(name="Сырьё (сухое: глина+отощитель)", pieces_per_year=n_formed,
                     t_per_year=t_year(n_formed, m_skeleton), t_per_hour=t_year(n_formed, m_skeleton) / h),
        BalanceStage(name="Формование (брус, влажный)", pieces_per_year=n_formed,
                     t_per_year=t_year(n_formed, m_formed), t_per_hour=t_year(n_formed, m_formed) / h),
        BalanceStage(name="На сушку", pieces_per_year=n_formed,
                     t_per_year=t_year(n_formed, m_formed), t_per_hour=t_year(n_formed, m_formed) / h),
        BalanceStage(name="После сушки (на обжиг)", pieces_per_year=n_to_fire,
                     t_per_year=t_year(n_to_fire, m_dried), t_per_hour=t_year(n_to_fire, m_dried) / h),
        BalanceStage(name="Готовая продукция", pieces_per_year=n_good,
                     t_per_year=t_year(n_good, m_fired), t_per_hour=t_year(n_good, m_fired) / h),
    ]

    raw_dry = t_year(n_formed, m_skeleton)
    forming_water = t_year(n_formed, m_formed - m_skeleton)
    water_removed = t_year(n_formed, m_formed) - t_year(n_to_fire, m_dried) - t_year(n_reject_dry, m_formed)
    loi_removed = t_year(n_to_fire, m_dried - m_fired)   # упрощённо: масса сырца − масса годного на тех же шт
    # точнее ППП по поступившим на обжиг: (скелет − обожж.) на n_to_fire
    loi_removed = t_year(n_to_fire, m_skeleton - m_fired)

    notes = [
        f"Формовочная влажность {inp.forming_moisture_pct:g}%, остаточная {inp.residual_moisture_pct:g}%, "
        f"ППП {inp.loi_pct:g}%; брак сушки {inp.drying_reject_pct:g}%, обжига {inp.firing_reject_pct:g}%.",
        "Коэффициенты типовые — уточняются по лабораторным данным и режимам завода.",
        f"На 1 годное изделие формуется {n_formed / n_good:.3f} шт (запас на брак).",
    ]
    return BalanceResult(
        stages=stages,
        raw_dry_t_per_year=round(raw_dry, 1),
        forming_water_t_per_year=round(forming_water, 1),
        water_removed_drying_t=round(water_removed, 1),
        loi_removed_firing_t=round(loi_removed, 1),
        reject_drying_t=round(t_year(n_reject_dry, m_formed), 1),
        reject_firing_t=round(t_year(n_reject_fire, m_dried), 1),
        notes=notes,
    )
