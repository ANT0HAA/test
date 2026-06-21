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

    @property
    def industry_name(self) -> str:
        return INDUSTRY_NAMES.get(self.industry, self.industry)

    @property
    def date_str(self) -> str:
        return self.created_at.strftime("%d.%m.%Y")


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
    )
