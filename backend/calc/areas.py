"""
Оценка площадей корпусов завода.

Базовые площади соответствуют типовому заводу ~15 млн шт/год (габариты корпусов
из генплана) и масштабируются от заданного объёма выпуска.
"""
from pydantic import BaseModel, Field

# Базовые площади корпусов, м² (≈15 млн шт/год) — из габаритов генплана
_BASE_AREAS = {
    "Склад сырья": 648,            # 18×36
    "Подготовительный цех": 1152,  # 24×48
    "Формовочный цех": 1728,       # 24×72
    "Сушильный корпус": 1728,      # 18×96
    "Обжигательный корпус": 2160,  # 18×120
    "Склад готовой продукции": 2160,  # 36×60
}
_BASE_CAPACITY = 15_000_000.0


class AreasInput(BaseModel):
    pieces_per_year: float = Field(..., description="Выпуск, шт/год")


class AreasResult(BaseModel):
    areas_m2: dict[str, float]
    total_m2: float
    notes: list[str] = []


# Типовые пролёты корпусов, м (ширина) — для перевода площади в габариты
_CORPUS_SPAN = {
    "Склад сырья": 18, "Подготовительный цех": 24, "Формовочный цех": 24,
    "Сушильный корпус": 18, "Обжигательный корпус": 18, "Склад готовой продукции": 36,
}


def buildings_from_areas(pieces_per_year: float) -> list[dict]:
    """Корпуса (название, ширина, длина) из вычисленных площадей — для генплана."""
    ar = estimate_areas(AreasInput(pieces_per_year=pieces_per_year))
    out: list[dict] = []
    for name, area in ar.areas_m2.items():
        span = _CORPUS_SPAN.get(name, 18)
        out.append({"name": name, "width_m": float(span), "length_m": round(area / span)})
    return out


def estimate_areas(inp: AreasInput) -> AreasResult:
    # Площади масштабируются как ~корень из отношения производительностей
    # (рост габаритов медленнее линейного), но не меньше базовых/2.
    ratio = max(inp.pieces_per_year / _BASE_CAPACITY, 0.01) ** 0.6
    areas = {k: round(v * ratio, 0) for k, v in _BASE_AREAS.items()}
    total = round(sum(areas.values()), 0)
    return AreasResult(
        areas_m2=areas, total_m2=total,
        notes=[f"Площади масштабированы от типового завода 15 млн шт/год "
               f"(коэффициент {ratio:.2f}); уточняются компоновкой оборудования."],
    )
