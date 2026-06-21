"""
Тесты уточняющих форм: распознавание запроса на проектирование и определение
недостающих обязательных исходных данных (без внешних сервисов).
"""
from main import _DESIGN_TRIGGER_RE, _missing_required_fields


def test_design_trigger_detects_request():
    assert _DESIGN_TRIGGER_RE.search("Спроектируй кирпичный завод")
    assert _DESIGN_TRIGGER_RE.search("рассчитай производство и подбери оборудование")
    assert not _DESIGN_TRIGGER_RE.search("привет, как дела?")
    assert not _DESIGN_TRIGGER_RE.search("спасибо")


def test_missing_required_fields():
    assert [f.key for f in _missing_required_fields({})] == ["product", "capacity"]
    assert [f.key for f in _missing_required_fields({"product": "кирпич"})] == ["capacity"]
    assert _missing_required_fields({"product": "кирпич", "capacity": "30000 шт/смену"}) == []
    # пустые строки не считаются заполненными
    assert [f.key for f in _missing_required_fields({"product": "  ", "capacity": ""})] == \
        ["product", "capacity"]
