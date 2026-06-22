"""
Лабораторно-технологические расчёты по сырью (ядро модуля «Лаборатория»).

Детерминированные методики керамической технологии (НЕ выдумки модели):
  • число пластичности и группа сырья (ГОСТ 21216);
  • чувствительность к сушке и решение «отощитель ↔ удлинение сушилки»;
  • усреднение шихты из нескольких глин при ограничении числа питателей;
  • дозировка отощителя (песка) под целевую пластичность;
  • усреднительный штабель глины (число слоёв, высота);
  • подбор питателя под производительность и число компонентов;
  • особенности способа формования (пластическое/полусухое/сухое).

Численные пороги — типовые (ГОСТ/справочники). Каталоги (питатели) и точные
коэффициенты уточняются по данным заказчика — это помечено в notes.
"""
from pydantic import BaseModel, Field


# ─── Пластичность ──────────────────────────────────────────────────────

def plasticity_group(ip: float) -> str:
    """Группа сырья по числу пластичности Ip = WL − WP (ГОСТ 21216)."""
    if ip < 7:
        return "малопластичное"
    if ip < 15:
        return "умереннопластичное"
    if ip < 25:
        return "среднепластичное"
    return "высокопластичное"


def plasticity_number(wl: float, wp: float) -> float:
    """Число пластичности Ip = граница текучести WL − граница раскатывания WP, %."""
    return round(wl - wp, 1)


# Целевое число пластичности массы по способу формования (типовые окна
# формуемости; уточняются по данным заказчика). Система считает цель сама.
_TARGET_IP_BY_FORMING = {
    "пластическое": 12.0,   # оптимум ~10–14 для шнекового пресса
    "полусухое": 7.0,       # пластичность менее критична
    "сухое": 5.0,
}


def recommended_target_plasticity(forming: str) -> float:
    """Целевое число пластичности массы под способ формования (рассчитывается системой)."""
    key = (forming or "").strip().lower()
    for k, v in _TARGET_IP_BY_FORMING.items():
        if k in key:
            return v
    return _TARGET_IP_BY_FORMING["пластическое"]


# ─── Чувствительность к сушке ──────────────────────────────────────────

def sensitivity_group(coeff: float) -> str:
    """
    Группа по коэффициенту чувствительности к сушке (по З.А. Носовой/Чижскому):
      < 1 — малочувствительное, 1…2 — среднечувствительное, > 2 — высокочувствительное.
    """
    if coeff < 1.0:
        return "малочувствительное"
    if coeff <= 2.0:
        return "среднечувствительное"
    return "высокочувствительное"


# ─── Компоненты шихты ──────────────────────────────────────────────────

class ClaySource(BaseModel):
    name: str
    plasticity: float = Field(..., description="Число пластичности компонента, %")
    fraction: float = Field(0.0, description="Доля в шихте, % (если задана)")
    oxides: dict[str, float] = Field(default_factory=dict)


class LeaningResult(BaseModel):
    blended_plasticity: float          # пластичность усреднённой глиняной смеси
    blended_group: str
    target_plasticity: float
    need_leaning: bool                 # нужен ли отощитель
    sand_fraction_pct: float           # рекомендуемая доля песка, % (0 если не нужен)
    options: list[str]                 # варианты решения (отощитель / сушилка)
    notes: list[str] = []


def average_blend(clays: list[ClaySource]) -> tuple[float, dict[str, float]]:
    """
    Усреднение нескольких глин (рядовая продукция). Если доли не заданы — поровну.
    Возвращает (средневзвешенная пластичность, средневзвешенный оксидный состав).
    """
    if not clays:
        raise ValueError("Нужна хотя бы одна глина")
    total = sum(c.fraction for c in clays)
    if total <= 0:
        weights = [1.0 / len(clays)] * len(clays)   # поровну
    else:
        weights = [c.fraction / total for c in clays]
    ip = sum(c.plasticity * w for c, w in zip(clays, weights))
    oxides: dict[str, float] = {}
    for c, w in zip(clays, weights):
        for ox, val in c.oxides.items():
            oxides[ox] = oxides.get(ox, 0.0) + val * w
    return round(ip, 1), {k: round(v, 2) for k, v in oxides.items()}


