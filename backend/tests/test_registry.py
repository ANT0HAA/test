"""
Тесты эффективного реестра агентов/отраслей (built-in + кэш кастомизаций).
БД не нужна — кэш заполняется напрямую.
"""
import pytest

import agents.definitions as d


@pytest.fixture(autouse=True)
def _clean_cache():
    """Изолируем кэш кастомизаций для каждого теста."""
    d._custom_industry_names.clear()
    d._overrides.clear()
    yield
    d._custom_industry_names.clear()
    d._overrides.clear()


def test_builtin_industries_present():
    ids = [i["id"] for i in d.list_industries()]
    assert "ceramics" in ids and "concrete" in ids
    assert all(i["builtin"] for i in d.list_industries())


def test_builtin_ceramics_agents():
    agents = d.get_agents("ceramics")
    assert "orchestrator" in agents and "technologist" in agents
    assert agents["technologist"]["display_name"] == "Технолог производства"


def test_override_builtin_agent():
    d._overrides[("ceramics", "technologist")] = {
        "display_name": "Изменённый технолог", "description": "", "color": "",
        "icon": "", "system_prompt": "новый промпт", "keywords": "",
        "is_custom": False, "deleted": False,
    }
    agents = d.get_agents("ceramics")
    assert agents["technologist"]["display_name"] == "Изменённый технолог"
    assert agents["technologist"]["system_prompt"] == "новый промпт"


def test_custom_industry_and_agent():
    d._custom_industry_names["glass"] = "Стекольные заводы"
    d._overrides[("glass", "melter")] = {
        "display_name": "Стекловар", "description": "варка", "color": "#FFD000",
        "icon": "flame", "system_prompt": "ты стекловар", "keywords": "стекло,варка",
        "is_custom": True, "deleted": False,
    }
    industries = {i["id"]: i for i in d.list_industries()}
    assert "glass" in industries and industries["glass"]["builtin"] is False
    agents = d.get_agents("glass")
    assert "melter" in agents and agents["melter"]["display_name"] == "Стекловар"
    assert d.routing_keywords("glass")["melter"] == ["стекло", "варка"]
    assert "melter" in d.all_agent_ids()


def test_deleted_builtin_hidden():
    d._overrides[("ceramics", "documentalist")] = {
        "display_name": "", "description": "", "color": "", "icon": "",
        "system_prompt": "", "keywords": "", "is_custom": False, "deleted": True,
    }
    assert "documentalist" not in d.get_agents("ceramics")


def test_unknown_industry_falls_back_to_default():
    # проект ссылается на удалённую отрасль → агенты отрасли по умолчанию
    agents = d.get_agents("nonexistent")
    assert "orchestrator" in agents and "technologist" in agents
