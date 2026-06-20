from datetime import datetime
from pydantic import BaseModel
from typing import Literal


# ─── WebSocket messages ───────────────────────────────────────────────

class WsIncoming(BaseModel):
    """Сообщение от клиента через WebSocket"""
    message: str
    agent: str = "orchestrator"  # целевой агент или 'orchestrator'
    session_id: str = "default"


class WsToken(BaseModel):
    """Стриминг-токен → клиент"""
    type: Literal["token"] = "token"
    content: str
    agent: str


class WsAgentStart(BaseModel):
    """Сигнал о том, что начал отвечать новый агент"""
    type: Literal["agent_start"] = "agent_start"
    agent: str
    display_name: str


class WsDone(BaseModel):
    """Ответ агента завершён"""
    type: Literal["done"] = "done"
    agent: str


class WsError(BaseModel):
    """Ошибка"""
    type: Literal["error"] = "error"
    message: str


# ─── REST ─────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    ok: bool
    chunks_added: int
    agent: str
    filename: str


class AgentInfo(BaseModel):
    id: str
    display_name: str
    description: str
    color: str
    icon: str
    builtin: bool = True


class HealthResponse(BaseModel):
    status: str
    agents: int
    collections: list[str]


# ─── Projects (память проектов) ───────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    industry: str = "ceramics"


class ProjectInfo(BaseModel):
    id: str
    name: str
    industry: str
    created_at: datetime


class ProjectMessageInfo(BaseModel):
    role: str
    agent: str
    content: str
    created_at: datetime


class ProjectDetail(ProjectInfo):
    messages: list[ProjectMessageInfo]


class MemoryNoteCreate(BaseModel):
    agent: str
    value: str


# ─── Экспорт документов ───────────────────────────────────────────────

class ExportRequest(BaseModel):
    project_id: str
    doc_type: Literal["docx", "xlsx", "pdf"]


# ─── Интеграция с Компас-3D (проксируется в kompas-connector) ──────────

class BuildingSpec(BaseModel):
    name: str
    width_m: float = 18.0
    length_m: float = 48.0


class KompasGenerateRequest(BaseModel):
    kind: Literal["foundation", "rectangle", "site_plan"] = "foundation"
    width_mm: float = 6000.0
    length_mm: float = 12000.0
    title: str = "План фундамента"
    project: str = ""
    designer: str = "AI Конструкторское бюро"
    buildings: list[BuildingSpec] = []


class KompasDesignRequest(BaseModel):
    """Бриф для генплана: Конструктор предложит состав корпусов, Компас отрисует."""
    brief: str = "кирпичный завод"
    project: str = ""
    title: str = "Генплан кирпичного завода"


# ─── Управление агентами и отраслями (admin UI) ───────────────────────

class IndustryCreate(BaseModel):
    id: str
    display_name: str


class AgentUpsert(BaseModel):
    display_name: str = ""
    description: str = ""
    color: str = ""
    icon: str = ""
    system_prompt: str = ""
    keywords: str = ""  # ключевые слова маршрутизации через запятую
