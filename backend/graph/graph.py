"""
Мультиагентный граф на LangGraph.

Архитектура (Фаза 2 — межагентное взаимодействие):
  orchestrator_router
    ├─ прямой агент      → dispatch → <specialist> → dispatch → END
    ├─ план (несколько)  → dispatch → <s1> → dispatch → <s2> → ... → norm_control_review
    │                         └─ при замечаниях: возврат на доработку (цикл, ≤ MAX_ITERATIONS)
    └─ отвечает сам       → orchestrator_respond → END

Узел `dispatch` — маршрутизатор без LLM: по плану направляет к следующему
специалисту, по исчерпании плана — к нормоконтролёру (если нужен ревью), иначе END.

Стриминг: токены идут только из узлов-агентов (specialist / orchestrator_respond /
          norm_control_review). orchestrator_router и dispatch модель не стримят.
Защита от зацикливания: лимит итераций доработки (MAX_ITERATIONS) +
жёсткий лимит шагов графа (GRAPH_RECURSION_LIMIT, задаётся при вызове в main.py).
"""
from typing import TypedDict, Annotated, Literal
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel

from config import settings
from agents.definitions import (
    get_agents, routing_keywords, all_agent_ids, DEFAULT_INDUSTRY,
)
from knowledge.chroma import search
from storage.db import get_memory


# ─── Константы межагентного режима ─────────────────────────────────────

MAX_ITERATIONS = 2        # максимум итераций доработки по замечаниям нормоконтролёра
MAX_PLAN_AGENTS = 5       # ограничение размера плана (защита от раздувания)
GRAPH_RECURSION_LIMIT = 50  # жёсткий лимит шагов графа (передаётся в astream_events)

# Вердикт нормоконтролёра — машиночитаемые маркеры в конце его ответа
VERDICT_REWORK = "НА ДОРАБОТКУ"
VERDICT_OK = "СОГЛАСОВАНО"


# ─── State ────────────────────────────────────────────────────────────

class BureauState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    direct_agent: str | None   # Если пользователь выбрал конкретного агента
    active_agent: str          # Кто сейчас отвечает
    delegated_task: str        # Задача последнего шага (для обратной совместимости)
    action: str                # "execute" | "respond_self"
    project_id: str            # Проект, в рамках которого идёт диалог (память по проекту)
    industry: str              # Отрасль проекта (определяет набор агентов и базу знаний)

    # Межагентное взаимодействие
    plan: list[dict]           # План работ: [{"agent": id, "task": str}, ...]
    step: int                  # Индекс текущего шага плана
    iteration: int             # Счётчик итераций доработки
    review: bool               # Нужен ли финальный нормоконтроль
    review_feedback: str       # Замечания нормоконтролёра для доработки
    done: bool                 # Граф завершил работу (после ревью)


async def _memory_context(project_id: str, agent_id: str) -> str:
    """Запомненные ранее решения проекта для данного агента (для подмеса в системный промпт)."""
    if not project_id:
        return ""
    rows = await get_memory(project_id, agent_id)
    if not rows:
        return ""
    return "\n".join(f"• {row.value}" for row in rows)


def _last_human(messages: list[BaseMessage]) -> str:
    return next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")


# ─── LLM factory ──────────────────────────────────────────────────────

def _llm(streaming: bool = False) -> BaseChatModel:
    """
    Создаёт LLM согласно настройке LLM_PROVIDER.
    По умолчанию — локальная модель через Ollama.
    """
    provider = settings.llm_provider.lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
            num_predict=settings.llm_max_tokens,
            reasoning=settings.llm_reasoning,  # False — отключает «думанье» qwen3
            # streaming у ChatOllama включается на уровне вызова astream/astream_events
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            streaming=streaming,
            api_key=settings.anthropic_api_key,
        )

    raise ValueError(f"Неизвестный LLM_PROVIDER: {settings.llm_provider}")


async def _stream_text(messages: list[BaseMessage]) -> str:
    """
    Сгенерировать ответ модели в потоковом режиме и вернуть полный текст.

    Используем `.astream()`, а не `.ainvoke()`: локальные модели (ChatOllama)
    при `.ainvoke` НЕ выдают пошаговые токены, и `astream_events` не получает
    `on_chat_model_stream` — в UI ничего не «капает». `.astream` гарантирует
    потоковую отдачу токенов для обоих провайдеров.
    """
    parts: list[str] = []
    async for chunk in _llm(streaming=True).astream(messages):
        if chunk.content:
            parts.append(chunk.content)
    return "".join(parts)


