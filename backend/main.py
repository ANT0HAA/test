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

from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException,
    Depends, Header,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from langchain_core.messages import HumanMessage

from config import settings
from agents.definitions import (
    AGENTS, get_agents, get_industry, list_industries, all_agent_ids, DEFAULT_INDUSTRY,
    load_customizations, _BUILTIN_INDUSTRIES,
)
from graph.graph import get_graph, reset_graph, BureauState, GRAPH_RECURSION_LIMIT
from knowledge.chroma import (
    add_file, add_project_file, add_project_text, list_collections, collection_stats,
    delete_project_collection, list_project_materials, update_project_material,
    delete_project_material, delete_project_source,
)
from models.schemas import (
    UploadResponse, AgentInfo, HealthResponse,
    ProjectCreate, ProjectInfo, ProjectDetail, ProjectMessageInfo, MemoryNoteCreate,
    ExportRequest, KompasGenerateRequest, KompasDesignRequest, BuildingSpec,
    IndustryCreate, AgentUpsert,
    InputField, InputsSchemaRequest, InputsSchemaResponse, ProjectInputsSubmit,
)
from pydantic import BaseModel
from storage import db as storage
from export import build_document
from calc import (
    ProductionInput, ProductionResult, production_program,
    DryerInput, DryerResult, dryer_calc,
    EquipmentInput, EquipmentResult, select_equipment,
    ElectricalInput, ElectricalResult, electrical_load,
    AreasInput, AreasResult, estimate_areas,
    EstimateInput, EstimateResult, cost_estimate,
    ShihtaInput, ShihtaResult, shihta_calc,
    buildings_from_areas, parse_capacity, production_program,
    LabInput,
)

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


_THINK_CLOSED = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _visible_text(raw: str) -> str:
    """
    Убрать «размышления» модели — в UI идёт только ответ.
    qwen3 через Ollama часто выдаёт рассуждение БЕЗ открывающего <think>, лишь с
    закрывающим </think> в конце; поэтому всё до последнего </think> отбрасываем.
    """
    low = raw.lower()
    j = low.rfind("</think>")
    if j != -1:
        return raw[j + len("</think>"):].lstrip()
    # парные блоки и незакрытый явный <think>
    s = _THINK_CLOSED.sub("", raw)
    i = s.lower().find("<think>")
    if i != -1:
        return ""           # рассуждение ещё идёт — пока ничего не показываем
    return s.lstrip()


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


# ─── Авторизация (логин/пароль + роли) ────────────────────────────────
import security
from datetime import timedelta, datetime as _dt, timezone as _tz

SESSION_TTL_DAYS = 30


class RegisterBody(BaseModel):
    username: str
    password: str


class LoginBody(BaseModel):
    username: str
    password: str


class CreateUserBody(BaseModel):
    username: str
    password: str
    role: str = "user"


def _user_info(user) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role}


async def get_current_user(authorization: str = Header(default="")):
    """Текущий пользователь по токену из заголовка Authorization: Bearer <token>."""
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    user = await storage.get_session_user(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="Требуется вход в систему")
    return user


async def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    return user


async def project_access(project_id: str, user=Depends(get_current_user)):
    """Проект с проверкой доступа: владелец, админ или «ничей» legacy-проект."""
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    if project.owner_id and project.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Нет доступа к проекту")
    return project


@app.get("/api/auth/me")
async def auth_me(user=Depends(get_current_user)):
    return _user_info(user)


@app.post("/api/auth/register")
async def auth_register(body: RegisterBody):
    """Регистрация. Первый зарегистрированный пользователь становится администратором."""
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(status_code=400, detail="Укажите логин и пароль")
    if await storage.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="Пользователь с таким логином уже есть")
    role = "admin" if await storage.count_users() == 0 else "user"
    user = await storage.create_user(username, security.hash_password(body.password), role)
    token = security.new_token()
    await storage.create_session(user.id, token,
                                 _dt.now(_tz.utc) + timedelta(days=SESSION_TTL_DAYS))
    return {"token": token, "user": _user_info(user)}


