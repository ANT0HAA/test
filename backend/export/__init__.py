"""
Генерация отчётных документов проекта (DOCX / XLSX / PDF).

Документы собираются из истории работы агентов по проекту:
  • пояснительная записка        → DOCX  (docx_report)
  • ведомость оборудования       → XLSX  (xlsx_report)
  • сводный отчёт                → PDF   (pdf_report)

Оформление по ЕСКД/СПДС — минимальное: титул, основная надпись (штамп),
нумерация. Точка входа для API — `build_document`.
"""
from .common import ProjectExportData, collect_project_content, DocType
from .docx_report import build_explanatory_note
from .xlsx_report import build_equipment_sheet
from .pdf_report import build_summary_report


# Тип файла → (генератор, MIME, расширение)
_BUILDERS = {
    "docx": (
        build_explanatory_note,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
    "xlsx": (
        build_equipment_sheet,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    "pdf": (build_summary_report, "application/pdf", "pdf"),
}


async def build_document(project_id: str, doc_type: str) -> tuple[bytes, str, str]:
    """
    Собрать документ выбранного типа по проекту.

    Возвращает (содержимое, MIME-тип, имя файла).
    Бросает ValueError для неизвестного типа и LookupError, если проект не найден.
    """
    if doc_type not in _BUILDERS:
        raise ValueError(f"Неизвестный тип документа: {doc_type}")

    data = await collect_project_content(project_id)
    builder, mime, ext = _BUILDERS[doc_type]
    content = await builder(data)

    safe_name = _slugify(data.name) or "project"
    filename = f"{safe_name}.{ext}"
    return content, mime, filename


def _slugify(name: str) -> str:
    """Безопасное имя файла из названия проекта (латиница/кириллица/цифры → _)."""
    keep = []
    for ch in name.strip():
        if ch.isalnum():
            keep.append(ch)
        elif ch in " -_":
            keep.append("_")
    slug = "".join(keep).strip("_")
    return slug[:80]
