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

from urllib.parse import quote

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from langchain_core.messages import HumanMessage

from config import settings
from agents.definitions import (
    AGENTS, get_agents, get_industry, list_industries, all_agent_ids, DEFAULT_INDUSTRY,
    load_customizations, _BUILTIN_INDUSTRIES,
)
from graph.graph import get_graph, reset_graph, BureauState, GRAPH_RECURSION_LIMIT
from knowledge.chroma import add_file, list_collections
from models.schemas import (
    UploadResponse, AgentInfo, HealthResponse,
    ProjectCreate, ProjectInfo, ProjectDetail, ProjectMessageInfo, MemoryNoteCreate,
    ExportRequest, KompasGenerateRequest, IndustryCreate, AgentUpsert,
)
from storage import db as storage
from export import build_document

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _node_to_agent(node: str) -> str | None:
    """
    Сопоставляет узел графа с агентом для стриминга. Управляющие узлы
    (роутер/диспетчер) возвращают None — у них нет «пузыря» в чате.
    """
    if node == "orchestrator_respond":
        return "orchestrator"
    if node == "norm_control_review":
        return "norm_control"
    if node in all_agent_ids():
        return node
    return None  # orchestrator_router, dispatch и прочие служебные


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
    await load_customizations()  # подтянуть кастомные отрасли/агентов из БД


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
    project = await storage.get_or_create_project(project_id)
    industry = project.industry or DEFAULT_INDUSTRY

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

                agent_info = get_agents(industry).get(memory_agent, {})
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
                "industry": industry,
                "plan": [],
                "step": 0,
                "iteration": 0,
                "review": False,
                "review_feedback": "",
                "done": False,
            }

            # Стримим ответ через astream_events.
            # У каждого агента — свой «пузырь»; в межагентном режиме их несколько
            # (включая итерации доработки). Сохраняем все по завершении.
            bubbles: list[dict] = []      # [{"agent": id, "content": str}, ...]
            current: dict | None = None   # текущий пузырь

            try:
                async for event in graph.astream_events(
                    input_state,
                    version="v2",
                    config={"recursion_limit": GRAPH_RECURSION_LIMIT},
                ):
                    kind = event["event"]
                    meta = event.get("metadata", {})
                    node = meta.get("langgraph_node", "")
                    agent = _node_to_agent(node)
                    if agent is None:
                        continue  # служебные узлы (роутер/диспетчер) не стримим

                    # Начало ответа агента — новый пузырь
                    if kind == "on_chat_model_start":
                        current = {"agent": agent, "content": ""}
                        bubbles.append(current)
                        agent_info = AGENTS.get(agent, {})
                        await websocket.send_text(json.dumps({
                            "type": "agent_start",
                            "agent": agent,
                            "display_name": agent_info.get("display_name", agent),
                        }, ensure_ascii=False))

                    # Токены текущего агента
                    elif kind == "on_chat_model_stream" and current is not None:
                        chunk = event["data"].get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            current["content"] += chunk.content
                            await websocket.send_text(json.dumps({
                                "type": "token",
                                "content": chunk.content,
                                "agent": agent,
                            }, ensure_ascii=False))

                # Сохраняем в персистентную историю проекта ДО сигнала «done»,
                # чтобы запись не потерялась, если клиент отключится сразу после done.
                await storage.add_message(project_id, "human", selected_agent, user_message)
                for b in bubbles:
                    if b["content"].strip():
                        await storage.add_message(project_id, "ai", b["agent"], b["content"])

                # Сигнал конца
                last_agent = bubbles[-1]["agent"] if bubbles else selected_agent
                await websocket.send_text(json.dumps({
                    "type": "done",
                    "agent": last_agent,
                }, ensure_ascii=False))

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
    industry: str = Form(DEFAULT_INDUSTRY),
):
    """Загрузить документ в базу знаний агента указанной отрасли."""
    if agent not in get_agents(industry):
        raise HTTPException(status_code=400, detail=f"Неизвестный агент «{agent}» в отрасли «{industry}»")

    allowed = {".txt", ".pdf", ".docx", ".xlsx", ".xlsm"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Поддерживаемые форматы: {', '.join(allowed)}",
        )

    # Сохраняем файл (имя с отраслью и агентом — чтобы не было коллизий)
    save_path = Path(settings.uploads_path) / f"{industry}_{agent}_{file.filename}"
    content = await file.read()
    save_path.write_bytes(content)

    # Добавляем в базу знаний отрасли
    try:
        chunks = await add_file(str(save_path), agent, industry)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return UploadResponse(
        ok=True,
        chunks_added=chunks,
        agent=agent,
        filename=file.filename or "",
    )