@app.post("/api/auth/login")
async def auth_login(body: LoginBody):
    user = await storage.get_user_by_username(body.username.strip())
    if not user or not security.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = security.new_token()
    await storage.create_session(user.id, token,
                                 _dt.now(_tz.utc) + timedelta(days=SESSION_TTL_DAYS))
    return {"token": token, "user": _user_info(user)}


@app.post("/api/auth/logout")
async def auth_logout(authorization: str = Header(default="")):
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if token:
        await storage.delete_session(token)
    return {"ok": True}


# ─── Управление пользователями (только администратор) ──────────────────

@app.get("/api/users")
async def list_users(_: object = Depends(require_admin)):
    return [_user_info(u) for u in await storage.list_users()]


@app.post("/api/users")
async def create_user_admin(body: CreateUserBody, _: object = Depends(require_admin)):
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(status_code=400, detail="Укажите логин и пароль")
    if await storage.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="Пользователь с таким логином уже есть")
    role = body.role if body.role in ("admin", "user") else "user"
    user = await storage.create_user(username, security.hash_password(body.password), role)
    return _user_info(user)


@app.delete("/api/users/{user_id}")
async def delete_user_admin(user_id: str, admin=Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    ok = await storage.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {"ok": True}

MAX_HISTORY = 40  # максимум сообщений из истории проекта, подаваемых в контекст модели

# Команда сохранения решения в память проекта: «запомни: <текст>»
_REMEMBER_RE = re.compile(r"^запомни\s*[:\-]\s*(.+)", re.IGNORECASE | re.DOTALL)

# Запрос на проектирование — по нему бюро может уточнить недостающие исходные данные.
_DESIGN_TRIGGER_RE = re.compile(
    r"спроектир|запроектир|рассчита|посчита|разработа|построй|сделай\s+проект|"
    r"генплан|завод|производств|цех|кирпич|керам|линию|подбери\s+оборуд",
    re.IGNORECASE,
)

# Минимально необходимые исходные данные, без которых проектирование бессмысленно.
_REQUIRED_INPUT_KEYS = ("product", "capacity")


def _missing_required_fields(inputs: dict | None) -> list[InputField]:
    """Какие из обязательных исходных данных ещё не заданы (поля для формы уточнения)."""
    have = {k for k, v in (inputs or {}).items() if str(v).strip()}
    by_key = {f.key: f for f in _DEFAULT_INPUT_FIELDS}
    return [by_key[k] for k in _REQUIRED_INPUT_KEYS if k not in have and k in by_key]


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
    # Авторизация по токену из query (?token=...): чат доступен только владельцу/админу
    token = websocket.query_params.get("token", "")
    user = await storage.get_session_user(token) if token else None
    if not user:
        await websocket.close(code=4401)
        return
    existing = await storage.get_project(project_id)
    if existing and existing.owner_id and existing.owner_id != user.id and user.role != "admin":
        await websocket.close(code=4403)
        return

    await manager.connect(websocket, project_id)
    graph = get_graph()

    # Проект может быть создан заранее через REST либо лениво (для обратной совместимости)
    project = await storage.get_or_create_project(project_id)
    if project.owner_id is None:
        # Закрепить «ничей» проект за первым подключившимся пользователем
        await storage.assign_project_owner(project_id, user.id)
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

            # Уточняющая форма: если это запрос на проектирование, а обязательных
            # исходных данных не хватает — бюро запрашивает их окошком и ждёт ответа
            # (клиент дозаполнит и пришлёт сообщение повторно с skip_clarify=true).
            if not data.get("skip_clarify") and _DESIGN_TRIGGER_RE.search(user_message):
                inputs = await storage.get_project_inputs(project_id)
                missing = _missing_required_fields(inputs)
                if missing:
                    await websocket.send_text(json.dumps({
                        "type": "clarify",
                        "message": user_message,
                        "agent": selected_agent,
                        "fields": [f.model_dump() for f in missing],
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
                        current = {"agent": agent, "raw": "", "content": ""}
                        bubbles.append(current)
                        agent_info = AGENTS.get(agent, {})
                        await websocket.send_text(json.dumps({
                            "type": "agent_start",
                            "agent": agent,
                            "display_name": agent_info.get("display_name", agent),
                        }, ensure_ascii=False))

                    # Токены текущего агента (без «размышлений»: стримим только видимую часть)
                    elif kind == "on_chat_model_stream" and current is not None:
                        chunk = event["data"].get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            current["raw"] += chunk.content
                            visible = _visible_text(current["raw"])
                            delta = visible[len(current["content"]):]
                            if delta:
                                current["content"] = visible
                                await websocket.send_text(json.dumps({
                                    "type": "token",
                                    "content": delta,
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


@app.get("/api/knowledge")
async def knowledge_stats(industry: str = DEFAULT_INDUSTRY):
    """База знаний отрасли по агентам: число фрагментов и файлы-источники."""
    return {aid: collection_stats(aid, industry) for aid in get_agents(industry)}


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


# ─── REST: расчётное ядро (детерминированные расчёты) ─────────────────

@app.post("/api/calc/production", response_model=ProductionResult)
async def calc_production(payload: ProductionInput):
    """Производственная программа и потребность ресурсов (по нормам из документа)."""
    try:
        return production_program(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/calc/dryer", response_model=DryerResult)
async def calc_dryer(payload: DryerInput):
    """Теплотехнический расчёт сушила (расход воздуха/теплоносителя)."""
    try:
        return dryer_calc(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/calc/equipment", response_model=EquipmentResult)
async def calc_equipment(payload: EquipmentInput):
    """Подбор основного оборудования по производительности."""
    try:
        return select_equipment(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/calc/electrical", response_model=ElectricalResult)
async def calc_electrical(payload: ElectricalInput):
    """Электрические нагрузки и подбор трансформатора."""
    try:
        return electrical_load(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/calc/areas", response_model=AreasResult)
async def calc_areas(payload: AreasInput):
    """Оценка площадей корпусов."""
    try:
        return estimate_areas(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/calc/estimate", response_model=EstimateResult)
async def calc_estimate(payload: EstimateInput):
    """Смета себестоимости (переменные затраты)."""
    try:
        return cost_estimate(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/calc/shihta", response_model=ShihtaResult)
async def calc_shihta(payload: ShihtaInput):
    """Оксидный состав массы из состава шихты."""
    try:
        return shihta_calc(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/calc/lab")
async def calc_lab(payload: LabInput):
    """Лабораторно-технологический расчёт по сырью (усреднение, отощитель,
    чувствительность, штабель, питатели, схема формования)."""
    from calc import lab_report
    try:
        return lab_report(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class _OxidesLLM(BaseModel):
    components: list[dict] = []   # [{name, fraction, oxides:{SiO2:..}}]
    summary: str = ""


@app.post("/api/projects/{project_id}/analyze-lab")
async def analyze_lab(project_id: str, _=Depends(project_access)):
    """Извлечь хим. состав сырья из приложенного отчёта лаборатории (LLM) и,
    при наличии данных, посчитать состав шихты. Пусто, если отчёта нет."""
    from knowledge.chroma import project_search
    lab_text = project_search("химический состав глины оксиды влажность пластичность", project_id)
    if not lab_text:
        return {"found": False, "detail": "Нет материалов проекта (приложите отчёт лаборатории)."}
    try:
        from graph.graph import _llm
        from langchain_core.messages import SystemMessage, HumanMessage
        system = (
            "Ты — технолог. Из отчёта лаборатории извлеки сырьевые компоненты и их "
            "оксидный состав (%). Верни СТРОГО JSON: components=[{name, fraction, "
            "oxides:{SiO2, Al2O3, Fe2O3, CaO, MgO, ...}}], summary — кратко о пригодности."
        )
        llm = _llm(streaming=False).with_structured_output(_OxidesLLM)
        res: _OxidesLLM = await llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=lab_text[:6000])])
        comps = [c for c in res.components if c.get("name")]
        shihta = None
        valid = [ShihtaInput.model_validate({"components": comps})] if comps else []
        if valid and any(c.get("oxides") for c in comps):
            try:
                shihta = shihta_calc(valid[0]).model_dump()
            except Exception:
                shihta = None
        return {"found": True, "components": comps, "summary": res.summary, "shihta": shihta}
    except Exception as e:
        log.info("Разбор лаборатории не удался", exc_info=True)
        return {"found": True, "components": [], "summary": "", "error": str(e)[:120]}


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
async def clear_session(session_id: str, user=Depends(get_current_user)):
    project = await storage.get_project(session_id)
    if project and project.owner_id and project.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Нет доступа к проекту")
    await storage.clear_messages(session_id)
    return {"ok": True, "session_id": session_id}


# ─── REST: projects (память проектов) ──────────────────────────────────

@app.post("/api/projects", response_model=ProjectInfo)
async def create_project(payload: ProjectCreate, user=Depends(get_current_user)):
    project = await storage.create_project(payload.name, payload.industry, owner_id=user.id)
    return ProjectInfo(
        id=project.id, name=project.name, industry=project.industry, created_at=project.created_at,
    )


@app.get("/api/projects", response_model=list[ProjectInfo])
async def get_projects(user=Depends(get_current_user)):
    # Админ видит все проекты, обычный пользователь — свои и «ничьи» (legacy)
    owner = None if user.role == "admin" else user.id
    projects = await storage.list_projects(owner_id=owner)
    return [
        ProjectInfo(id=p.id, name=p.name, industry=p.industry, created_at=p.created_at)
        for p in projects
    ]


@app.get("/api/projects/{project_id}", response_model=ProjectDetail)
async def get_project(project=Depends(project_access)):
    project_id = project.id
    rows = await storage.get_messages(project_id)
    return ProjectDetail(
        id=project.id, name=project.name, industry=project.industry, created_at=project.created_at,
        messages=[
            ProjectMessageInfo(role=r.role, agent=r.agent, content=r.content, created_at=r.created_at)
            for r in rows
        ],
    )


# Минимальный набор: ТОЛЬКО то, без чего непонятна цель проекта.
# Всё остальное (хим. состав, нормы ввода, режимы, оборудование, энергию, площади и т.д.)
# бюро выводит само из отчётов лаборатории и расчётов.
_DEFAULT_INPUT_FIELDS = [
    InputField(key="product", label="Что проектируем (продукция)", type="select",
               options=["рядовой кирпич", "облицовочный кирпич", "клинкерный кирпич",
                        "поризованный кирпич/камень"]),
    InputField(key="capacity", label="Целевой объём производства", type="text",
               placeholder="напр. 30000 шт/смену или 60 млн шт/год"),
    InputField(key="fuel", label="Топливо (если известно)", type="select",
               options=["природный газ", "иное", "не определено"]),
    InputField(key="site", label="Участок (если известно)", type="text",
               placeholder="размеры/ограничения площадки, необязательно"),
]


class _FieldLLM(BaseModel):
    key: str
    label: str
    type: str = "text"
    unit: str = ""
    options: list[str] = []


class _FieldsLLM(BaseModel):
    fields: list[_FieldLLM] = []


@app.post("/api/projects/{project_id}/inputs-schema", response_model=InputsSchemaResponse)
async def inputs_schema(project_id: str, payload: InputsSchemaRequest, _=Depends(project_access)):
    """Какие исходные данные запросить у пользователя (поля формы).
    Оркестратор предлагает поля по брифу; при сбое — курируемый набор."""
    if payload.brief.strip():
        try:
            from graph.graph import _llm
            from langchain_core.messages import SystemMessage, HumanMessage
            system = (
                "Ты — Главный конструктор. Система проектирует завод АВТОМАТИЧЕСКИ и сама "
                "выводит параметры (хим. состав сырья — из отчётов лаборатории; нормы ввода "
                "добавок, режимы сушки/обжига, подбор оборудования, энергопотребление, площади "
                "и т.д. — рассчитывает). Перечисли ТОЛЬКО те исходные данные, без которых "
                "НЕВОЗМОЖНО понять цель и тип результата (обычно 2–4 поля: вид продукции, "
                "объём производства, опц. топливо/участок). НЕ включай то, что можно посчитать "
                "или взять из отчёта лаборатории. Для каждого поля: key (лат.), label (рус.), "
                "type (text/number/select), unit, options. Ответь СТРОГО JSON."
            )
            llm = _llm(streaming=False).with_structured_output(_FieldsLLM)
            res: _FieldsLLM = await llm.ainvoke(
                [SystemMessage(content=system), HumanMessage(content=payload.brief)]
            )
            fields = [
                InputField(key=f.key.strip(), label=f.label.strip(),
                           type=f.type if f.type in ("text", "number", "select") else "text",
                           unit=f.unit, options=f.options)
                for f in res.fields if f.key and f.label
            ][:12]
            if fields:
                return InputsSchemaResponse(fields=fields)
        except Exception:
            log.info("Схема полей через LLM не получена — курируемый набор", exc_info=True)
    return InputsSchemaResponse(fields=_DEFAULT_INPUT_FIELDS)


@app.post("/api/projects/{project_id}/inputs")
async def submit_inputs(project_id: str, payload: ProjectInputsSubmit, _=Depends(project_access)):
    """Сохранить заполненные исходные данные как материалы проекта (приоритет над БЗ)."""
    clean = {k: v for k, v in payload.values.items() if str(v).strip()}
    if not clean:
        return {"ok": True, "saved": 0}
    # структурно (для расчётного ядра) + текстом (для RAG-контекста)
    await storage.set_project_inputs(project_id, clean)
    text = "ИСХОДНЫЕ ДАННЫЕ ПРОЕКТА (заданы пользователем):\n" + \
        "\n".join(f"- {k}: {v}" for k, v in clean.items())
    chunks = add_project_text(text, project_id, filename="исходные данные")
    return {"ok": True, "saved": len(clean), "chunks": chunks}


@app.get("/api/projects/{project_id}/spec")
async def project_spec(project_id: str, _=Depends(project_access)):
    """
    Структурированная спецификация проекта — единый источник истины.

    Собирает из исходных данных проекта детерминированную спецификацию
    (производственная программа, ресурсы, оборудование, электроснабжение,
    площади, состав корпусов, себестоимость) через расчётное ядро. Если объём
    выпуска не задан, возвращает has_data=False с уже введёнными данными.
    """
    from calc import build_spec
    inputs = await storage.get_project_inputs(project_id) or {}
    return build_spec(inputs)


async def _spec_snapshot(project_id: str) -> str:
    """JSON-снимок спецификации проекта на текущий момент (для версии артефакта)."""
    from calc import build_spec
    try:
        inputs = await storage.get_project_inputs(project_id) or {}
        return json.dumps(build_spec(inputs), ensure_ascii=False)
    except Exception:
        return ""


@app.get("/api/projects/{project_id}/versions")
async def project_versions(project_id: str, _=Depends(project_access)):
    """История версий артефактов проекта (без бинарного содержимого)."""
    rows = await storage.list_versions(project_id)
    return [
        {"id": r.id, "label": r.label, "file_name": r.file_name,
         "mime": r.mime, "created_at": r.created_at.isoformat(),
         "has_file": bool(r.file_name)}
        for r in rows
    ]


@app.get("/api/projects/{project_id}/versions/{version_id}")
async def download_version(project_id: str, version_id: int, _=Depends(project_access)):
    """Скачать файл сохранённой версии артефакта."""
    row = await storage.get_version(version_id)
    if not row or row.project_id != project_id or not row.content:
        raise HTTPException(status_code=404, detail="Версия или файл не найдены")
    quoted = quote(row.file_name or f"version_{version_id}")
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"}
    return Response(content=row.content,
                    media_type=row.mime or "application/octet-stream", headers=headers)


@app.get("/api/projects/{project_id}/package")
async def project_package(project=Depends(project_access)):
    """Полный пакет проекта одним архивом: записка (DOCX), ведомость (XLSX),
    сводный отчёт (PDF), генплан (.cdw, если доступен коннектор) и манифест."""
    import io
    import zipfile
    project_id = project.id

    buf = io.BytesIO()
    included: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for doc_type in ("docx", "xlsx", "pdf"):
            try:
                content, _, fname = await build_document(project_id, doc_type)
                z.writestr(f"documents/{fname}", content)
                included.append(fname)
            except Exception:
                log.exception("Пакет: не удалось собрать %s", doc_type)

        # Генплан завода через коннектор Компас (если запущен) — best-effort
        try:
            import httpx
            buildings = await _project_buildings(project)
            gen = {"kind": "site_plan", "title": f"Генплан — {project.name}",
                   "project": project.id[:8], "designer": "AI Конструкторское бюро",
                   "buildings": [b.model_dump() for b in buildings]}
            url = settings.kompas_connector_url.rstrip("/")
            async with httpx.AsyncClient(timeout=180.0) as client:
                r = await client.post(f"{url}/generate", json=gen)
            if r.status_code < 400 and r.content[:2] == b"PK":
                z.writestr("drawings/Генплан.cdw", r.content)
                included.append("Генплан.cdw")
        except Exception:
            log.info("Пакет: чертёж пропущен (коннектор Компас недоступен)")

        manifest = (
            f"ПАКЕТ ПРОЕКТА\nПроект: {project.name}\nОтрасль: {project.industry}\n"
            f"Дата: {project.created_at:%d.%m.%Y}\nСформировано: AI Конструкторское бюро\n\n"
            "Состав пакета:\n" + "\n".join(f"  • {n}" for n in included)
        )
        z.writestr("manifest.txt", manifest.encode("utf-8"))

    fname = f"{project.name}_пакет.zip"
    try:
        await storage.add_version(project_id, "Пакет проекта (ZIP)",
                                  spec_json=await _spec_snapshot(project_id),
                                  file_name=fname, mime="application/zip",
                                  content=buf.getvalue())
    except Exception:
        log.info("Версия пакета не сохранена", exc_info=True)

    quoted = quote(fname)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"}
    return Response(content=buf.getvalue(), media_type="application/zip", headers=headers)


@app.post("/api/projects/{project_id}/materials", response_model=UploadResponse)
async def upload_project_materials(project_id: str, file: UploadFile = File(...),
                                   _=Depends(project_access)):
    """
    Загрузить готовый проект/материалы в КОНКРЕТНЫЙ проект. Эти материалы имеют
    приоритет над базой знаний — агенты дорабатывают именно их.
    """
    allowed = {".txt", ".pdf", ".docx", ".xlsx", ".xlsm"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Поддерживаемые форматы: {', '.join(allowed)}")
    save_path = Path(settings.uploads_path) / f"proj_{project_id}_{file.filename}"
    save_path.write_bytes(await file.read())
    try:
        chunks = await add_project_file(str(save_path), project_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return UploadResponse(ok=True, chunks_added=chunks, agent="(проект)", filename=file.filename or "")


class _MaterialEdit(BaseModel):
    text: str


@app.get("/api/projects/{project_id}/materials")
async def get_project_materials(project_id: str, _=Depends(project_access)):
    """Список фрагментов материалов проекта (что добавлено) — для просмотра/правки."""
    return list_project_materials(project_id)


@app.patch("/api/projects/{project_id}/materials/{frag_id}")
async def edit_project_material(project_id: str, frag_id: str, payload: _MaterialEdit,
                                _=Depends(project_access)):
    """Изменить текст фрагмента материала проекта."""
    if not update_project_material(project_id, frag_id, payload.text):
        raise HTTPException(status_code=404, detail="Фрагмент не найден")
    return {"ok": True}


@app.delete("/api/projects/{project_id}/materials/{frag_id}")
async def remove_project_material(project_id: str, frag_id: str, _=Depends(project_access)):
    """Удалить один фрагмент материала проекта."""
    if not delete_project_material(project_id, frag_id):
        raise HTTPException(status_code=404, detail="Фрагмент не найден")
    return {"ok": True}


@app.delete("/api/projects/{project_id}/materials")
async def remove_project_source(project_id: str, source: str, _=Depends(project_access)):
    """Удалить все фрагменты одного источника (файла) из материалов проекта."""
    n = delete_project_source(project_id, source)
    return {"ok": True, "deleted": n}


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, _=Depends(project_access)):
    """Удалить проект со всей историей, памятью и материалами."""
    if not await storage.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Проект не найден")
    delete_project_collection(project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/memory")
async def add_project_memory(project_id: str, payload: MemoryNoteCreate, _=Depends(project_access)):
    await storage.add_memory(project_id, payload.agent, payload.value)
    return {"ok": True}


# ─── REST: экспорт документов (DOCX / XLSX / PDF) ─────────────────────

@app.post("/api/export")
async def export_document(payload: ExportRequest, user=Depends(get_current_user)):
    """Сформировать документ по проекту и вернуть файл на скачивание."""
    proj = await storage.get_project(payload.project_id)
    if proj and proj.owner_id and proj.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Нет доступа к проекту")
    try:
        content, mime, filename = await build_document(payload.project_id, payload.doc_type)
    except LookupError:
        raise HTTPException(status_code=404, detail="Проект не найден")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Снимок версии: документ + спецификация на момент генерации
    try:
        await storage.add_version(payload.project_id, f"Документ {payload.doc_type.upper()}",
                                  spec_json=await _spec_snapshot(payload.project_id),
                                  file_name=filename, mime=mime, content=content)
    except Exception:
        log.info("Версия документа не сохранена", exc_info=True)

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


# Типовой состав корпусов кирпичного завода (откат, если LLM недоступен)
_DEFAULT_BUILDINGS = [
    BuildingSpec(name="Склад сырья", width_m=18, length_m=36),
    BuildingSpec(name="Подготовительный цех", width_m=24, length_m=48),
    BuildingSpec(name="Формовочный цех", width_m=24, length_m=72),
    BuildingSpec(name="Сушильный корпус", width_m=18, length_m=96),
    BuildingSpec(name="Обжигательный корпус", width_m=18, length_m=120),
    BuildingSpec(name="Склад готовой продукции", width_m=36, length_m=60),
]


class _BuildingLLM(BaseModel):
    name: str
    width_m: float = 18.0
    length_m: float = 48.0


class _BuildingListLLM(BaseModel):
    buildings: list[_BuildingLLM] = []


async def _project_buildings(project) -> list[BuildingSpec]:
    """Состав корпусов проекта: из ВЫЧИСЛЕННЫХ площадей (если задан объём),
    иначе — предложение Конструктора по названию проекта."""
    try:
        inputs = await storage.get_project_inputs(project.id)
        prod_in = parse_capacity(str(inputs.get("capacity", ""))) if inputs else None
        if prod_in:
            prog = production_program(prod_in)
            return [BuildingSpec(**b) for b in buildings_from_areas(prog.pieces_per_year)]
    except Exception:
        log.info("Корпуса по площадям не получены — откат на LLM", exc_info=True)
    return await _design_buildings(project.name)


async def _design_buildings(brief: str) -> list[BuildingSpec]:
    """Конструктор (LLM) предлагает состав корпусов по брифу. Откат — типовой состав."""
    try:
        from graph.graph import _llm
        from knowledge.chroma import search
        from langchain_core.messages import SystemMessage, HumanMessage

        ctx = search(brief, "builder", "ceramics")
        system = (
            "Ты Конструктор кирпичного завода. По заданию предложи состав основных "
            "корпусов и зданий (от 4 до 8). Для каждого укажи name (рус.), width_m и "
            "length_m — реалистичные габариты в метрах. Ответь СТРОГО JSON."
            + (f"\n\nКонтекст из базы знаний:\n{ctx[:2000]}" if ctx else "")
        )
        llm = _llm(streaming=False).with_structured_output(_BuildingListLLM)
        res: _BuildingListLLM = await llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=brief)]
        )
        skip = ("площадк", "территор", "участок", "генплан")
        items = [
            BuildingSpec(
                name=b.name.strip(),
                width_m=min(max(b.width_m, 6.0), 60.0),     # клэмп до реалистичных
                length_m=min(max(b.length_m, 12.0), 180.0),
            )
            for b in res.buildings
            if b.name and b.name.strip() and not any(s in b.name.lower() for s in skip)
        ][:8]
        if items:
            return items
    except Exception:
        log.info("Состав корпусов через LLM не получен — откат на типовой", exc_info=True)
    return list(_DEFAULT_BUILDINGS)


@app.post("/api/kompas/design")
async def kompas_design(payload: KompasDesignRequest):
    """Бюро проектирует генплан: Конструктор → состав корпусов → Компас рисует .cdw."""
    import httpx
    buildings = await _design_buildings(payload.brief)
    url = settings.kompas_connector_url.rstrip("/")
    gen = {
        "kind": "site_plan", "title": payload.title, "project": payload.project,
        "designer": "AI Конструкторское бюро",
        "buildings": [b.model_dump() for b in buildings],
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(f"{url}/generate", json=gen)
    except Exception:
        raise HTTPException(status_code=503, detail=_KOMPAS_DOWN)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=_connector_error(r))
    headers = {
        "Content-Disposition": 'attachment; filename="site_plan.cdw"',
        "X-Buildings-Count": str(len(buildings)),
    }
    return Response(content=r.content, media_type="application/octet-stream", headers=headers)


@app.post("/api/projects/{project_id}/site-plan")
async def project_site_plan(project=Depends(project_access)):
    """Генплан завода по ВЫЧИСЛЕННЫМ площадям проекта (через коннектор Компас)."""
    import httpx
    project_id = project.id
    buildings = await _project_buildings(project)
    gen = {"kind": "site_plan", "title": f"Генплан — {project.name}",
           "project": project.id[:8], "designer": "AI Конструкторское бюро",
           "buildings": [b.model_dump() for b in buildings]}
    url = settings.kompas_connector_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(f"{url}/generate", json=gen)
    except Exception:
        raise HTTPException(status_code=503, detail=_KOMPAS_DOWN)
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=_connector_error(r))
    try:
        await storage.add_version(project_id, "Генплан (Компас)",
                                  spec_json=await _spec_snapshot(project_id),
                                  file_name="Генплан.cdw",
                                  mime="application/octet-stream", content=r.content)
    except Exception:
        log.info("Версия генплана не сохранена", exc_info=True)
    headers = {"Content-Disposition": 'attachment; filename="site_plan.cdw"'}
    return Response(content=r.content, media_type="application/octet-stream", headers=headers)


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
