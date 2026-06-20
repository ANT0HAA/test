"""Схемы запросов/ответов сервиса-коннектора Компас-3D."""
from typing import Literal
from pydantic import BaseModel


class HealthResponse(BaseModel):
    ok: bool
    kompas_available: bool
    version: str | None = None
    detail: str = ""


class SpecRow(BaseModel):
    """Строка спецификации/ведомости из чертежа."""
    position: str = ""
    designation: str = ""   # обозначение
    name: str = ""          # наименование
    qty: str = ""           # количество
    note: str = ""          # примечание


class TextEntity(BaseModel):
    """Текстовая надпись на чертеже."""
    text: str
    x: float = 0.0
    y: float = 0.0


class DimensionEntity(BaseModel):
    """Размер на чертеже."""
    kind: str               # тип размера (линейный/угловой/...)
    value: float = 0.0      # измеренное значение
    text: str = ""          # отображаемый текст размера


class ReadResult(BaseModel):
    """Результат разбора .cdw/.frw."""
    filename: str
    doc_type: str = ""                  # тип документа (чертёж/фрагмент)
    sheet_count: int = 0
    texts: list[TextEntity] = []
    dimensions: list[DimensionEntity] = []
    specification: list[SpecRow] = []


class BuildingSpec(BaseModel):
    """Корпус/здание для генплана."""
    name: str
    width_m: float = 18.0
    length_m: float = 48.0


class GenerateRequest(BaseModel):
    """Параметры генерации простого чертежа."""
    kind: Literal["foundation", "rectangle", "site_plan"] = "foundation"
    width_mm: float = 6000.0            # размер по X
    length_mm: float = 12000.0          # размер по Y
    title: str = "План фундамента"      # наименование изделия (в штамп)
    project: str = ""                   # обозначение/проект (в штамп)
    designer: str = "AI Конструкторское бюро"
    buildings: list[BuildingSpec] = []  # для kind=site_plan: свой состав корпусов
