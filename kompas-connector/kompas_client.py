"""
COM-обёртка над Компас-3D (API7, pywin32).

Все вызовы COM изолированы здесь. При отсутствии pywin32 или Компас-3D
методы бросают KompasUnavailable — backend превращает это в внятную ошибку,
а остальная платформа продолжает работать.

Проверено вживую на Компас-3D v24 (Windows): создание чертежа с геометрией
и штампом, сохранение .cdw, открытие и чтение текстов/размеров/штампа.
"""
import logging

from schemas import (
    ReadResult, GenerateRequest, TextEntity, DimensionEntity, SpecRow,
)

log = logging.getLogger("kompas-connector.client")

# Тип документа Компас: ksDocumentDrawing = 1 (чертёж)
_KS_DOCUMENT_DRAWING = 1

# Коллекции размеров в ISymbols2DContainer → человекочитаемый тип
_DIMENSION_COLLECTIONS = [
    ("LineDimensions", "линейный"),
    ("AngleDimensions", "угловой"),
    ("RadialDimensions", "радиальный"),
    ("DiametralDimensions", "диаметральный"),
    ("ArcDimensions", "дуговой"),
    ("HeightDimensions", "высотный"),
]


class KompasUnavailable(RuntimeError):
    """Компас-3D или pywin32 недоступны."""


def _registry_version() -> str | None:
    """Версия Компас-3D из реестра (без запуска приложения)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\ASCON\KOMPAS-3D") as key:
            value, _ = winreg.QueryValueEx(key, "CurrentVersion")
            return str(value)
    except Exception:
        return None


def _text_of(entity) -> str:
    """Достать строку из текстовой сущности Компаса (разные версии — разные свойства)."""
    for getter in (
        lambda e: e.Text.Str,
        lambda e: e.Str,
        lambda e: e.Text,
    ):
        try:
            val = getter(entity)
            if isinstance(val, str) and val.strip():
                return val.strip()
        except Exception:
            continue
    return ""


class KompasClient:
    """Тонкая обёртка: подключение к Компас-3D и операции с чертежами."""

    def probe(self) -> tuple[bool, str | None, str]:
        """Установлен ли Компас-3D (без запуска приложения)."""
        try:
            import win32com  # noqa: F401
        except ImportError:
            return False, None, "pywin32 не установлен (нужен Windows + Компас-3D)"
        version = _registry_version()
        if version is None:
            return False, None, "Компас-3D не найден в реестре (ключ ASCON\\KOMPAS-3D)"
        return True, version, f"Компас-3D v{version} установлен"

    # ── Подключение ──────────────────────────────────────────────────
    def _connect(self):
        """Запустить/подключиться к Компас-3D (API7), вернуть IApplication."""
        try:
            import pythoncom
            from win32com.client import gencache
        except ImportError as e:
            raise KompasUnavailable("pywin32 не установлен (нужен Windows)") from e

        pythoncom.CoInitialize()
        try:
            app = gencache.EnsureDispatch("KOMPAS.Application.7")
            app.Visible = False
            return app
        except Exception as e:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            raise KompasUnavailable(f"Не удалось запустить Компас-3D: {e}") from e

    @staticmethod
    def _release():
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    # ── Чтение чертежа ───────────────────────────────────────────────
    def read_drawing(self, path: str, filename: str) -> ReadResult:
        app = self._connect()
        from win32com.client import CastTo
        doc = app.Documents.Open(path, False, True)  # invisible, readonly
        if doc is None:
            self._release()
            raise RuntimeError("Компас не смог открыть документ")
        try:
            doc2d = CastTo(doc, "IKompasDocument2D")
            texts: list[TextEntity] = []
            dimensions: list[DimensionEntity] = []
            specification: list[SpecRow] = []

            try:
                sheet_count = doc2d.LayoutSheets.Count
            except Exception:
                sheet_count = 0

            # Поля основной надписи (штампа) → как текстовые поля
            try:
                stamp = doc2d.LayoutSheets.Item(0).Stamp
                for col in range(1, 11):
                    try:
                        s = stamp.Text(col).Str
                    except Exception:
                        continue
                    if isinstance(s, str) and s.strip():
                        texts.append(TextEntity(text=s.strip()))
            except Exception:
                log.debug("Штамп не прочитан", exc_info=True)

            # Геометрия/надписи активного вида
            try:
                view = doc2d.ViewsAndLayersManager.Views.ActiveView
                cont = CastTo(view, "IDrawingContainer")
                dt = cont.DrawingTexts
                for i in range(dt.Count):
                    s = _text_of(dt.Item(i))
                    if s:
                        texts.append(TextEntity(text=s))

                sym = CastTo(view, "ISymbols2DContainer")
                for coll_name, kind in _DIMENSION_COLLECTIONS:
                    coll = getattr(sym, coll_name, None)
                    if not coll:
                        continue
                    try:
                        count = coll.Count
                    except Exception:
                        continue
                    for i in range(count):
                        d = coll.Item(i)
                        value = 0.0
                        for attr in ("Value", "Tolerance", "Radius"):
                            try:
                                value = float(getattr(d, attr))
                                break
                            except Exception:
                                continue
                        dimensions.append(DimensionEntity(kind=kind, value=value, text=_text_of(d)))
            except Exception:
                log.debug("Геометрия/размеры не прочитаны", exc_info=True)

            return ReadResult(
                filename=filename,
                doc_type="чертёж" if filename.lower().endswith(".cdw") else "фрагмент",
                sheet_count=sheet_count,
                texts=texts,
                dimensions=dimensions,
                specification=specification,
            )
        finally:
            try:
                doc.Close(0)  # kdDoNotSaveChanges
            except Exception:
                pass
            self._release()

    # ── Генерация чертежа ────────────────────────────────────────────
    def generate_drawing(self, req: GenerateRequest, out_path: str) -> None:
        app = self._connect()
        from win32com.client import CastTo
        doc = app.Documents.AddWithDefaultSettings(_KS_DOCUMENT_DRAWING, True)
        try:
            doc2d = CastTo(doc, "IKompasDocument2D")
            view = doc2d.ViewsAndLayersManager.Views.ActiveView
            cont = CastTo(view, "IDrawingContainer")

            # Прямоугольный контур (план фундамента / габарит) основной линией
            w, h = float(req.width_mm), float(req.length_mm)
            segments = [(0, 0, w, 0), (w, 0, w, h), (w, h, 0, h), (0, h, 0, 0)]
            line_segments = cont.LineSegments
            for x1, y1, x2, y2 in segments:
                seg = line_segments.Add()
                seg.X1, seg.Y1, seg.X2, seg.Y2 = x1, y1, x2, y2
                seg.Style = 1  # основная линия
                seg.Update()

            # Основная надпись (штамп)
            try:
                stamp = doc2d.LayoutSheets.Item(0).Stamp
                stamp.Text(1).Str = req.title
                if req.designer:
                    stamp.Text(2).Str = req.designer
                if req.project:
                    stamp.Text(3).Str = req.project
                stamp.Update()
            except Exception:
                log.debug("Штамп не заполнен", exc_info=True)

            doc.SaveAs(out_path)
        finally:
            try:
                doc.Close(0)
            except Exception:
                pass
            self._release()
