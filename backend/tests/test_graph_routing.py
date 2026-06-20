"""
Тесты графа на фейковом LLM: маршрутизация, план, цикл доработки, лимиты.
Внешние сервисы не нужны (search/memory подменены).
"""
import pytest

import graph.graph as G
from graph.graph import (
    build_graph, PlanDecision, PlanStep, GRAPH_RECURSION_LIMIT,
    VERDICT_OK, VERDICT_REWORK,
)
from langchain_core.messages import HumanMessage, AIMessage
from tests.conftest import make_fake_llm_factory


@pytest.fixture(autouse=True)
def _no_external(monkeypatch):
    """Отключаем доступ к БЗ и памяти проектов."""
    monkeypatch.setattr(G, "search", lambda *a, **k: "")

    async def _empty_mem(*a, **k):
        return ""
    monkeypatch.setattr(G, "_memory_context", _empty_mem)


def _state(text, *, direct=None, industry="ceramics"):
    return {
        "messages": [HumanMessage(content=text)],
        "direct_agent": direct, "active_agent": direct or "orchestrator",
        "delegated_task": "", "action": "", "project_id": "", "industry": industry,
        "plan": [], "step": 0, "iteration": 0, "review": False,
        "review_feedback": "", "done": False,
    }


def _ai_names(final):
    return [m.name for m in final["messages"] if isinstance(m, AIMessage)]


async def _run(state):
    return await build_graph().ainvoke(state, config={"recursion_limit": GRAPH_RECURSION_LIMIT})


async def test_direct_agent_single_bubble(monkeypatch):
    monkeypatch.setattr(G, "_llm", make_fake_llm_factory("Ответ технолога."))
    final = await _run(_state("какая марка кирпича", direct="technologist"))
    assert _ai_names(final) == ["technologist"]
    assert final["done"] is False or final.get("review") is False


async def test_plan_with_norm_control_approve(monkeypatch):
    plan = PlanDecision(reasoning="r", action="delegate",
                        plan=[PlanStep(agent="builder", task="каркас"),
                              PlanStep(agent="mechanic", task="оборудование")])
    monkeypatch.setattr(G, "_llm", make_fake_llm_factory(f"Готово. ВЕРДИКТ: {VERDICT_OK}", plan))
    final = await _run(_state("спроектируй обжигательный корпус"))
    assert _ai_names(final) == ["builder", "mechanic", "norm_control"]
    assert final["done"] is True
    assert final["iteration"] == 0


async def test_rework_loop_capped(monkeypatch):
    plan = PlanDecision(reasoning="r", action="delegate",
                        plan=[PlanStep(agent="builder", task="каркас")])
    monkeypatch.setattr(G, "_llm", make_fake_llm_factory(f"Замечания. ВЕРДИКТ: {VERDICT_REWORK}", plan))
    final = await _run(_state("спроектируй корпус"))
    names = _ai_names(final)
    # исходный проход + 2 доработки → нормоконтроль вызван 3 раза, без зацикливания
    assert names.count("norm_control") == 3
    assert names.count("builder") == 3
    assert final["iteration"] == 2
    assert final["done"] is True


async def test_keyword_fallback_when_planner_fails(monkeypatch):
    # planner бросает (None plan_decision → ainvoke вернёт None → .action упадёт)
    monkeypatch.setattr(G, "_llm", make_fake_llm_factory("Ответ.", plan_decision=None))
    final = await _run(_state("рассчитай печь обжига и температуру"))  # ключевые слова → technologist
    names = _ai_names(final)
    assert names == ["technologist"]  # single-agent fallback, без нормоконтроля


async def test_self_answer_when_no_plan(monkeypatch):
    plan = PlanDecision(reasoning="r", action="answer_self", plan=[])
    monkeypatch.setattr(G, "_llm", make_fake_llm_factory("Общий ответ.", plan))
    final = await _run(_state("привет, что ты умеешь"))
    assert _ai_names(final) == ["orchestrator"]


async def test_other_industry_plan(monkeypatch):
    plan = PlanDecision(reasoning="r", action="delegate",
                        plan=[PlanStep(agent="technologist", task="состав бетона")])
    monkeypatch.setattr(G, "_llm", make_fake_llm_factory(f"ОК. ВЕРДИКТ: {VERDICT_OK}", plan))
    final = await _run(_state("подбери состав бетона", industry="concrete"))
    names = _ai_names(final)
    assert "technologist" in names and names[-1] == "norm_control"
