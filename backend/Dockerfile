FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend \
    MARSCOPE_SEED_DATASETS_DIR=/app/seed_datasets \
    MARSCOPE_DATASETS_DIR=/data/datasets \
    HOST=0.0.0.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libexpat1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY scripts/bootstrap_datasets.py /app/scripts/bootstrap_datasets.py
COPY datasets/bootstrap_manifest.json /app/seed_datasets/bootstrap_manifest.json
COPY datasets/catalog /app/seed_datasets/catalog

RUN chmod +x /app/backend/start.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health" >/dev/null || exit 1'

CMD ["/app/backend/start.sh"]
