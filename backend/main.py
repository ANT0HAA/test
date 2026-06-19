"""
FastAPI бэкенд AI Конструкторского бюро.

Endpoints:
  WS  /ws/{session_id}       — стриминг чата
  POST /api/upload            — загрузка документов в базу знаний
  GET  /api/agents            — список агентов
  GET  /api/health            — статус платформы
  DELETE /api/session/{id}   — сбросить историю сессии
"""
import os
import re
import json
import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage

from config import settings
from agents.definitions import AGENTS
from graph.graph import get_graph, BureauState
from knowledge.chroma import add_file, list_collections
from models.schemas import (
    UploadResponse, AgentInfo, HealthResponse,
    ProjectCreate, ProjectInfo, ProjectDetail, ProjectMessageInfo, MemoryNoteCreate,
)
from storage import db as storage

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ─── App setup ────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Конструкторское бюро",
    description="Мультиагентная платформа для проектирования керамических заводов",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)

MAX_HISTORY = 40  # максимум сообщений из истории проекта, подаваемых в контекст модели

# Команда сохранения решения в память проекта: «запомни: <текст>»
_REMEMBER_RE = re.compile(r"^запомни\s*[:\-]\s*(.+)", re.IGNORECASE | re.DOTALL)


@app.on_event("startup")
async def on_startup() -> None:
    await storage.init_db()


# ─── WebSocket manager ────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, ws: WebSocket, session_id: str):
        await ws.accept()
        self.active[session_id] = ws
        log.info("WS connected: %s", session_id)

    def disconnect(self, session_id: str):
        self.active.pop(session_id, None)
        log.info("WS disconnected: %s", session_id)

    async def send(self, session_id: str, data: dict):
        ws = self.active.get(session_id)
        if ws:
            await ws.send_text(json.dumps(data, ensure_ascii=False))


manager = ConnectionManager()


# ─── WebSocket endpoint ───────────────────────────────────────────────

@app.websocket("/ws/{project_id}")
async def websocket_chat(websocket: WebSocket, project_id: str):
    await manager.connect(websocket, project_id)
    graph = get_graph()

    # Проект может быть создан заранее через REST либо лениво (для обратной совместимости)
    await storage.get_or_create_project(project_id)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            user_message: str = data.get("message", "").strip()
            selected_agent: str = data.get("agent", "orchestrator")

            if not user_message:
                continue

            # Команда «запомни: <решение>» — сохраняет заметку в память проекта без вызова LLM
            remember_match = _REMEMBER_RE.match(user_message)
            if remember_match:
                note = remember_match.group(1).strip()
                memory_agent = selected_agent if selected_agent != "orchestrator" else "orchestrator"
                await storage.add_memory(project_id, memory_agent, note)

                confirmation = f"Запомнил по проекту: «{note}»"
                await storage.add_message(project_id, "human", selected_agent, user_message)
                await storage.add_message(project_id, "ai", memory_agent, confirmation)

                agent_info = AGENTS.get(memory_agent, {})
                await websocket.send_text(json.dumps({
                    "type": "agent_start",
                    "agent": memory_agent,
                    "display_name": agent_info.get("display_name", memory_agent),
                }, ensure_ascii=False))
                await websocket.send_text(json.dumps({
                    "type": "token", "content": confirmation, "agent": memory_agent,
                }, ensure_ascii=False))
                await websocket.send_text(json.dumps({
                    "type": "done", "agent": memory_agent,
                }, ensure_ascii=False))
                continue

            history = await storage.get_history(project_id, limit=MAX_HISTORY)

            # Формируем стартовое состояние
            input_state: BureauState = {
                "messages": history + [HumanMessage(content=user_message)],
                "direct_agent": selected_agent if selected_agent != "orchestrator" else None,
                "active_agent": selected_agent,
                "delegated_task": "",
                "action": "",
                "project_id": project_id,
            }

            # Стримим ответ через astream_events
            full_response = ""
            current_agent = selected_agent

            try:
                async for event in graph.astream_events(input_state, version="v2"):
                    kind = event["event"]
                    meta = event.get("metadata", {})
                    node = meta.get("langgraph_node", "")

                    # Сигнал о начале ответа агента
                    if kind == "on_node_start" and node not in ("orchestrator_router",):
                        current_agent = node.replace("_respond", "")
                        agent_info = AGENTS.get(current_agent, {})
                        await websocket.send_text(json.dumps({
                            "type": "agent_start",
                            "agent": current_agent,
                            "display_name": agent_info.get("display_name", current_agent),
                        }, ensure_ascii=False))

                    # Стриминг токенов (только не из роутера)
                    elif kind == "on_chat_model_stream" and node != "orchestrator_router":
                        chunk = event["data"].get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            full_response += chunk.content
                            await websocket.send_text(json.dumps({
                                "type": "token",
                                "content": chunk.content,
                                "agent": node.replace("_respond", ""),
                            }, ensure_ascii=False))

                # Сигнал конца
                await websocket.send_text(json.dumps({
                    "type": "done",
                    "agent": current_agent,
                }, ensure_ascii=False))

                # Сохраняем в персистентную историю проекта
                await storage.add_message(project_id, "human", selected_agent, user_message)
                await storage.add_message(project_id, "ai", current_agent, full_response)

            except Exception as e:
                log.exception("Graph error in project %s", project_id)
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Ошибка агента: {str(e)}",
                }, ensure_ascii=False))

    except WebSocketDisconnect:
        manager.disconnect(project_id)
    except Exception as e:
        log.exception("WS error: %s", e)
        manager.disconnect(project_id)


