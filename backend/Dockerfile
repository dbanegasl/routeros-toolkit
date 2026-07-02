# Backend FastAPI del RouterOS Toolkit
# Contexto de build: la RAÍZ del repo (necesita lib/ y core/):
#   docker build -f backend/Dockerfile .
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY lib/ lib/
COPY core/ core/
COPY backend/app/ backend/app/
COPY backend/__init__.py backend/__init__.py

# config/ y backups/ llegan como volúmenes (ver docker-compose.yml);
# se crean vacíos para que existan aunque no se monten.
RUN mkdir -p config backups \
    && useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
