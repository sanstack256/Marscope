#!/usr/bin/env sh
set -eu

DATASETS_DIR="${MARSCOPE_DATASETS_DIR:-/data/datasets}"
export MARSCOPE_DATASETS_DIR="${DATASETS_DIR}"

mkdir -p \
  "${DATASETS_DIR}/catalog" \
  "${DATASETS_DIR}/manifests" \
  "${DATASETS_DIR}/raw" \
  "${DATASETS_DIR}/processed" \
  "${DATASETS_DIR}/index" \
  "${DATASETS_DIR}/private_attachments"

if [ -z "${DATABASE_URL:-}" ]; then
  export DATABASE_URL="sqlite:////${DATASETS_DIR#/}/index/marscope_mission.sqlite"
fi

python3 - <<'PY'
import os
from pathlib import Path
from app.ingestion.bootstrap import seed_catalog_metadata_if_empty

seed_catalog_metadata_if_empty(Path(os.environ["MARSCOPE_DATASETS_DIR"]))
PY

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
