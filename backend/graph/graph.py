"""
Мультиагентный граф на LangGraph.

Архитектура:
  orchestrator_router → (если прямой вызов) → agent_node → END
                      → (если делегирование) → agent_node → END
                      → (если отвечает сам)  → orchestrator_respond → END

Стриминг: токены идут только из orchestrator_respond или agent_node,
          НЕ из orchestrator_router (там structured output без стриминга).
"""
from typing import TypedDict, Annotated, Literal
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel

from config import settings
from agents.definitions import AGENTS
from knowledge.chroma import search
from storage.db import get_memory


# ─── State ────────────────────────────────────────────────────────────

class BureauState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    direct_agent: str | None   # Если пользователь выбрал конкретного агента
    active_agent: str          # Кто сейчас отвечает
    delegated_task: str        # Задача, переданная специалисту
    action: str                # "delegate" | "respond_self" | "done"
    project_id: str            # Проект, в рамках которого идёт диалог (память по проекту)


async def _memory_context(project_id: str, agent_id: str) -> str:
    """Запомненные ранее решения проекта для данного агента (для подмеса в системный промпт)."""
    rows = await get_memory(project_id, agent_id)
    if not rows:
        return ""
    return "\n".join(f"• {row.value}" for row in rows)


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


# ─── Structured output for routing decision ────────────────────────────

AGENT_IDS = Literal[
    "technologist", "builder", "mechanic", "electrician",
    "kipia", "norm_control", "estimator", "documentalist"
]


class RoutingDecision(BaseModel):
    """Решение оркестратора: отвечать самому или делегировать."""
    reasoning: str
    action: Literal["answer_self", "delegate"]
    next_agent: AGENT_IDS | None = None
    task_for_agent: str = ""


# ─── Keyword fallback for routing (если structured output не сработал) ─

_ROUTING_KEYWORDS: dict[str, list[str]] = {
    "technologist": ["глин", "обжиг", "сушк", "масс", "шихт", "формов", "техпроцесс",
                     "клинкер", "марк", "морозостойк", "печь", "температур", "состав"],
    "builder": ["здани", "цех", "корпус", "фундамент", "констукц", "конструкц",
                "каркас", "колонн", "балк", "ферм", "кровл", "перекрыт", "снип", "сп "],
    "mechanic": ["пресс", "дробилк", "бегун", "конвейер", "вагонетк", "толкатель",
                 "горелк", "дымосос", "вентилятор", "оборудован", "привод", "мельниц"],
    "electrician": ["электр", "кабел", "щит", "трансформатор", "квт", "освещ",
                    "напряжен", "заземлен", "пуэ", "двигател", "подстанц"],
    "kipia": ["автоматиз", "плк", "scada", "датчик", "термопар", "кип", "асутп",
              "регулятор", "контроллер", "измерен", "сигнал"],
    "norm_control": ["гост", "норматив", "соответств", "требован", "проверь",
                     "проверк", "норм", "ту ", "еск", "спдс", "стандарт"],
    "estimator": ["смет", "стоимост", "цен", "расцен", "ведомост", "спецификац",
                  "bom", "бюджет", "затрат", "калькуляц"],
    "documentalist": ["документ", "отчёт", "отчет", "пояснительн", "записк", "тз ",
                      "техническое задание", "комплект", "оформлен", "раздел"],
}


def _keyword_route(text: str) -> str | None:
    """Простая эвристика выбора агента по ключевым словам."""
    low = text.lower()
    scores: dict[str, int] = {}
    for agent, kws in _ROUTING_KEYWORDS.items():
        scores[agent] = sum(1 for kw in kws if kw in low)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


# ─── Orchestrator router (НЕ стримит) ─────────────────────────────────

