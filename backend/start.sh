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

# Do not download 390 MB+ NASA DEMs during Cloud Run web startup; use the dedicated
# Cloud Run Job (scripts/acquire_datasets_job.py) + GCS persistence (MARSCOPE_GCS_BUCKET).
echo "[MARSCOPE] Startup dataset check: datasets_dir=${DATASETS_DIR} gcs_bucket=${MARSCOPE_GCS_BUCKET:-<unset>} startup_acquire_dems=${MARSCOPE_STARTUP_ACQUIRE_DEMS:-false} target_datasets=mola_megt00n090hb,mola_megt90n000cb,hirise_dteec_009149_1750"
if [ "${MARSCOPE_STARTUP_ACQUIRE_DEMS:-false}" = "true" ]; then
  if [ ! -f "${DATASETS_DIR}/raw/dteec_009149_1750_009294_1750_u01.img" ] && [ ! -f "${DATASETS_DIR}/raw/DTEEC_009149_1750_009294_1750_U01.IMG" ]; then
    echo "[MARSCOPE] Scheduling background NASA dataset acquisition (mode=startup_background_job, datasets=mola_megt00n090hb,mola_megt90n000cb,hirise_dteec_009149_1750, datasets_dir=${DATASETS_DIR})"
    (
      set +e
      echo "[MARSCOPE] Background acquisition task started (mode=startup_background_job, datasets=mola_megt00n090hb,mola_megt90n000cb,hirise_dteec_009149_1750)"
      if [ -z "${MARSCOPE_GCS_BUCKET:-}" ]; then
        PYTHONPATH="${PYTHONPATH:-/app/backend}" python3 /app/backend/scripts/acquire_datasets_job.py --no-gcs
      else
        PYTHONPATH="${PYTHONPATH:-/app/backend}" python3 /app/backend/scripts/acquire_datasets_job.py
      fi
      rc=$?
      echo "[MARSCOPE] Background acquisition task completed (exit_status=${rc})"
    ) &
  else
    echo "[MARSCOPE] Startup background acquisition skipped: HiRISE DEM already present in ${DATASETS_DIR}/raw"
  fi
else
  echo "[MARSCOPE] Startup DEM acquisition disabled (mode=cloud_run_job_and_gcs_on_demand, datasets=mola_megt00n090hb,mola_megt90n000cb,hirise_dteec_009149_1750)"
fi

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
