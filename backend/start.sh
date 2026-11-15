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

# Auto-acquire mandatory Gale DEMs on empty persistent volumes without blocking healthchecks
if [ ! -f "${DATASETS_DIR}/raw/dteec_009149_1750_009294_1750_u01.img" ] && [ ! -f "${DATASETS_DIR}/raw/DTEEC_009149_1750_009294_1750_U01.IMG" ]; then
  echo "[MARSCOPE] Mandatory HiRISE DEM missing in ${DATASETS_DIR}/raw; starting background NASA PDS acquisition..."
  (
    PYTHONPATH="${PYTHONPATH:-/app/backend}" python3 - <<'PY'
import asyncio, json
from app.ingestion.bootstrap import acquire_bootstrap_datasets
from app.services.container import acquisition_service, catalog_service

res = asyncio.run(
    acquire_bootstrap_datasets(
        catalog_service=catalog_service,
        acquisition_service=acquisition_service,
        dataset_ids=["hirise_dteec_009149_1750", "mola_megt90n000cb", "mola_megt00n090hb"],
    )
)
print("[MARSCOPE] Background DEM acquisition finished:", json.dumps(res))
PY
  ) &
fi

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