def recommend_leaning(clays: list[ClaySource], target_plasticity: float = 12.0,
                      sand_plasticity: float = 0.0) -> LeaningResult:
    """
    По усреднённой пластичности решает, нужен ли отощитель (песок), и оценивает его
    долю под целевую пластичность. Альтернатива отощению — удлинение сушилки.

    Дозировка песка (линейное смешение пластичности):
        Ip_смеси = Ip_глины·(1−x) + Ip_песка·x  →  x = (Ip_глины − Ip_цель)/(Ip_глины − Ip_песка)
    где x — массовая доля песка.
    """
    blended_ip, _ = average_blend(clays)
    group = plasticity_group(blended_ip)
    notes = ["Пороги пластичности — ГОСТ 21216; цель Ip≈10–14 для пластического "
             "формования. Уточняется по данным лаборатории заказчика."]

    if blended_ip <= target_plasticity or blended_ip <= sand_plasticity:
        return LeaningResult(
            blended_plasticity=blended_ip, blended_group=group,
            target_plasticity=target_plasticity, need_leaning=False,
            sand_fraction_pct=0.0,
            options=["Отощитель не требуется — пластичность в норме."],
            notes=notes)

    x = (blended_ip - target_plasticity) / (blended_ip - sand_plasticity)
    sand_pct = round(max(0.0, min(0.4, x)) * 100, 1)   # ограничиваем разумным пределом 40%
    options = [
        f"Добавить отощитель (песок) ≈ {sand_pct}% — снизит пластичность до целевой "
        f"и уменьшит чувствительность к сушке.",
        "Либо удлинить сушилку (мягче режим) без отощителя — выше капзатраты и площадь, "
        "но сохраняется прочность сырца.",
    ]
    if group == "высокопластичное":
        notes.append("Высокопластичное сырьё — отощение обычно предпочтительнее "
                     "(иначе риск трещин при сушке).")
    return LeaningResult(
        blended_plasticity=blended_ip, blended_group=group,
        target_plasticity=target_plasticity, need_leaning=True,
        sand_fraction_pct=sand_pct, options=options, notes=notes)


# ─── Усреднительный штабель глины на площадке ──────────────────────────

class YardResult(BaseModel):
    annual_clay_t: float
    stockpile_t: float        # объём усреднительного штабеля (нормативный запас)
    layers: int               # число слоёв послойной укладки
    height_m: float           # высота штабеля
    area_m2: float            # площадь основания
    notes: list[str] = []


def clay_yard(annual_clay_t: float, store_days: int = 30, bulk_density_t_m3: float = 1.6,
              layer_thickness_m: float = 0.3, height_m: float = 4.0) -> YardResult:
    """
    Усреднительный штабель глины: послойная укладка для усреднения нескольких глин.
    Запас — на store_days суток выпуска. Число слоёв = высота / толщина слоя.
    """
    if annual_clay_t <= 0:
        raise ValueError("Годовой расход глины должен быть > 0")
    daily = annual_clay_t / 330.0                 # рабочих суток в году ≈ 330
    stockpile = daily * store_days
    volume = stockpile / bulk_density_t_m3
    area = volume / height_m
    layers = max(1, round(height_m / layer_thickness_m))
    notes = [f"Запас на {store_days} сут; послойная укладка ({layers} слоёв по "
             f"{layer_thickness_m:g} м) обеспечивает усреднение глин на одном штабеле.",
             "Плотность/высота штабеля — типовые, уточняются по площадке."]
    return YardResult(
        annual_clay_t=round(annual_clay_t, 1), stockpile_t=round(stockpile, 1),
        layers=layers, height_m=height_m, area_m2=round(area, 1), notes=notes)


# ─── Выработка карьера ─────────────────────────────────────────────────

class QuarryResult(BaseModel):
    usable_clay_t: float        # нужно заводу (полезного), т/год
    mined_clay_t: float         # добыть с учётом потерь, т/год
    mined_volume_m3: float      # объём полезного ископаемого, м³/год
    overburden_m3: float        # объём вскрыши, м³/год
    life_years: float | None    # срок отработки (если заданы запасы)
    notes: list[str] = []


