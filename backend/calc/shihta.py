"""
Расчёт химического (оксидного) состава керамической массы из состава шихты.

Метод — из проектного документа заказчика «Расчёт состава шихты»: вклад каждого
компонента в оксид = доля компонента (%) × содержание оксида в нём (%) / 100.
Проверка: глина 31.9 % при SiO2 52.43 % даёт 16.72 % SiO2 (число документа).
"""
from pydantic import BaseModel, Field


class Component(BaseModel):
    name: str
    fraction: float = Field(..., description="Доля компонента в шихте, %")
    oxides: dict[str, float] = Field(default_factory=dict, description="Оксидный состав компонента, %")


class ShihtaInput(BaseModel):
    components: list[Component]


class ShihtaResult(BaseModel):
    composition: dict[str, float]            # итоговый оксидный состав массы, %
    normalized_fractions: dict[str, float]   # доли компонентов, приведённые к 100 %
    notes: list[str] = []


def shihta_calc(inp: ShihtaInput) -> ShihtaResult:
    if not inp.components:
        raise ValueError("Нужен хотя бы один компонент")

    total = sum(c.fraction for c in inp.components)
    if total <= 0:
        raise ValueError("Сумма долей компонентов должна быть > 0")

    # Приводим доли к 100 % (как в методике документа)
    norm = {c.name: round(c.fraction / total * 100.0, 2) for c in inp.components}

    composition: dict[str, float] = {}
    for c in inp.components:
        frac = c.fraction / total * 100.0
        for oxide, pct in c.oxides.items():
            composition[oxide] = composition.get(oxide, 0.0) + frac * pct / 100.0

    composition = {k: round(v, 2) for k, v in composition.items()}
    return ShihtaResult(
        composition=composition,
        normalized_fractions=norm,
        notes=["Метод — из документа «Расчёт состава шихты»: вклад = доля × оксид / 100."],
    )