async def orchestrator_router(state: BureauState) -> dict:
    """
    Если выбран прямой агент — сразу делегируем ему без вызова LLM.
    Иначе — спрашиваем LLM куда маршрутизировать (structured output),
    с откатом на ключевые слова, если локальная модель не вернула валидный JSON.
    """
    direct = state.get("direct_agent")
    if direct and direct != "orchestrator":
        last_msg = next(
            (m.content for m in reversed(state["messages"])
             if isinstance(m, HumanMessage)), ""
        )
        return {
            "active_agent": direct,
            "delegated_task": last_msg,
            "action": "delegate",
        }

    user_text = next(
        (m.content for m in reversed(state["messages"])
         if isinstance(m, HumanMessage)), ""
    )

    agent_list = "\n".join(
        f"• {k}: {v['display_name']} — {v['description']}"
        for k, v in AGENTS.items()
        if k != "orchestrator"
    )
    system = (
        AGENTS["orchestrator"]["system_prompt"]
        + f"\n\nСписок специалистов:\n{agent_list}"
        + "\n\nОтветь СТРОГО JSON-объектом RoutingDecision без пояснений."
    )
    messages = [SystemMessage(content=system)] + list(state["messages"])

    # Пытаемся получить structured output. На локальных моделях это может
    # не сработать — тогда откатываемся на эвристику по ключевым словам.
    try:
        llm = _llm(streaming=False).with_structured_output(RoutingDecision)
        decision: RoutingDecision = await llm.ainvoke(messages)

        if decision.action == "delegate" and decision.next_agent:
            return {
                "active_agent": decision.next_agent,
                "delegated_task": decision.task_for_agent or user_text,
                "action": "delegate",
            }
        return {"active_agent": "orchestrator", "action": "respond_self"}

    except Exception:
        # Откат: ключевые слова. Если ничего не совпало — отвечает оркестратор.
        agent = _keyword_route(user_text)
        if agent:
            return {
                "active_agent": agent,
                "delegated_task": user_text,
                "action": "delegate",
            }
        return {"active_agent": "orchestrator", "action": "respond_self"}


# ─── Orchestrator direct response (стримит) ───────────────────────────

async def orchestrator_respond(state: BureauState) -> dict:
    """Оркестратор отвечает пользователю напрямую."""
    kb_context = search(state["messages"][-1].content, "orchestrator")
    system = AGENTS["orchestrator"]["system_prompt"]
    if kb_context:
        system += f"\n\n--- Контекст из базы знаний ---\n{kb_context}"

    memory_context = await _memory_context(state["project_id"], "orchestrator")
    if memory_context:
        system += f"\n\n--- Запомненные решения по проекту ---\n{memory_context}"

    messages = [SystemMessage(content=system)] + list(state["messages"])
    response = await _llm(streaming=True).ainvoke(messages)

    return {
        "messages": [AIMessage(content=response.content, name="orchestrator")],
        "action": "done",
    }


# ─── Specialist node factory ───────────────────────────────────────────

def _make_specialist(agent_id: str):
    """Фабрика: создаёт async-функцию ноды для агента."""

    async def specialist_node(state: BureauState) -> dict:
        agent_def = AGENTS[agent_id]

        # Определяем запрос для поиска по базе знаний
        query = state.get("delegated_task") or state["messages"][-1].content

        # Ищем в базе знаний агента
        kb_context = search(query, agent_id)
        system = agent_def["system_prompt"]
        if kb_context:
            system += f"\n\n--- Контекст из базы знаний ---\n{kb_context}"

        memory_context = await _memory_context(state["project_id"], agent_id)
        if memory_context:
            system += f"\n\n--- Запомненные решения по проекту ---\n{memory_context}"

        # Если задача пришла от оркестратора — добавляем её явно
        messages = [SystemMessage(content=system)] + list(state["messages"])
        if state.get("delegated_task") and state.get("direct_agent") != agent_id:
            messages.append(
                HumanMessage(content=f"Задача от Главного конструктора: {state['delegated_task']}")
            )

        response = await _llm(streaming=True).ainvoke(messages)
        return {
            "messages": [AIMessage(content=response.content, name=agent_id)],
            "active_agent": agent_id,
            "action": "done",
        }

    specialist_node.__name__ = agent_id  # для LangGraph metadata
    return specialist_node


# ─── Routing logic ────────────────────────────────────────────────────

def _route_after_router(state: BureauState) -> str:
    action = state.get("action", "respond_self")
    if action == "delegate":
        return state.get("active_agent", "orchestrator_respond")
    return "orchestrator_respond"


# ─── Build & compile graph ────────────────────────────────────────────

def build_graph():
    g = StateGraph(BureauState)

    # Ноды
    g.add_node("orchestrator_router", orchestrator_router)
    g.add_node("orchestrator_respond", orchestrator_respond)

    specialist_ids = [k for k in AGENTS if k != "orchestrator"]
    for sid in specialist_ids:
        g.add_node(sid, _make_specialist(sid))

    # Точка входа
    g.set_entry_point("orchestrator_router")

    # Условный переход из роутера
    g.add_conditional_edges(
        "orchestrator_router",
        _route_after_router,
        {sid: sid for sid in specialist_ids} | {"orchestrator_respond": "orchestrator_respond"},
    )

    # Все конечные ноды → END
    g.add_edge("orchestrator_respond", END)
    for sid in specialist_ids:
        g.add_edge(sid, END)

    return g.compile()


# Синглтон скомпилированного графа
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
