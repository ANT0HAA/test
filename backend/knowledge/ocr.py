"""
OCR скан-PDF (без текстового слоя): рендер страниц через PyMuPDF → Tesseract.

Пути к Tesseract и tessdata определяются автоматически (типовые места установки
на Windows + папка backend/.tessdata с русским языком) либо берутся из настроек.
Если Tesseract/зависимости недоступны — OCR молча отключается (ocr_available()=False).
"""
import os
from pathlib import Path

from config import settings

# Типовые места установки Tesseract на Windows
_WIN_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    str(Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    str(Path.home() / r"AppData\Local\Tesseract-OCR\tesseract.exe"),
]

# Папка с языковыми данными (rus лежит здесь — в стандартной установке его нет)
_LOCAL_TESSDATA = Path(__file__).resolve().parent.parent / ".tessdata"

_configured = False


def _find_tesseract() -> str | None:
    if settings.tesseract_cmd and Path(settings.tesseract_cmd).exists():
        return settings.tesseract_cmd
    import shutil
    found = shutil.which("tesseract")
    if found:
        return found
    for c in _WIN_CANDIDATES:
        if Path(c).exists():
            return c
    return None


def _configure() -> bool:
    """Один раз: прописать путь к tesseract и TESSDATA_PREFIX. True, если бинарь найден."""
    global _configured
    if _configured:
        return True
    try:
        import pytesseract
    except ImportError:
        return False
    cmd = _find_tesseract()
    if not cmd:
        return False
    pytesseract.pytesseract.tesseract_cmd = cmd
    # tessdata: настройка → локальная .tessdata (есть rus) → не трогаем
    prefix = settings.tessdata_prefix or (str(_LOCAL_TESSDATA) if _LOCAL_TESSDATA.exists() else "")
    if prefix:
        os.environ["TESSDATA_PREFIX"] = prefix
    _configured = True
    return True


def ocr_available() -> bool:
    """OCR доступен только при наличии pymupdf, pytesseract и бинаря Tesseract."""
    if not settings.ocr_enabled:
        return False
    try:
        import fitz  # noqa: F401  (pymupdf)
        import pytesseract
    except ImportError:
        return False
    if not _configure():
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_pdf(path: Path, max_pages: int | None = None) -> str:
    """Распознать текст скан-PDF. max_pages=None → settings.ocr_max_pages (0 — все)."""
    import fitz
    import pytesseract
    from PIL import Image

    _configure()
    limit = settings.ocr_max_pages if max_pages is None else max_pages
    doc = fitz.open(str(path))
    try:
        last = len(doc) if limit <= 0 else min(limit, len(doc))
        parts: list[str] = []
        for i in range(last):
            pix = doc[i].get_pixmap(dpi=settings.ocr_dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            parts.append(pytesseract.image_to_string(img, lang=settings.ocr_lang))
        return "\n".join(parts)
    finally:
        doc.close()
