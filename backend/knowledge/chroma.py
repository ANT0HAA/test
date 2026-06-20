"""
База знаний на ChromaDB.
У каждого агента в каждой отрасли — своя коллекция: имя `{industry}_{agent}`.
Документы разбиваются на чанки и хранятся с метаданными.
"""
import os
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from config import settings
from agents.definitions import DEFAULT_INDUSTRY


# ─── Singleton ChromaDB client ─────────────────────────────────────────

_client: chromadb.ClientAPI | None = None


def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=settings.chroma_path)
    return _client


def get_collection(agent_name: str, industry: str = DEFAULT_INDUSTRY) -> chromadb.Collection:
    """Получить (или создать) коллекцию агента в рамках отрасли (изоляция по `{industry}_{agent}`)."""
    ef = embedding_functions.DefaultEmbeddingFunction()
    return get_client().get_or_create_collection(
        name=f"{industry}_{agent_name}",
        embedding_function=ef,
        metadata={"agent": agent_name, "industry": industry},
    )


def list_collections() -> list[str]:
    return [c.name for c in get_client().list_collections()]


# ─── Chunking ──────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    """Разбить текст на перекрывающиеся чанки."""
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks


# ─── Add documents ─────────────────────────────────────────────────────

def add_text(
    text: str,
    agent_name: str,
    filename: str = "manual",
    extra_metadata: dict | None = None,
    industry: str = DEFAULT_INDUSTRY,
) -> int:
    """Добавить текст в базу знаний агента отрасли. Возвращает кол-во добавленных чанков."""
    chunks = _chunk_text(text)
    if not chunks:
        return 0

    col = get_collection(agent_name, industry)
    existing_ids = set(col.get()["ids"])

    ids, documents, metadatas = [], [], []
    for i, chunk in enumerate(chunks):
        doc_id = f"{filename}_{i}"
        if doc_id in existing_ids:
            continue  # пропускаем дубликаты
        ids.append(doc_id)
        documents.append(chunk)
        metadatas.append({"source": filename, "chunk": i, **(extra_metadata or {})})

    if ids:
        col.add(ids=ids, documents=documents, metadatas=metadatas)

    return len(ids)


async def add_file(file_path: str, agent_name: str, industry: str = DEFAULT_INDUSTRY) -> int:
    """Прочитать файл (txt/pdf/docx) и добавить в базу агента отрасли."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    text = ""

    if suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace")

    elif suffix == ".pdf":
        try:
            import PyPDF2

            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                text = "\n".join(
                    page.extract_text() or "" for page in reader.pages
                )
        except Exception as e:
            raise ValueError(f"Ошибка чтения PDF: {e}") from e

    elif suffix in (".docx", ".doc"):
        try:
            from docx import Document

            doc = Document(str(path))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            raise ValueError(f"Ошибка чтения DOCX: {e}") from e

    else:
        raise ValueError(f"Неподдерживаемый тип файла: {suffix}")

    return add_text(text, agent_name, filename=path.name, industry=industry)


# ─── Search ────────────────────────────────────────────────────────────

def search(query: str, agent_name: str, industry: str = DEFAULT_INDUSTRY, n_results: int = 5) -> str:
    """
    Семантический поиск по базе знаний агента отрасли.
    Возвращает конкатенированные релевантные чанки или пустую строку.
    """
    col = get_collection(agent_name, industry)

    # Если коллекция пустая — вернуть пустоту без ошибки
    if col.count() == 0:
        return ""

    n_results = min(n_results, col.count())
    results = col.query(query_texts=[query], n_results=n_results)

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        return ""

    parts = []
    for doc, meta in zip(docs, metas):
        source = meta.get("source", "")
        parts.append(f"[{source}]\n{doc}")

    return "\n\n---\n\n".join(parts)