# ─── REST: file upload ────────────────────────────────────────────────

@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    agent: str = Form("orchestrator"),
):
    """Загрузить документ в базу знаний указанного агента."""
    if agent not in AGENTS:
        raise HTTPException(status_code=400, detail=f"Неизвестный агент: {agent}")

    allowed = {".txt", ".pdf", ".docx", ".doc"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Поддерживаемые форматы: {', '.join(allowed)}",
        )

    # Сохраняем файл
    save_path = Path(settings.uploads_path) / f"{agent}_{file.filename}"
    content = await file.read()
    save_path.write_bytes(content)

    # Добавляем в базу знаний
    try:
        chunks = await add_file(str(save_path), agent)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return UploadResponse(
        ok=True,
        chunks_added=chunks,
        agent=agent,
        filename=file.filename or "",
    )


# ─── REST: agents list ────────────────────────────────────────────────

@app.get("/api/agents", response_model=list[AgentInfo])
async def get_agents():
    return [
        AgentInfo(
            id=k,
            display_name=v["display_name"],
            description=v["description"],
            color=v["color"],
            icon=v["icon"],
        )
        for k, v in AGENTS.items()
    ]


# ─── REST: health ─────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
async def health():
    collections = list_collections()
    return HealthResponse(
        status="ok",
        agents=len(AGENTS),
        collections=collections,
    )


@app.get("/api/llm-status")
async def llm_status():
    """Проверка доступности LLM-провайдера (для Ollama — что модель скачана)."""
    provider = settings.llm_provider.lower()
    if provider != "ollama":
        return {"provider": provider, "reachable": True, "model": settings.llm_model}

    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            r.raise_for_status()
            tags = [m["name"] for m in r.json().get("models", [])]
        model_ready = any(
            t == settings.llm_model or t.split(":")[0] == settings.llm_model.split(":")[0]
            for t in tags
        )
        return {
            "provider": "ollama",
            "reachable": True,
            "model": settings.llm_model,
            "model_pulled": model_ready,
            "available_models": tags,
            "hint": None if model_ready
                    else f"Модель не скачана. Выполните: ollama pull {settings.llm_model}",
        }
    except Exception as e:
        return {
            "provider": "ollama",
            "reachable": False,
            "model": settings.llm_model,
            "error": str(e),
            "hint": f"Ollama недоступен по {settings.ollama_base_url}. "
                    "Запустите Ollama (`ollama serve`) и проверьте OLLAMA_BASE_URL.",
        }


# ─── REST: clear session (история чата проекта) ───────────────────────

@app.delete("/api/session/{session_id}")
async def clear_session(session_id: str):
    await storage.clear_messages(session_id)
    return {"ok": True, "session_id": session_id}


# ─── REST: projects (память проектов) ──────────────────────────────────

@app.post("/api/projects", response_model=ProjectInfo)
async def create_project(payload: ProjectCreate):
    project = await storage.create_project(payload.name, payload.industry)
    return ProjectInfo(
        id=project.id, name=project.name, industry=project.industry, created_at=project.created_at,
    )


@app.get("/api/projects", response_model=list[ProjectInfo])
async def get_projects():
    projects = await storage.list_projects()
    return [
        ProjectInfo(id=p.id, name=p.name, industry=p.industry, created_at=p.created_at)
        for p in projects
    ]


@app.get("/api/projects/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str):
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    rows = await storage.get_messages(project_id)
    return ProjectDetail(
        id=project.id, name=project.name, industry=project.industry, created_at=project.created_at,
        messages=[
            ProjectMessageInfo(role=r.role, agent=r.agent, content=r.content, created_at=r.created_at)
            for r in rows
        ],
    )


@app.post("/api/projects/{project_id}/memory")
async def add_project_memory(project_id: str, payload: MemoryNoteCreate):
    if not await storage.get_project(project_id):
        raise HTTPException(status_code=404, detail="Проект не найден")
    await storage.add_memory(project_id, payload.agent, payload.value)
    return {"ok": True}


# ─── Entrypoint ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload,
    )
