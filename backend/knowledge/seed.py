"""
Наполнение базы знаний агентов документами проекта (batch-ингест).

Берёт папку с документами и раскладывает их по коллекциям агентов отрасли
согласно маппингу «имя файла → агент(ы)». Поддерживает txt / pdf / docx / xlsx.
Сканы без текстового слоя и архивы (.rar/.7z/.doc) пропускаются с пояснением.

Запуск:
    cd backend && .venv\\Scripts\\activate
    python -m knowledge.seed "C:\\путь\\к\\Документы" [--industry ceramics] [--max-pdf-pages 0]

--max-pdf-pages 0 — без ограничения (весь документ); иначе — первые N страниц.
"""
import argparse
import sys
from pathlib import Path

from agents.definitions import DEFAULT_INDUSTRY, get_agents
from knowledge.chroma import add_text


# Маппинг: подстрока имени файла (в нижнем регистре) → агенты-получатели.
# Файл попадает в базу знаний КАЖДОГО указанного агента.
MAPPING: dict[str, list[str]] = {
    "справочник по керамике": ["technologist"],
    "расчет сушил": ["technologist"],
    "варианты расчета сушил": ["technologist"],
    "расчет состава шихты": ["technologist"],
    "регламент": ["technologist"],
    "схема_потоков": ["technologist"],
    "оборудование": ["mechanic", "estimator"],
    "штатное расписание": ["estimator", "documentalist"],
    "теплотехник": ["documentalist"],
    "тэо": ["documentalist"],
    "пояснительная записка": ["documentalist"],
    "геолог": ["technologist"],
    "карты залеган": ["technologist"],
}

_TEXT_EXT = {".txt", ".pdf", ".docx", ".xlsx", ".xlsm"}


def _match_agents(filename: str) -> list[str]:
    low = filename.lower()
    agents: list[str] = []
    for key, targets in MAPPING.items():
        if key in low:
            for t in targets:
                if t not in agents:
                    agents.append(t)
    return agents


def _pdf_text(path: Path, max_pages: int) -> str:
    from PyPDF2 import PdfReader
    reader = PdfReader(str(path))
    pages = reader.pages if max_pages <= 0 else reader.pages[:max_pages]
    return "\n".join((p.extract_text() or "") for p in pages)


def _docx_text(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _xlsx_text(path: Path) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    lines: list[str] = []
    for ws in wb.worksheets:
        lines.append(f"[Лист: {ws.title}]")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c not in (None, "")]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _extract(path: Path, max_pdf_pages: int) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return _pdf_text(path, max_pdf_pages)
    if suffix == ".docx":
        return _docx_text(path)
    if suffix in (".xlsx", ".xlsm"):
        return _xlsx_text(path)
    return ""


def seed_directory(directory: str, industry: str = DEFAULT_INDUSTRY, max_pdf_pages: int = 0) -> None:
    root = Path(directory)
    if not root.is_dir():
        print(f"Папка не найдена: {root}")
        sys.exit(1)

    known_agents = set(get_agents(industry))
    total_chunks = 0
    print(f"Ингест в отрасль «{industry}». Папка: {root}\n")

    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        agents = _match_agents(path.name)
        if not agents:
            print(f"  — {path.name}: пропуск (нет маппинга)")
            continue
        agents = [a for a in agents if a in known_agents]
        if not agents:
            print(f"  — {path.name}: пропуск (агенты не из отрасли «{industry}»)")
            continue
        if path.suffix.lower() not in _TEXT_EXT:
            print(f"  — {path.name}: пропуск (формат {path.suffix} не поддерживается — архив/.doc)")
            continue

        try:
            text = _extract(path, max_pdf_pages)
        except Exception as e:
            print(f"  ✗ {path.name}: ошибка чтения — {type(e).__name__}: {e}")
            continue

        if len(text.strip()) < 50:
            print(f"  — {path.name}: пропуск (нет текстового слоя — вероятно скан, нужен OCR)")
            continue

        for agent in agents:
            added = add_text(text, agent, filename=path.name, industry=industry)
            total_chunks += added
            print(f"  ✓ {path.name} → {agent}: +{added} чанков")

    print(f"\nГотово. Всего добавлено чанков: {total_chunks}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Наполнение базы знаний агентов документами")
    parser.add_argument("directory", help="Папка с документами")
    parser.add_argument("--industry", default=DEFAULT_INDUSTRY, help="Отрасль (по умолчанию ceramics)")
    parser.add_argument("--max-pdf-pages", type=int, default=0,
                        help="Лимит страниц PDF (0 — без ограничения)")
    args = parser.parse_args()
    seed_directory(args.directory, args.industry, args.max_pdf_pages)


if __name__ == "__main__":
    main()
