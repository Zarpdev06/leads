# Celery worker + beat image (shares the backend codebase).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev libmagic1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/ ./backend/
COPY worker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && useradd --system --create-home --uid 10001 appuser \
    && mkdir -p /app/backend/media && chown -R appuser:appuser /app/backend
ENV PYTHONPATH=/app/backend
WORKDIR /app/backend
USER appuser

ENTRYPOINT ["/entrypoint.sh"]
