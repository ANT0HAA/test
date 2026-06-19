# Kompas-3D Connector

Отдельный **Windows-сервис** для интеграции платформы с Компас-3D через COM API
(`pywin32`). Backend общается с ним по HTTP и **продолжает работать, если коннектор
не запущен** (например, backend на Linux) — операции с чертежами в этом случае
возвращают внятную ошибку, остальная платформа не затрагивается.

## Требования
- Windows с установленным **Компас-3D** (проверено на v24).
- Python 3.12.

## Запуск
```powershell
cd kompas-connector
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --port 8100
```
Backend находит коннектор по `KOMPAS_CONNECTOR_URL` (по умолчанию
`http://localhost:8100`, см. `backend/config.py`).

## Эндпоинты
| Метод | Путь        | Назначение |
|-------|-------------|------------|
| GET   | `/health`   | Установлен ли Компас-3D (без запуска приложения) |
| POST  | `/read`     | Разбор `.cdw` / `.frw`: штамп, тексты, размеры → JSON |
| POST  | `/generate` | Генерация простого чертежа (план/габарит + штамп) → `.cdw` |

`/read` принимает файл (multipart `file`). `/generate` принимает JSON
(`GenerateRequest`: `kind`, `width_mm`, `length_mm`, `title`, `project`, `designer`).

## Как это вызывается с платформы
Backend проксирует:
- `GET  /api/kompas/status`   → `/health`
- `POST /api/kompas/read`     → `/read`
- `POST /api/kompas/generate` → `/generate`

При первом обращении Компас-3D стартует в фоне (может занять ~30–40 с).
Последующие вызовы быстрые. Окно Компаса не показывается (`Visible = False`).

## Замечания
- Весь COM-код изолирован в `kompas_client.py`. Отсутствие `pywin32`/Компаса
  даёт `KompasUnavailable` → HTTP 503 на стороне backend.
- Чтение спецификации зависит от структуры документа; текущая версия извлекает
  поля штампа, текстовые надписи и размеры активного вида.
