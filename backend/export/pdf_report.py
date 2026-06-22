"""
Сводный отчёт → PDF (reportlab).

Титул с основной надписью (штампом), исходное задание, разделы по
специалистам. Кириллица — через системный TTF (см. fonts.ensure_fonts).
"""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .common import ProjectExportData, ORG_NAME, ORG_SUBTITLE, lab_lines
from .fonts import ensure_fonts


def _escape(text: str) -> str:
    """Экранирование для мини-разметки reportlab Paragraph."""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


async def build_summary_report(data: ProjectExportData) -> bytes:
    """Сформировать сводный отчёт и вернуть PDF как bytes."""
    font, font_bold = ensure_fonts()

    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "BodyRu", parent=base["Normal"], fontName=font, fontSize=11, leading=15,
    )
    title = ParagraphStyle(
        "TitleRu", parent=base["Title"], fontName=font_bold, fontSize=20,
        leading=24, alignment=TA_CENTER,
    )
    subtitle = ParagraphStyle(
        "SubRu", parent=base["Normal"], fontName=font, fontSize=11,
        leading=14, alignment=TA_CENTER, textColor=colors.grey,
    )
    h1 = ParagraphStyle("H1Ru", parent=base["Heading1"], fontName=font_bold, fontSize=14, leading=18)
    h2 = ParagraphStyle("H2Ru", parent=base["Heading2"], fontName=font_bold, fontSize=12, leading=16)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=15 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
        title=f"Сводный отчёт — {data.name}",
    )

    flow = []
    flow.append(Spacer(1, 30 * mm))
    flow.append(Paragraph(_escape(ORG_NAME), title))
    flow.append(Spacer(1, 4 * mm))
    flow.append(Paragraph(_escape(ORG_SUBTITLE), subtitle))
    flow.append(Spacer(1, 16 * mm))
    flow.append(Paragraph("СВОДНЫЙ ОТЧЁТ", title))
    flow.append(Spacer(1, 3 * mm))
    flow.append(Paragraph(_escape(f"по проекту «{data.name}»"), subtitle))
    flow.append(Spacer(1, 14 * mm))

    # Основная надпись (штамп)
    stamp_rows = [
        ["Организация", ORG_NAME],
        ["Проект", data.name],
        ["Отрасль", data.industry_name],
        ["Документ", "Сводный отчёт"],
        ["Дата", data.date_str],
    ]
    stamp = Table(stamp_rows, colWidths=[45 * mm, 120 * mm])
    stamp.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTNAME", (0, 0), (0, -1), font_bold),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(stamp)

    from reportlab.platypus import PageBreak
    flow.append(PageBreak())

    # Исходное задание
    flow.append(Paragraph("1. Исходное задание", h1))
    flow.append(Spacer(1, 3 * mm))
    if data.tasks:
        for i, task in enumerate(data.tasks, 1):
            flow.append(Paragraph(f"{i}. {_escape(task)}", body))
            flow.append(Spacer(1, 1.5 * mm))
    else:
        flow.append(Paragraph("Задание не зафиксировано.", body))

    no = 1
    if data.calc_summary:
        no += 1
        flow.append(Spacer(1, 5 * mm))
        flow.append(Paragraph(f"{no}. Расчётные данные", h1))
        flow.append(Spacer(1, 3 * mm))
        for para in data.calc_summary.split("\n"):
            para = para.rstrip()
            if para:
                flow.append(Paragraph(_escape(para), body))
                flow.append(Spacer(1, 1 * mm))

    lab_block = lab_lines(data.lab)
    if lab_block:
        no += 1
        flow.append(Spacer(1, 5 * mm))
        flow.append(Paragraph(f"{no}. Лаборатория · сырьё и шихта", h1))
        flow.append(Spacer(1, 3 * mm))
        for line in lab_block:
            flow.append(Paragraph(_escape(line), body))
            flow.append(Spacer(1, 1 * mm))

    section_no = no + 1
    flow.append(Spacer(1, 5 * mm))
    flow.append(Paragraph(f"{section_no}. Проектные решения", h1))
    flow.append(Spacer(1, 3 * mm))
    if not data.sections:
        flow.append(Paragraph("По проекту пока нет проработанных решений специалистов.", body))
    for idx, section in enumerate(data.sections, 1):
        flow.append(Spacer(1, 3 * mm))
        flow.append(Paragraph(f"{section_no}.{idx}. {_escape(section.display_name)}", h2))
        flow.append(Spacer(1, 1.5 * mm))
        for para in (section.content or "—").split("\n"):
            para = para.strip()
            if para:
                flow.append(Paragraph(_escape(para), body))
                flow.append(Spacer(1, 1 * mm))

    doc.build(flow)
    return buf.getvalue()
