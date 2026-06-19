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
