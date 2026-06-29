FROM python:3.12-slim

WORKDIR /app

# build-essential — на случай сборки C-расширений; fonts-dejavu-core — кириллица в PDF;
# tesseract-ocr(+rus) — OCR скан-PDF в материалах проекта (см. knowledge/ocr.py)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fonts-dejavu-core \
    tesseract-ocr \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p chroma_data uploads

# Большой ws-ping-timeout: чат не рвётся, пока модель грузится в память (~мин) или
# инициализируются эмбеддинги ChromaDB при первом запросе (иначе WS закрывается по
# таймауту пинга 1011 и в чате видна «ошибка загрузки»).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--ws-ping-interval", "30", "--ws-ping-timeout", "600"]