# ─── REST: industries & agents ────────────────────────────────────────

@app.get("/api/industries")
async def get_industries():
    """Список отраслей платформы."""
    return list_industries()


@app.get("/api/agents", response_model=list[AgentInfo])
async def list_agents(industry: str = DEFAULT_INDUSTRY):
    """Агенты указанной отрасли (по умолчанию — отрасль по умолчанию)."""
    return [
        AgentInfo(
            id=k,
            display_name=v["display_name"],
            description=v["description"],
            color=v["color"],
            icon=v["icon"],
            builtin=_is_builtin_agent(industry, k),
        )
        for k, v in get_agents(industry).items()
    ]


@app.get("/api/agents/{industry}/{agent_id}")
async def get_agent_detail(industry: str, agent_id: str):
    """Полное описание агента (включая system_prompt и keywords) — для формы редактирования."""
    agents = get_agents(industry)
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Агент не найден")
    a = agents[agent_id]
    from agents.definitions import routing_keywords as _kw
    keywords = ", ".join(_kw(industry).get(agent_id, []))
    return {
        "id": agent_id,
        "display_name": a["display_name"],
        "description": a.get("description", ""),
        "color": a.get("color", ""),
        "icon": a.get("icon", ""),
        "system_prompt": a.get("system_prompt", ""),
        "keywords": keywords,
        "builtin": _is_builtin_agent(industry, agent_id),
    }


# ─── REST: управление агентами и отраслями (admin UI) ─────────────────

async def _refresh_registry() -> None:
    """Перечитать кэш кастомизаций и пересобрать граф под новый набор агентов."""
    await load_customizations()
    reset_graph()


def _is_builtin_agent(industry: str, agent_id: str) -> bool:
    return agent_id in _BUILTIN_INDUSTRIES.get(industry, {}).get("agents", {})


@app.post("/api/industries")
async def create_industry(payload: IndustryCreate):
    """Создать кастомную отрасль (с базовым оркестратором, чтобы была работоспособна)."""
    industry_id = payload.id.strip().lower()
    if not industry_id.isidentifier():
        raise HTTPException(status_code=400, detail="id отрасли: латиница/цифры/подчёркивание")
    if industry_id in _BUILTIN_INDUSTRIES:
        raise HTTPException(status_code=400, detail="Такая отрасль уже встроена")
    await storage.upsert_custom_industry(industry_id, payload.display_name.strip() or industry_id)
    # базовый оркестратор, чтобы отрасль сразу могла вести диалог
    await storage.upsert_agent_override(industry_id, "orchestrator", {
        "display_name": "Главный конструктор",
        "description": "Оркестратор · координирует работу бюро",
        "color": "#58A6FF", "icon": "sitemap",
        "system_prompt": f"Ты Главный конструктор бюро (отрасль «{payload.display_name}»). "
                         "Принимай задачи, отвечай сам или распределяй между специалистами. Отвечай на русском.",
        "is_custom": True,
    })
    await _refresh_registry()
    return {"ok": True, "id": industry_id}


@app.delete("/api/industries/{industry_id}")
async def delete_industry(industry_id: str):
    """Удалить кастомную отрасль (встроенные не удаляются)."""
    if industry_id in _BUILTIN_INDUSTRIES:
        raise HTTPException(status_code=400, detail="Встроенную отрасль удалить нельзя")
    await storage.delete_custom_industry(industry_id)
    await _refresh_registry()
    return {"ok": True}