def quarry_output(annual_clay_t: float, losses_pct: float = 5.0,
                  overburden_ratio: float = 0.3, density_t_m3: float = 1.7,
                  reserves_t: float = 0.0) -> QuarryResult:
    """
    Годовая выработка карьера по потребности завода в глине.
    Добыча с учётом потерь: Mдоб = Mполезн / (1 − потери). Объём вскрыши — по
    коэффициенту вскрыши. Срок отработки = запасы / годовая добыча (если запасы заданы).
    Коэффициенты — типовые, уточняются по геологическому отчёту/проекту карьера.
    """
    if annual_clay_t <= 0:
        raise ValueError("Годовой расход глины должен быть > 0")
    losses = max(0.0, min(0.3, losses_pct / 100.0))
    mined_t = annual_clay_t / (1.0 - losses)
    mined_m3 = mined_t / density_t_m3
    overburden_m3 = mined_m3 * overburden_ratio
    life = round(reserves_t / mined_t, 1) if reserves_t and reserves_t > 0 else None
    notes = [f"Добыча с учётом потерь {losses_pct:g}% = {mined_t:,.0f} т/год.".replace(",", " "),
             f"Вскрыша по коэффициенту {overburden_ratio:g} = {overburden_m3:,.0f} м³/год."
             .replace(",", " "),
             "Потери/вскрыша/плотность — типовые, уточняются по проекту карьера."]
    if life:
        notes.append(f"Срок отработки при запасах {reserves_t:,.0f} т ≈ {life} лет."
                     .replace(",", " "))
    return QuarryResult(
        usable_clay_t=round(annual_clay_t, 1), mined_clay_t=round(mined_t, 1),
        mined_volume_m3=round(mined_m3, 1), overburden_m3=round(overburden_m3, 1),
        life_years=life, notes=notes)


# ─── Питатели (дозирование компонентов) ────────────────────────────────

# Типовые ящичные питатели (марка, производительность т/ч) — ПЛЕЙСХОЛДЕР,
# уточняется по каталогу заказчика.
_FEEDERS = [("СМК-78 (ящичный)", 25.0), ("ДПР-2 (ящичный)", 45.0)]


class FeederResult(BaseModel):
    raw_tph: float
    components: int               # сколько компонентов нужно дозировать
    feeders_used: int             # сколько питателей ставим
    model: str
    unit_capacity_tph: float
    notes: list[str] = []


def select_feeder(raw_tph: float, components: int, max_feeders: int = 3,
                  averaging: bool = True) -> FeederResult:
    """
    Подбор ящичных питателей: по одному на дозируемый компонент, но не больше
    max_feeders. При усреднении рядовой продукции глины подают через общий тракт,
    поэтому число питателей ограничивают (типично ≤3: глины усреднённо + добавка).
    """
    # При усреднении несколько глин идут как один усреднённый поток
    feeders = components if not averaging else min(components, max_feeders)
    feeders = min(feeders, max_feeders)
    model, cap = _FEEDERS[-1] if raw_tph > _FEEDERS[0][1] else _FEEDERS[0]
    notes = [f"Питателей: {feeders} (компонентов {components}, лимит {max_feeders}).",
             "Марки питателей — типовые, уточняются по каталогу заказчика."]
    if averaging and components > max_feeders:
        notes.append("Глины усредняются на штабеле и подаются общим трактом — "
                     "отдельный питатель на каждую глину не требуется.")
    return FeederResult(
        raw_tph=round(raw_tph, 1), components=components, feeders_used=feeders,
        model=model, unit_capacity_tph=cap, notes=notes)


# ─── Способ формования ─────────────────────────────────────────────────

