"""
Слой доступа к PostgreSQL: персистентная память проектов.

Хранит проекты, историю сообщений (взамен in-memory _sessions) и
«запомненные» решения агентов по проекту (ProjectMemory), которые
подмешиваются в контекст наряду с базой знаний (см. graph/graph.py).
"""
import uuid
from datetime import datetime, timezone

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from sqlalchemy import String, Text, ForeignKey, DateTime, select, delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import settings


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(50), default="ceramics")
    owner_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class User(Base):
    """Пользователь системы. Роль: 'admin' (управление пользователями/агентами) или 'user'."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class UserSession(Base):
    """Сессионный токен пользователя (выдаётся при входе, проверяется в каждом запросе)."""
    __tablename__ = "user_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProjectMessage(Base):
    __tablename__ = "project_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "human" | "ai"
    agent: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ProjectMemory(Base):
    __tablename__ = "project_memory"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(50), index=True)
    key: Mapped[str] = mapped_column(String(100), default="note")
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CustomIndustry(Base):
    """Пользовательская отрасль (добавленная через UI поверх встроенных)."""
    __tablename__ = "custom_industries"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))


class AgentOverride(Base):
    """
    Кастомизация агента: правка встроенного (поля переопределяют код),
    новый агент (is_custom=True) или скрытие (deleted=True).
    Ключ — (industry, agent_id).
    """
    __tablename__ = "agent_overrides"

    industry: Mapped[str] = mapped_column(String(50), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(20), default="")
    icon: Mapped[str] = mapped_column(String(50), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[str] = mapped_column(Text, default="")  # ключевые слова через запятую
    is_custom: Mapped[bool] = mapped_column(default=False)
    deleted: Mapped[bool] = mapped_column(default=False)


_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    """Создать таблицы, если их ещё нет (вызывается при старте приложения)."""
    from sqlalchemy import text
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Идемпотентная миграция: колонка владельца у уже существующих проектов
        await conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS owner_id VARCHAR(36)"
        ))


# ─── Projects ────────────────────────────────────────────────────────────

async def create_project(name: str, industry: str = "ceramics", project_id: str | None = None,
                         owner_id: str | None = None) -> Project:
    async with _SessionLocal() as session:
        project = Project(id=project_id or str(uuid.uuid4()), name=name, industry=industry,
                          owner_id=owner_id)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


async def get_project(project_id: str) -> Project | None:
    async with _SessionLocal() as session:
        return await session.get(Project, project_id)


async def list_projects(owner_id: str | None = None) -> list[Project]:
    """Список проектов. Если owner_id задан — только проекты этого владельца
    (и «ничьи» legacy-проекты с owner_id IS NULL). Без owner_id — все (для админа)."""
    async with _SessionLocal() as session:
        stmt = select(Project).order_by(Project.created_at.desc())
        if owner_id is not None:
            from sqlalchemy import or_
            stmt = stmt.where(or_(Project.owner_id == owner_id, Project.owner_id.is_(None)))
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def delete_project(project_id: str) -> bool:
    """Удалить проект (сообщения и память удалятся каскадом по FK). True, если был."""
    async with _SessionLocal() as session:
        project = await session.get(Project, project_id)
        if not project:
            return False
        await session.delete(project)
        await session.commit()
        return True


async def assign_project_owner(project_id: str, owner_id: str) -> None:
    """Закрепить владельца за проектом (для legacy-проектов без owner_id)."""
    async with _SessionLocal() as session:
        project = await session.get(Project, project_id)
        if project and not project.owner_id:
            project.owner_id = owner_id
            await session.commit()


async def get_or_create_project(project_id: str, default_name: str = "Проект по умолчанию") -> Project:
    """Получить проект или лениво создать с указанным id (обратная совместимость со старым session_id)."""
    project = await get_project(project_id)
    if project:
        return project
    return await create_project(default_name, project_id=project_id)


# ─── История сообщений (взамен in-memory _sessions) ───────────────────────

async def add_message(project_id: str, role: str, agent: str, content: str) -> None:
    async with _SessionLocal() as session:
        session.add(ProjectMessage(project_id=project_id, role=role, agent=agent, content=content))
        await session.commit()


async def get_history(project_id: str, limit: int = 40) -> list[BaseMessage]:
    """Последние `limit` сообщений проекта как LangChain-сообщения, по возрастанию времени."""
    async with _SessionLocal() as session:
        result = await session.execute(
            select(ProjectMessage)
            .where(ProjectMessage.project_id == project_id)
            .order_by(ProjectMessage.id.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())[::-1]

    messages: list[BaseMessage] = []
    for row in rows:
        if row.role == "human":
            messages.append(HumanMessage(content=row.content))
        else:
            messages.append(AIMessage(content=row.content, name=row.agent))
    return messages


async def get_messages(project_id: str, limit: int = 200) -> list[ProjectMessage]:
    """Сырые строки сообщений проекта (для REST, в отличие от get_history для LLM)."""
    async with _SessionLocal() as session:
        result = await session.execute(
            select(ProjectMessage)
            .where(ProjectMessage.project_id == project_id)
            .order_by(ProjectMessage.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def clear_messages(project_id: str) -> None:
    async with _SessionLocal() as session:
        await session.execute(delete(ProjectMessage).where(ProjectMessage.project_id == project_id))
        await session.commit()


# ─── Память агентов по проекту («запомненные» решения) ────────────────────

async def add_memory(project_id: str, agent: str, value: str, key: str = "note") -> None:
    async with _SessionLocal() as session:
        session.add(ProjectMemory(project_id=project_id, agent=agent, key=key, value=value))
        await session.commit()


_INPUTS_AGENT = "__inputs__"


async def set_project_inputs(project_id: str, values: dict) -> None:
    """Сохранить структурные исходные данные проекта (перезаписью)."""
    import json
    async with _SessionLocal() as session:
        await session.execute(
            delete(ProjectMemory).where(
                ProjectMemory.project_id == project_id, ProjectMemory.agent == _INPUTS_AGENT)
        )
        session.add(ProjectMemory(project_id=project_id, agent=_INPUTS_AGENT,
                                  key="json", value=json.dumps(values, ensure_ascii=False)))
        await session.commit()


async def get_project_inputs(project_id: str) -> dict:
    """Получить структурные исходные данные проекта ({} если нет)."""
    import json
    async with _SessionLocal() as session:
        result = await session.execute(
            select(ProjectMemory).where(
                ProjectMemory.project_id == project_id, ProjectMemory.agent == _INPUTS_AGENT)
        )
        row = result.scalars().first()
    if not row:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


async def get_memory(project_id: str, agent: str) -> list[ProjectMemory]:
    async with _SessionLocal() as session:
        result = await session.execute(
            select(ProjectMemory)
            .where(ProjectMemory.project_id == project_id, ProjectMemory.agent == agent)
            .order_by(ProjectMemory.created_at.asc())
        )
        return list(result.scalars().all())


# ─── Кастомизация агентов и отраслей (управление через UI) ────────────

async def list_custom_industries() -> list[CustomIndustry]:
    async with _SessionLocal() as session:
        result = await session.execute(select(CustomIndustry))
        return list(result.scalars().all())


async def upsert_custom_industry(industry_id: str, display_name: str) -> None:
    async with _SessionLocal() as session:
        row = await session.get(CustomIndustry, industry_id)
        if row:
            row.display_name = display_name
        else:
            session.add(CustomIndustry(id=industry_id, display_name=display_name))
        await session.commit()


async def delete_custom_industry(industry_id: str) -> None:
    async with _SessionLocal() as session:
        row = await session.get(CustomIndustry, industry_id)
        if row:
            await session.delete(row)
        # заодно убрать кастомизации агентов этой отрасли
        await session.execute(delete(AgentOverride).where(AgentOverride.industry == industry_id))
        await session.commit()


async def list_agent_overrides() -> list[AgentOverride]:
    async with _SessionLocal() as session:
        result = await session.execute(select(AgentOverride))
        return list(result.scalars().all())


async def upsert_agent_override(industry: str, agent_id: str, fields: dict) -> None:
    """Создать/обновить кастомизацию агента. fields — только переопределяемые поля."""
    async with _SessionLocal() as session:
        row = await session.get(AgentOverride, (industry, agent_id))
        if not row:
            row = AgentOverride(industry=industry, agent_id=agent_id)
            session.add(row)
        for key, value in fields.items():
            setattr(row, key, value)
        await session.commit()


async def delete_agent_override(industry: str, agent_id: str) -> None:
    async with _SessionLocal() as session:
        row = await session.get(AgentOverride, (industry, agent_id))
        if row:
            await session.delete(row)
            await session.commit()


# ─── Пользователи и сессии (авторизация) ──────────────────────────────

async def count_users() -> int:
    from sqlalchemy import func
    async with _SessionLocal() as session:
        result = await session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())


async def create_user(username: str, password_hash: str, role: str = "user") -> User:
    async with _SessionLocal() as session:
        user = User(username=username, password_hash=password_hash, role=role)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def get_user_by_username(username: str) -> User | None:
    async with _SessionLocal() as session:
        result = await session.execute(select(User).where(User.username == username))
        return result.scalars().first()


async def get_user(user_id: str) -> User | None:
    async with _SessionLocal() as session:
        return await session.get(User, user_id)


async def list_users() -> list[User]:
    async with _SessionLocal() as session:
        result = await session.execute(select(User).order_by(User.created_at.asc()))
        return list(result.scalars().all())


async def delete_user(user_id: str) -> bool:
    async with _SessionLocal() as session:
        user = await session.get(User, user_id)
        if not user:
            return False
        await session.delete(user)
        await session.commit()
        return True


async def create_session(user_id: str, token: str, expires_at: datetime) -> None:
    async with _SessionLocal() as session:
        session.add(UserSession(token=token, user_id=user_id, expires_at=expires_at))
        await session.commit()


async def get_session_user(token: str) -> User | None:
    """Пользователь по действующему токену (None, если токен неизвестен или истёк)."""
    async with _SessionLocal() as session:
        row = await session.get(UserSession, token)
        if not row:
            return None
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            await session.delete(row)
            await session.commit()
            return None
        return await session.get(User, row.user_id)


async def delete_session(token: str) -> None:
    async with _SessionLocal() as session:
        row = await session.get(UserSession, token)
        if row:
            await session.delete(row)
            await session.commit()
