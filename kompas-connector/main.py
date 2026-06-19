"""
Сервис-коннектор Компас-3D.

Отдельный процесс (Windows), общается с backend по HTTP. Управляет Компас-3D
через COM API (pywin32). Backend проксирует сюда запросы на чтение/генерацию
чертежей; если коннектор не запущен — платформа продолжает работать (см.
обработку в backend/main.py).

Запуск:
    cd kompas-connector
    python -m venv .venv && .venv\\Scripts\\activate
    pip install -r requirements.txt
    uvicorn main:app --port 8100
"""
import logging
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response

from schemas import HealthResponse, ReadResult, GenerateRequest
from kompas_client import KompasClient, KompasUnavailable

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kompas-connector")

app = FastAPI(title="Kompas-3D Connector", version="0.1.0")

# Клиент COM создаётся лениво и переиспользуется между запросами
_client = KompasClient()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Доступность Компас-3D (без запуска тяжёлых операций)."""
    available, version, detail = _client.probe()
    return HealthResponse(ok=True, kompas_available=available, version=version, detail=detail)


@app.post("/read", response_model=ReadResult)
async def read_drawing(file: UploadFile = File(...)) -> ReadResult:
    """Разобрать загруженный .cdw/.frw: спецификация, размеры, тексты."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".cdw", ".frw"):
        raise HTTPException(status_code=400, detail="Ожидается файл .cdw или .frw")

    data = await file.read()
    tmp = Path(tempfile.gettempdir()) / f"kompas_in_{abs(hash(file.filename))}{suffix}"
    tmp.write_bytes(data)
    try:
        return _client.read_drawing(str(tmp), filename=file.filename or tmp.name)
    except KompasUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.exception("Ошибка чтения чертежа")
        raise HTTPException(status_code=422, detail=f"Не удалось разобрать чертёж: {e}")
    finally:
        tmp.unlink(missing_ok=True)


@app.post("/generate")
def generate_drawing(req: GenerateRequest) -> Response:
    """Сгенерировать простой чертёж по параметрам и вернуть .cdw."""
    out = Path(tempfile.gettempdir()) / f"kompas_out_{abs(hash(req.title))}.cdw"
    try:
        _client.generate_drawing(req, str(out))
        content = out.read_bytes()
    except KompasUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.exception("Ошибка генерации чертежа")
        raise HTTPException(status_code=422, detail=f"Не удалось сгенерировать чертёж: {e}")
    finally:
        out.unlink(missing_ok=True)

    headers = {"Content-Disposition": 'attachment; filename="drawing.cdw"'}
    return Response(content=content, media_type="application/octet-stream", headers=headers)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8100)