_FORMING = {
    "пластическое": {
        "moisture": "18–25%",
        "press": "вакуумный шнековый пресс",
        "additive_stage": "отощитель и добавки вводят в массоподготовке до пресса; "
                          "выгорающие/упрочняющие добавки — на последнем этапе смешения",
        "notes": "Требует сушки сырца (чувствительность к сушке критична); "
                 "отощитель снижает усадку и трещинообразование.",
    },
    "полусухое": {
        "moisture": "8–12%",
        "press": "пресс полусухого прессования (гидравлический/механический)",
        "additive_stage": "добавки вводят в пресс-порошок при подготовке шихты",
        "notes": "Сушка сырца почти не нужна — чувствительность к сушке менее важна; "
                 "ключевое — гранулометрия и влажность пресс-порошка.",
    },
    "сухое": {
        "moisture": "2–6%",
        "press": "пресс сухого прессования",
        "additive_stage": "добавки и связующее — в пресс-порошок",
        "notes": "Применяют для плотной продукции; требует тонкого помола и связующих.",
    },
}


def forming_guidance(method: str = "пластическое") -> dict:
    """Особенности способа формования: влажность, пресс, на каком этапе добавки."""
    key = (method or "").strip().lower()
    for k, v in _FORMING.items():
        if k in key:
            return {"method": k, **v}
    return {"method": "пластическое", **_FORMING["пластическое"]}


# ─── Сводный лабораторный расчёт ───────────────────────────────────────

class LabInput(BaseModel):
    clays: list[ClaySource]
    forming: str = "пластическое"
    target_plasticity: float | None = None   # None → система считает по способу формования
    sand_plasticity: float = 0.0
    sensitivity_coeff: float | None = None    # коэффициент чувствительности к сушке (из лаборатории)
    annual_clay_t: float = 0.0                # годовой расход глины (из производственной программы)
    reserves_t: float = 0.0                   # запасы сырья (из геологического отчёта), т
    raw_tph: float = 0.0                      # производительность по сырью, т/ч
    max_feeders: int = 3


def lab_report(inp: LabInput) -> dict:
    """
    Сводный лабораторный расчёт по сырью: усреднённая шихта, отощитель/решение по
    сушке, чувствительность, штабель усреднения, питатели, схема по способу формования.
    Контрольные точки — что лаборатория должна замерить для уточнения расчёта.
    """
    if not inp.clays:
        return {"has_data": False, "notes": ["Не заданы глины (компоненты шихты)."]}

    # Цель система считает сама по способу формования, если не задана явно
    target_ip = (inp.target_plasticity if inp.target_plasticity is not None
                 else recommended_target_plasticity(inp.forming))
    blended_ip, blended_oxides = average_blend(inp.clays)
    leaning = recommend_leaning(inp.clays, target_ip, inp.sand_plasticity)
    forming = forming_guidance(inp.forming)
    feeders = select_feeder(inp.raw_tph or 1.0, components=len(inp.clays) + 1,
                            max_feeders=inp.max_feeders, averaging=True)
    yard = clay_yard(inp.annual_clay_t) if inp.annual_clay_t > 0 else None
    quarry = quarry_output(inp.annual_clay_t, reserves_t=inp.reserves_t).model_dump() \
        if inp.annual_clay_t > 0 else None

    sensitivity = None
    if inp.sensitivity_coeff is not None:
        grp = sensitivity_group(inp.sensitivity_coeff)
        rec = ("высокая чувствительность — мягкий режим сушки/отощение"
               if inp.sensitivity_coeff > 2 else
               "умеренная — стандартный режим сушки" if inp.sensitivity_coeff > 1 else
               "низкая — допускается ускоренная сушка")
        sensitivity = {"coeff": inp.sensitivity_coeff, "group": grp, "recommendation": rec}

    # Контрольные точки опробования — что замерить лаборатории
    control_points = [
        "Число пластичности каждой глины (WL, WP) — подтвердить группу сырья.",
        "Коэффициент чувствительности к сушке усреднённой шихты.",
        "Гранулометрия и карбонатные включения (>0,5 мм недопустимы для лицевого).",
        "Воздушная и огневая усадка, водопоглощение и прочность образцов после обжига.",
    ]

    return {
        "has_data": True,
        "blend": {"plasticity": blended_ip, "group": plasticity_group(blended_ip),
                  "oxides": blended_oxides, "clays": len(inp.clays)},
        "leaning": leaning.model_dump(),
        "sensitivity": sensitivity,
        "forming": forming,
        "feeders": feeders.model_dump(),
        "yard": yard.model_dump() if yard else None,
        "quarry": quarry,
        "control_points": control_points,
    }