@app.put("/api/agents/{industry}/{agent_id}")
async def upsert_agent(industry: str, agent_id: str, payload: AgentUpsert):
    """Создать или изменить агента отрасли (правка встроенного или новый кастомный)."""
    agent_id = agent_id.strip().lower()
    if not agent_id.isidentifier():
        raise HTTPException(status_code=400, detail="id агента: латиница/цифры/подчёркивание")
    if industry not in _BUILTIN_INDUSTRIES and industry not in [i["id"] for i in list_industries()]:
        raise HTTPException(status_code=404, detail="Отрасль не найдена")

    fields = payload.model_dump()
    fields["is_custom"] = not _is_builtin_agent(industry, agent_id)
    fields["deleted"] = False
    await storage.upsert_agent_override(industry, agent_id, fields)
    await _refresh_registry()
    return {"ok": True, "industry": industry, "agent_id": agent_id, "custom": fields["is_custom"]}


@app.delete("/api/agents/{industry}/{agent_id}")
async def delete_agent(industry: str, agent_id: str):
    """
    Кастомного агента — удалить насовсем; встроенного — сбросить к стандарту
    (снять кастомизацию). В обоих случаях убираем строку оверрайда.
    """
    if agent_id == "orchestrator":
        raise HTTPException(status_code=400, detail="Оркестратора удалить нельзя")
    await storage.delete_agent_override(industry, agent_id)
    await _refresh_registry()
    return {"ok": True}


# ─── REST: health ─────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
async def health():
    collections = list_collections()
    return HealthResponse(
        status="ok",
        agents=len(all_agent_ids()),
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


# ─── REST: экспорт документов (DOCX / XLSX / PDF) ─────────────────────

@app.post("/api/export")
async def export_document(payload: ExportRequest):
    """Сформировать документ по проекту и вернуть файл на скачивание."""
    try:
        content, mime, filename = await build_document(payload.project_id, payload.doc_type)
    except LookupError:
        raise HTTPException(status_code=404, detail="Проект не найден")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # RFC 5987 — корректное имя файла с кириллицей
    quoted = quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}"
    }
    return Response(content=content, media_type=mime, headers=headers)


# ─── REST: интеграция с Компас-3D (прокси к kompas-connector) ──────────

_KOMPAS_DOWN = (
    "Коннектор Компас-3D недоступен. Запустите сервис kompas-connector "
    "на Windows-машине с установленным Компас-3D (см. kompas-connector/README.md). "
    "Остальная платформа работает без него."
)


@app.get("/api/kompas/status")
async def kompas_status():
    """Доступность коннектора Компас-3D. Не падает, если коннектор не запущен."""
    import httpx
    url = settings.kompas_connector_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{url}/health")
            r.raise_for_status()
            data = r.json()
        return {"connector_up": True, **data}
    except Exception as e:
        return {"connector_up": False, "kompas_available": False, "detail": _KOMPAS_DOWN, "error": str(e)}


@app.post("/api/kompas/read")
async def kompas_read(file: UploadFile = File(...)):
    """Проксировать разбор чертежа .cdw/.frw в коннектор."""
    import httpx
    url = settings.kompas_connector_url.rstrip("/")
    content = await file.read()
    files = {"file": (file.filename or "drawing.cdw", content,
                      file.content_type or "application/octet-stream")}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{url}/read", files=files)
    except Exception:
        raise HTTPException(status_code=503, detail=_KOMPAS_DOWN)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code,
                            detail=_connector_error(r))
    return r.json()


@app.post("/api/kompas/generate")
async def kompas_generate(payload: KompasGenerateRequest):
    """Проксировать генерацию чертежа в коннектор и вернуть .cdw."""
    import httpx
    url = settings.kompas_connector_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{url}/generate", json=payload.model_dump())
    except Exception:
        raise HTTPException(status_code=503, detail=_KOMPAS_DOWN)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=_connector_error(r))
    headers = {"Content-Disposition": 'attachment; filename="drawing.cdw"'}
    return Response(content=r.content, media_type="application/octet-stream", headers=headers)


def _connector_error(resp) -> str:
    """Достать сообщение об ошибке из ответа коннектора."""
    try:
        return resp.json().get("detail", resp.text)
    except Exception:
        return resp.text or "Ошибка коннектора Компас-3D"


# ─── Entrypoint ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload,
    )
