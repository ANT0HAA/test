"""
Сбор данных проекта для генерации документов и общие константы оформления.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from agents.definitions import get_agents
from storage import db as storage

DocType = Literal["docx", "xlsx", "pdf"]

# Реквизиты для основной надписи (штампа). Минимальный набор по ЕСКД/СПДС.
ORG_NAME = "AI Конструкторское бюро"
ORG_SUBTITLE = "Мультиагентная платформа проектирования керамических заводов"

INDUSTRY_NAMES = {
    "ceramics": "Керамические (кирпичные) заводы",
}


@dataclass
class AgentSection:
    """Раздел документа — вклад одного агента (его ответы по проекту)."""
    agent_id: str
    display_name: str
    content: str


@dataclass
class ProjectExportData:
    """Данные проекта, подготовленные для генераторов документов."""
    project_id: str
    name: str
    industry: str
    created_at: datetime
    tasks: list[str] = field(default_factory=list)          # запросы пользователя
    sections: list[AgentSection] = field(default_factory=list)  # ответы по агентам
    raw_text: str = ""                                       # весь текст ответов (для извлечения)
    calc_summary: str = ""                                   # детерминированные расчёты (текст)
    equipment: list[dict] = field(default_factory=list)      # подобранное оборудование
    spec: dict = field(default_factory=dict)                 # структурная спецификация (единый источник)
    lab: dict = field(default_factory=dict)                  # лабораторный расчёт по сырью (если задан)

    @property
    def industry_name(self) -> str:
        return INDUSTRY_NAMES.get(self.industry, self.industry)

    @property
    def date_str(self) -> str:
        return self.created_at.strftime("%d.%m.%Y")


def balance_lines(spec: dict) -> list[str]:
    """Текстовые строки материального баланса по переделам для документов."""
    bal = (spec or {}).get("balance")
    if not bal or not bal.get("stages"):
        return []
    lines = [f"{s['name']}: {s['t_per_year']:,.0f} т/год ({s['t_per_hour']:g} т/ч)."
             .replace(",", " ") for s in bal["stages"]]
    lines.append(f"Вода на затворение: {bal['forming_water_t_per_year']:,.0f} т/год; "
                 f"удалено влаги в сушке: {bal['water_removed_drying_t']:,.0f} т/год; "
                 f"потери при прокаливании (обжиг): {bal['loi_removed_firing_t']:,.0f} т/год."
                 .replace(",", " "))
    lines.append(f"Брак: сушки {bal['reject_drying_t']:,.0f} т/год, "
                 f"обжига {bal['reject_firing_t']:,.0f} т/год.".replace(",", " "))
    return lines


def lab_lines(lab: dict) -> list[str]:
    """Текстовые строки лабораторного раздела для документов (docx/pdf)."""
    if not lab or not lab.get("has_data"):
        return []
    lines: list[str] = []
    b = lab.get("blend", {})
    if b:
        lines.append(f"Усреднённая шихта: Ip {b.get('plasticity')} — {b.get('group')} "
                     f"(глин: {b.get('clays')}).")
    ln = lab.get("leaning", {})
    if ln:
        if ln.get("need_leaning"):
            lines.append(f"Отощитель (песок): ≈ {ln.get('sand_fraction_pct')}% "
                         f"(цель Ip {ln.get('target_plasticity')}).")
        else:
            lines.append("Отощитель не требуется — пластичность в норме.")
    s = lab.get("sensitivity")
    if s:
        lines.append(f"Чувствительность к сушке: Кч {s.get('coeff')} — {s.get('group')} "
                     f"({s.get('recommendation')}).")
    f = lab.get("feeders", {})
    if f:
        lines.append(f"Питатели: {f.get('feeders_used')} × {f.get('model')} "
                     f"({f.get('unit_capacity_tph')} т/ч).")
    q = lab.get("quarry")
    if q:
        life = f", срок отработки ≈ {q.get('life_years')} лет" if q.get("life_years") else ""
        lines.append(f"Выработка карьера: добыть {q.get('mined_clay_t')} т/год "
                     f"(полезного {q.get('usable_clay_t')} т/год){life}.")
    fm = lab.get("forming", {})
    if fm:
        lines.append(f"Формование ({fm.get('method')}): влажность {fm.get('moisture')}, "
                     f"{fm.get('press')}. Добавки: {fm.get('additive_stage')}.")
    cps = lab.get("control_points", [])
    if cps:
        lines.append("Контрольные точки опробования: " + "; ".join(cps))
    return lines


async def collect_project_content(project_id: str) -> ProjectExportData:
    """
    Загрузить проект и его историю, сгруппировать ответы по агентам
    (в порядке первого появления). Бросает LookupError, если проекта нет.
    """
    project = await storage.get_project(project_id)
    if not project:
        raise LookupError(f"Проект не найден: {project_id}")

    messages = await storage.get_messages(project_id, limit=1000)

    tasks: list[str] = []
    grouped: dict[str, list[str]] = {}
    order: list[str] = []

    for m in messages:
        if m.role == "human":
            text = m.content.strip()
            if text and not text.lower().startswith("запомни"):
                tasks.append(text)
        else:  # ai
            agent = m.agent or "orchestrator"
            if agent not in grouped:
                grouped[agent] = []
                order.append(agent)
            grouped[agent].append(m.content.strip())

    industry_agents = get_agents(project.industry)
    sections = [
        AgentSection(
            agent_id=agent,
            display_name=industry_agents.get(agent, {}).get("display_name", agent),
            content="\n\n".join(p for p in grouped[agent] if p),
        )
        for agent in order
    ]
    raw_text = "\n\n".join(s.content for s in sections)

    # Единый источник истины: структурная спецификация (build_spec) по исходным
    # данным проекта. Из неё же берём ведомость оборудования и текстовую сводку —
    # чтобы числа в документах совпадали со спецификацией на экране.
    calc_summary = ""
    equipment: list[dict] = []
    spec: dict = {}
    try:
        inputs = await storage.get_project_inputs(project_id)
        if inputs:
            from calc import build_spec, build_summary
            spec = build_spec(inputs)
            calc_summary = build_summary(inputs)
            if spec.get("has_data"):
                equipment = [{"role": it["role"], "name": it["name"],
                              "capacity": it["unit_capacity"], "qty": it["qty"]}
                             for it in spec.get("equipment", {}).get("items", [])]
    except Exception:
        pass

    # Лабораторный расчёт по сырью — ТОЛЬКО по сохранённым в проект данным
    # (детерминированно, без LLM). Если глины не заданы — раздела в документе нет.
    lab: dict = {}
    try:
        saved = await storage.get_project_lab(project_id)
        if saved.get("clays"):
            from calc import ClaySource, LabInput, lab_report
            annual_clay = 0.0
            raw_tph = 0.0
            if spec.get("has_data"):
                res = spec.get("resources", {})
                annual_clay = (res.get("clay_main_t", 0) or 0) + (res.get("clay_kaolin_t", 0) or 0)
                raw_tph = spec.get("equipment", {}).get("throughput_tph", 0) or 0
            clays = [ClaySource(name=c.get("name", ""),
                                plasticity=float(c.get("plasticity") or 15.0),
                                oxides=c.get("oxides") or {})
                     for c in saved["clays"] if c.get("name")]
            if clays:
                lab = lab_report(LabInput(
                    clays=clays, forming=saved.get("forming") or "пластическое",
                    sensitivity_coeff=saved.get("sensitivity_coeff"),
                    annual_clay_t=annual_clay, raw_tph=raw_tph,
                    reserves_t=float(saved.get("reserves_t") or 0)))
    except Exception:
        pass

    return ProjectExportData(
        project_id=project.id,
        name=project.name,
        industry=project.industry,
        created_at=project.created_at,
        tasks=tasks,
        sections=sections,
        raw_text=raw_text,
        calc_summary=calc_summary,
        equipment=equipment,
        spec=spec,
        lab=lab,
    )
