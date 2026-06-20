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
    """Достать строку из текстовой сущности Компаса (разные версии — разные свойства).
    У IDrawingText содержимое доступно только через интерфейс IText (CastTo)."""
    def _via_itext(e):
        from win32com.client import CastTo
        return CastTo(e, "IText").Str

    for getter in (
        _via_itext,
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

    # ── Примитивы рисования ──────────────────────────────────────────
    @staticmethod
    def _rect(cont, x: float, y: float, w: float, h: float, style: int = 1) -> None:
        ls = cont.LineSegments
        for x1, y1, x2, y2 in [(x, y, x + w, y), (x + w, y, x + w, y + h),
                               (x + w, y + h, x, y + h), (x, y + h, x, y)]:
            seg = ls.Add()
            seg.X1, seg.Y1, seg.X2, seg.Y2 = x1, y1, x2, y2
            seg.Style = style
            seg.Update()

    @staticmethod
    def _axes(cont, x: float, y: float, w: float, h: float) -> None:
        """Осевые линии (штрихпунктир, стиль «осевая») по центру прямоугольника."""
        ext = max(w, h) * 0.1
        ls = cont.LineSegments
        for x1, y1, x2, y2 in [(x + w / 2, y - ext, x + w / 2, y + h + ext),
                               (x - ext, y + h / 2, x + w + ext, y + h / 2)]:
            seg = ls.Add()
            seg.X1, seg.Y1, seg.X2, seg.Y2 = x1, y1, x2, y2
            seg.Style = 3  # осевая
            seg.Update()

    @staticmethod
    def _dimension(sym, x1: float, y1: float, x2: float, y2: float,
                   x3: float, y3: float, orient: int) -> None:
        """Линейный размер между (x1,y1)-(x2,y2); (x3,y3) — позиция размерной линии."""
        d = sym.LineDimensions.Add()
        d.X1, d.Y1, d.X2, d.Y2, d.X3, d.Y3 = x1, y1, x2, y2, x3, y3
        try:
            d.Orientation = orient  # 0 — горизонтальный, 1 — вертикальный
        except Exception:
            pass
        d.Update()

    @staticmethod
    def _label(cont, cast_to, x: float, y: float, text: str, height: float = 3.5) -> None:
        t = cont.DrawingTexts.Add()
        t.X, t.Y, t.Height = x, y, height
        try:
            cast_to(t, "IText").Str = text
        except Exception:
            pass
        t.Update()

    # ── Генерация чертежа ────────────────────────────────────────────
    def generate_drawing(self, req: GenerateRequest, out_path: str) -> None:
        app = self._connect()
        from win32com.client import CastTo
        doc = app.Documents.AddWithDefaultSettings(_KS_DOCUMENT_DRAWING, True)
        try:
            doc2d = CastTo(doc, "IKompasDocument2D")
            view = doc2d.ViewsAndLayersManager.Views.ActiveView
            cont = CastTo(view, "IDrawingContainer")
            sym = CastTo(view, "ISymbols2DContainer")

            if req.kind == "site_plan":
                self._draw_site_plan(cont, CastTo, req.buildings)
                stamp_title = req.title if req.title != "План фундамента" else "Генплан кирпичного завода"
            else:
                # План корпуса/фундамента: контур + оси + размерные линии (реальные мм)
                w, h = float(req.width_mm), float(req.length_mm)
                self._rect(cont, 0, 0, w, h)
                self._axes(cont, 0, 0, w, h)
                off = max(w, h) * 0.18
                self._dimension(sym, 0, 0, w, 0, w / 2, -off, 0)   # ширина (снизу)
                self._dimension(sym, 0, 0, 0, h, -off, h / 2, 1)   # длина (слева)
                self._label(cont, CastTo, 0, h + off * 0.4, req.title, height=max(w, h) * 0.03)
                stamp_title = req.title

            # Основная надпись (штамп)
            try:
                stamp = doc2d.LayoutSheets.Item(0).Stamp
                stamp.Text(1).Str = stamp_title
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

    # ── Генплан кирпичного завода (схематический, корпуса + подписи) ──
    # Координаты в мм на листе (схема); в подписях — реальные габариты корпусов.
    _SITE_BUILDINGS = [
        # (название, реальные ВхД, м;  x, y, w, h на листе, мм)
        ("Склад сырья", "18×36", 10, 150, 45, 28),
        ("Подготовит. цех", "24×48", 65, 148, 55, 32),
        ("Формовочный цех", "24×72", 130, 145, 75, 38),
        ("Склад готовой продукции", "36×60", 215, 150, 60, 30),
        ("Сушильный корпус", "18×96", 10, 60, 95, 45),
        ("Обжигательный корпус", "18×120", 120, 55, 135, 50),
    ]

    @staticmethod
    def _layout(buildings) -> list[tuple]:
        """Авто-раскладка корпусов на листе (полочная упаковка), масштаб под габариты.
        Возвращает (название, размер, x, y, w, h) в мм на листе."""
        sheet_w, top, margin, gap = 285.0, 188.0, 8.0, 14.0
        max_len = max((b.length_m for b in buildings), default=100.0) or 100.0
        k = 130.0 / max_len            # длиннейший корпус → ~130 мм
        placed, x, y_top, row_h = [], margin, top, 0.0
        for b in buildings:
            w, h = max(b.length_m * k, 12.0), max(b.width_m * k, 8.0)
            if x + w > sheet_w - margin:        # перенос на новую «полку»
                x = margin
                y_top -= row_h + gap + 6
                row_h = 0.0
            placed.append((b.name, f"{b.width_m:g}×{b.length_m:g} м", x, y_top - h, w, h))
            x += w + gap
            row_h = max(row_h, h)
        return placed

    def _draw_site_plan(self, cont, cast_to, buildings=None) -> None:
        # Граница участка + заголовок
        self._rect(cont, 0, 0, 285, 200, style=3)
        self._label(cont, cast_to, 5, 205, "ГЕНПЛАН КИРПИЧНОГО ЗАВОДА", height=7)
        rows = (self._layout(buildings) if buildings
                else [(n, s, x, y, w, h) for n, s, x, y, w, h in self._SITE_BUILDINGS])
        for name, size, x, y, w, h in rows:
            self._rect(cont, x, y, w, h)                       # контур корпуса
            self._axes(cont, x, y, w, h)                       # разбивочные оси корпуса
            self._label(cont, cast_to, x + 2, y + h - 6, name, height=3.5)
            self._label(cont, cast_to, x + 2, y + 2, f"{size}", height=3.0)
