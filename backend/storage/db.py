"""
Слой доступа к PostgreSQL: персистентная память проектов.

Хранит проекты, историю сообщений (взамен in-memory _sessions) и
«запомненные» решения агентов по проекту (ProjectMemory), которые
подмешиваются в контекст наряду с базой знаний (см. graph/graph.py).
"""
import uuid
from datetime import datetime, timezone

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from sqlalchemy import String, Text, ForeignKey, select, delete
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
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


class ProjectMessage(Base):
    __tablename__ = "project_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "human" | "ai"
    agent: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


class ProjectMemory(Base):
    __tablename__ = "project_memory"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(50), index=True)
    key: Mapped[str] = mapped_column(String(100), default="note")
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    """Создать таблицы, если их ещё нет (вызывается при старте приложения)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ─── Projects ────────────────────────────────────────────────────────────

async def create_project(name: str, industry: str = "ceramics", project_id: str | None = None) -> Project:
    async with _SessionLocal() as session:
        project = Project(id=project_id or str(uuid.uuid4()), name=name, industry=industry)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


async def get_project(project_id: str) -> Project | None:
    async with _SessionLocal() as session:
        return await session.get(Project, project_id)


async def list_projects() -> list[Project]:
    async with _SessionLocal() as session:
        result = await session.execute(select(Project).order_by(Project.created_at.desc()))
        return list(result.scalars().all())


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


async def get_memory(project_id: str, agent: str) -> list[ProjectMemory]:
    async with _SessionLocal() as session:
        result = await session.execute(
            select(ProjectMemory)
            .where(ProjectMemory.project_id == project_id, ProjectMemory.agent == agent)
            .order_by(ProjectMemory.created_at.asc())
        )
        return list(result.scalars().all())
