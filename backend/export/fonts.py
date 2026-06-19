"""
Поиск кириллического TTF-шрифта для reportlab (PDF).

Шрифт не хранится в репозитории: используем системный. На Windows — Arial,
в Docker (Linux) — DejaVu (ставится через `fonts-dejavu-core`, см. Dockerfile).
Если ничего не найдено — откат на встроенный Helvetica (только латиница).
"""
import logging
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

log = logging.getLogger(__name__)

# Кандидаты (обычный, жирный). Берём первый существующий комплект.
_CANDIDATES: list[tuple[str, str]] = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
]

FONT_REGULAR = "Body"
FONT_BOLD = "Body-Bold"

_registered = False


def ensure_fonts() -> tuple[str, str]:
    """
    Зарегистрировать кириллический шрифт в reportlab (один раз).
    Возвращает имена (regular, bold) для использования в стилях.
    """
    global _registered
    if _registered:
        return FONT_REGULAR, FONT_BOLD

    for regular, bold in _CANDIDATES:
        if Path(regular).exists():
            try:
                pdfmetrics.registerFont(TTFont(FONT_REGULAR, regular))
                bold_path = bold if Path(bold).exists() else regular
                pdfmetrics.registerFont(TTFont(FONT_BOLD, bold_path))
                pdfmetrics.registerFontFamily(
                    FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD
                )
                _registered = True
                log.info("PDF: используется шрифт %s", regular)
                return FONT_REGULAR, FONT_BOLD
            except Exception:
                log.warning("Не удалось зарегистрировать шрифт %s", regular, exc_info=True)

    # Откат: встроенные шрифты reportlab (без кириллицы — будут «квадраты»).
    log.warning("Кириллический TTF не найден — PDF будет с Helvetica (только латиница). "
                "Установите fonts-dejavu-core (Linux) или используйте Windows.")
    return "Helvetica", "Helvetica-Bold"