# ─── Structured output для планирования ────────────────────────────────

class PlanStep(BaseModel):
    """Один шаг плана: какому специалисту какую подзадачу поручить."""
    agent: str   # id агента отрасли; валидируется в _sanitize_plan
    task: str


class PlanDecision(BaseModel):
    """Решение оркестратора: ответить самому или составить план из специалистов."""
    reasoning: str
    action: Literal["answer_self", "delegate"]
    plan: list[PlanStep] = []


# ─── Keyword fallback (если structured output не сработал на локальной модели) ─

def _keyword_route(text: str, industry: str) -> str | None:
    """Простая эвристика выбора агента по ключевым словам отрасли."""
    low = text.lower()
    keywords = routing_keywords(industry)
    if not keywords:
        return None
    scores = {agent: sum(1 for kw in kws if kw in low) for agent, kws in keywords.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def _sanitize_plan(steps: list[PlanStep], fallback_task: str, valid_agents: set[str]) -> list[dict]:
    """
    Приводит план к рабочему виду: убирает нормоконтролёра (он работает как
    финальный ревьюер автоматически), отбрасывает агентов не из отрасли,
    ограничивает длину MAX_PLAN_AGENTS.
    """
    plan: list[dict] = []
    seen: set[str] = set()
    for s in steps:
        if s.agent == "norm_control" or s.agent not in valid_agents:
            continue
        if s.agent in seen:
            continue  # один агент — один шаг в плане
        seen.add(s.agent)
        plan.append({"agent": s.agent, "task": s.task.strip() or fallback_task})
        if len(plan) >= MAX_PLAN_AGENTS:
            break
    return plan


def _industry_of(state: BureauState) -> str:
    return state.get("industry") or DEFAULT_INDUSTRY


# ─── Базовое начальное состояние межагентных полей ─────────────────────

def _base_fields() -> dict:
    return {
        "plan": [],
        "step": 0,
        "iteration": 0,
        "review": False,
        "review_feedback": "",
        "done": False,
    }


# ─── Orchestrator router / planner (НЕ стримит) ───────────────────────

async def orchestrator_router(state: BureauState) -> dict:
    """
    Прямой агент → план из одного шага, без ревью (поведение прямого диалога).
    Иначе оркестратор формирует план из нескольких специалистов (structured output),
    с откатом на ключевые слова (single-agent, без ревью), если модель не вернула план.
    """
    user_text = _last_human(state["messages"])

    industry = _industry_of(state)
    agents = get_agents(industry)
    has_norm_control = "norm_control" in agents

    direct = state.get("direct_agent")
    if direct and direct != "orchestrator":
        return {
            **_base_fields(),
            "active_agent": direct,
            "delegated_task": user_text,
            "action": "execute",
            "plan": [{"agent": direct, "task": user_text}],
            "review": False,
        }

    agent_list = "\n".join(
        f"• {k}: {v['display_name']} — {v['description']}"
        for k, v in agents.items()
        if k not in ("orchestrator", "norm_control")
    )
    system = (
        agents["orchestrator"]["system_prompt"]
        + f"\n\nСписок специалистов:\n{agent_list}"
        + "\n\nРазбей задачу контролёра проекта на подзадачи и распредели их между "
          "специалистами (от 1 до 5 шагов, по одному на агента). Нормоконтролёра "
          "НЕ включай — он проверит результат автоматически. Если задача простая "
          "или общая — верни action='answer_self' с пустым планом."
        + "\n\nОтветь СТРОГО JSON-объектом PlanDecision без пояснений."
    )
    messages = [SystemMessage(content=system)] + list(state["messages"])
    valid_agents = {k for k in agents if k != "orchestrator"}

    # Пытаемся получить план. На локальных моделях structured output может
    # не сработать — тогда откатываемся на эвристику по ключевым словам.
    try:
        llm = _llm(streaming=False).with_structured_output(PlanDecision)
        decision: PlanDecision = await llm.ainvoke(messages)

        if decision.action == "delegate":
            plan = _sanitize_plan(decision.plan, user_text, valid_agents)
            if plan:
                return {
                    **_base_fields(),
                    "active_agent": plan[0]["agent"],
                    "delegated_task": plan[0]["task"],
                    "action": "execute",
                    "plan": plan,
                    "review": has_norm_control,  # нормоконтроль, если он есть в отрасли
                }
        return {**_base_fields(), "active_agent": "orchestrator", "action": "respond_self"}

    except Exception:
        # Откат: один агент по ключевым словам, без ревью (деградация на слабой модели).
        agent = _keyword_route(user_text, industry)
        if agent:
            return {
                **_base_fields(),
                "active_agent": agent,
                "delegated_task": user_text,
                "action": "execute",
                "plan": [{"agent": agent, "task": user_text}],
                "review": False,
            }
        return {**_base_fields(), "active_agent": "orchestrator", "action": "respond_self"}


# ─── Orchestrator direct response (стримит) ───────────────────────────

async def orchestrator_respond(state: BureauState) -> dict:
    """Оркестратор отвечает пользователю напрямую."""
    industry = _industry_of(state)
    kb_context = search(_last_human(state["messages"]), "orchestrator", industry)
    system = get_agents(industry)["orchestrator"]["system_prompt"]
    if kb_context:
        system += f"\n\n--- Контекст из базы знаний ---\n{kb_context}"

    memory_context = await _memory_context(state.get("project_id", ""), "orchestrator")
    if memory_context:
        system += f"\n\n--- Запомненные решения по проекту ---\n{memory_context}"

    messages = [SystemMessage(content=system)] + list(state["messages"])
    content = await _stream_text(messages)

    return {
        "messages": [AIMessage(content=content, name="orchestrator")],
        "active_agent": "orchestrator",
        "done": True,
    }


# ─── Specialist node factory ───────────────────────────────────────────

def _make_specialist(agent_id: str):
    """Фабрика: создаёт async-функцию ноды для агента."""

    async def specialist_node(state: BureauState) -> dict:
        industry = _industry_of(state)
        agent_def = get_agents(industry)[agent_id]
        plan = state.get("plan", [])
        step = state.get("step", 0)

        # Задача текущего шага плана (или последний вопрос пользователя)
        task = plan[step]["task"] if 0 <= step < len(plan) else (
            state.get("delegated_task") or _last_human(state["messages"])
        )

        # База знаний агента
        kb_context = search(task, agent_id, industry)
        system = agent_def["system_prompt"]
        if kb_context:
            system += f"\n\n--- Контекст из базы знаний ---\n{kb_context}"

        # Память проекта
        memory_context = await _memory_context(state.get("project_id", ""), agent_id)
        if memory_context:
            system += f"\n\n--- Запомненные решения по проекту ---\n{memory_context}"

        messages = [SystemMessage(content=system)] + list(state["messages"])

        # Делегированная задача (не для прямого диалога с этим же агентом)
        if state.get("direct_agent") != agent_id:
            framing = f"Задача от Главного конструктора: {task}"
            feedback = state.get("review_feedback", "")
            if feedback:
                framing += (
                    "\n\nПо предыдущей версии есть замечания нормоконтролёра — "
                    f"учти их при доработке:\n{feedback}"
                )
            messages.append(HumanMessage(content=framing))

        content = await _stream_text(messages)
        return {
            "messages": [AIMessage(content=content, name=agent_id)],
            "active_agent": agent_id,
            "step": step + 1,
        }

    specialist_node.__name__ = agent_id  # для LangGraph metadata
    return specialist_node


# ─── Norm control review (стримит) ────────────────────────────────────

async def norm_control_review(state: BureauState) -> dict:
    """
    Нормоконтролёр проверяет накопленные результаты специалистов.
    В конце ответа ставит машиночитаемый вердикт. При замечаниях и наличии
    лимита итераций — отправляет план на доработку, иначе завершает работу.
    """
    industry = _industry_of(state)
    agent_def = get_agents(industry)["norm_control"]
    system = (
        agent_def["system_prompt"]
        + "\n\nСейчас твоя роль — финальный нормоконтроль результатов специалистов выше "
          "по текущему диалогу. Проверь их на соответствие нормам и взаимную согласованность. "
          "Дай краткое заключение по существу.\n"
          f"В САМОМ КОНЦЕ ответа поставь ОТДЕЛЬНОЙ строкой ровно один из вердиктов:\n"
          f"«ВЕРДИКТ: {VERDICT_OK}» — если замечаний, требующих исправления, нет;\n"
          f"«ВЕРДИКТ: {VERDICT_REWORK}» — если есть замечания, которые специалисты должны устранить."
    )

    kb_context = search(_last_human(state["messages"]), "norm_control", industry)
    if kb_context:
        system += f"\n\n--- Контекст из базы знаний ---\n{kb_context}"
    memory_context = await _memory_context(state.get("project_id", ""), "norm_control")
    if memory_context:
        system += f"\n\n--- Запомненные решения по проекту ---\n{memory_context}"

    messages = [SystemMessage(content=system)] + list(state["messages"]) + [
        HumanMessage(content="Проверь результаты работы специалистов и вынеси вердикт.")
    ]
    text = await _stream_text(messages)
    upper = text.upper()

    iteration = state.get("iteration", 0)
    # Доработка только если явно «НА ДОРАБОТКУ» и не исчерпан лимит итераций.
    needs_rework = (VERDICT_REWORK in upper) and (iteration < MAX_ITERATIONS)

    out: dict = {
        "messages": [AIMessage(content=text, name="norm_control")],
        "active_agent": "norm_control",
    }
    if needs_rework:
        out.update({
            "iteration": iteration + 1,
            "step": 0,                 # перезапускаем план на доработку
            "review_feedback": text,
            "done": False,
        })
    else:
        out["done"] = True
    return out


# ─── Dispatch (НЕ стримит) ─────────────────────────────────────────────

async def dispatch(state: BureauState) -> dict:
    """Узел-проход: вся маршрутизация в `_route_from_dispatch`."""
    return {}


# ─── Routing logic ────────────────────────────────────────────────────

def _route_after_router(state: BureauState) -> str:
    if state.get("action") == "execute":
        return "dispatch"
    return "orchestrator_respond"


def _route_from_dispatch(state: BureauState) -> str:
    """Следующий шаг: специалист по плану → нормоконтроль → END."""
    if state.get("done"):
        return END
    plan = state.get("plan", [])
    step = state.get("step", 0)
    if step < len(plan):
        return plan[step]["agent"]
    if state.get("review"):
        return "norm_control_review"
    return END


# ─── Build & compile graph ────────────────────────────────────────────

def build_graph():
    g = StateGraph(BureauState)

    g.add_node("orchestrator_router", orchestrator_router)
    g.add_node("orchestrator_respond", orchestrator_respond)
    g.add_node("dispatch", dispatch)
    g.add_node("norm_control_review", norm_control_review)

    # Узлы — объединение специалистов по всем отраслям (граф один на все отрасли)
    specialist_ids = [k for k in all_agent_ids() if k != "orchestrator"]
    for sid in specialist_ids:
        g.add_node(sid, _make_specialist(sid))

    g.set_entry_point("orchestrator_router")

    # Из роутера — либо собственный ответ, либо в диспетчер плана
    g.add_conditional_edges(
        "orchestrator_router",
        _route_after_router,
        {"dispatch": "dispatch", "orchestrator_respond": "orchestrator_respond"},
    )

    # Диспетчер: к специалисту по плану / к нормоконтролю / END
    g.add_conditional_edges(
        "dispatch",
        _route_from_dispatch,
        {sid: sid for sid in specialist_ids}
        | {"norm_control_review": "norm_control_review", END: END},
    )

    # Специалисты и ревьюер возвращаются в диспетчер (он решает, что дальше)
    for sid in specialist_ids:
        g.add_edge(sid, "dispatch")
    g.add_edge("norm_control_review", "dispatch")

    g.add_edge("orchestrator_respond", END)

    return g.compile()


# Синглтон скомпилированного графа
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def reset_graph() -> None:
    """Сбросить синглтон графа — пересоберётся с актуальным набором агентов
    (после добавления/удаления агентов или отраслей через UI)."""
    global _graph
    _graph = None
