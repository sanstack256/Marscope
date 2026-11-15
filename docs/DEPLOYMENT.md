# MARSCOPE Deployment & Production Requirements

For the full split-hosting runbook (Vercel Next.js frontend + Railway FastAPI backend with persistent volume), see [`docs/DEPLOYMENT_SPLIT.md`](./DEPLOYMENT_SPLIT.md).

## Critical Production Requirements
- **Durable Storage:** `DATABASE_URL` and `MARSCOPE_DATASETS_DIR` must point to persistent storage (e.g., Railway `/data/datasets`). Ephemeral `:memory:` SQLite is rejected, and `ENVIRONMENT=production` without `DATABASE_URL` fails closed.
- **Signing Secret:** `MARSCOPE_SECRET_KEY` must be configured in `ENVIRONMENT=production`; `get_signing_secret()` refuses to fall back to an ephemeral process secret.
- **Cookies & CORS:** `AUTH_COOKIE_SECURE=true`, `AUTH_COOKIE_SAMESITE=lax`, and explicit `CORS_ORIGINS` (wildcards `*` are rejected).
- **Same-Origin Proxy:** Vercel `BACKEND_INTERNAL_URL` proxies `/api/*` to Railway so `HttpOnly` session cookies, `marscope_csrf` / `X-CSRF-Token`, and `no-transform` SSE streams operate same-origin.
- **Dataset Honesty:** Empty volumes are seeded with tracked catalog JSONs and `bootstrap_manifest.json` only; real NASA PDS products must be acquired and processed via `scripts/bootstrap_datasets.py --acquire --process --rebuild-index`.

## Judge Demo Mode Configuration
- **`MARSCOPE_DEMO_ENABLED`** (`true` by default): Enables the isolated Judge Demo account, `GET /api/demo/config`, `POST /api/demo/reset`, and startup seeding of `demo-mission-gale-001` (`0003_demo_mode.sql`). Set `MARSCOPE_DEMO_ENABLED=false` to disable public demo access in restricted deployments.
- **`MARSCOPE_DEMO_EMAIL`** (default `demo-commander@marscope.demo`): Email for the primary Judge Demo Commander account.
- **`MARSCOPE_DEMO_PASSWORD`** (optional): Explicit password for the Judge Demo Commander account. When omitted, `DemoService` generates a strong random password once and persists the provisioned demo credentials to `<MARSCOPE_DATASETS_DIR>/index/.demo_credentials.json` (`0600`). On Railway, ensure `MARSCOPE_DATASETS_DIR` points to the persistent `/data/datasets` volume so demo credentials survive restarts cleanly.
- **Demo Isolation:** Demo astronauts (`is_demo=1`) can only access `is_demo=1` missions, and standard registered astronauts (`is_demo=0`) cannot access or leak into demo missions (`HTTP 403`).

## Google Cloud Run & GCS Persistence (`marscope-backend`, `asia-south1`)

Cloud Run containers do not persist `/data/datasets` across instances or revisions, and `/data/datasets` is backed by container memory (tmpfs). To prevent 512 MiB OOM kills when acquiring or serving the 390.55 MB HiRISE DEM (`DTEEC_009149_1750_009294_1750_U01.IMG`), acquisition runs in a dedicated **Cloud Run Job** that persists verified raw products to **Google Cloud Storage (GCS)**, and the **Cloud Run Service** retrieves verified DEMs on demand from GCS.

### 1. GCS Bucket & Least-Privilege IAM

```bash
export PROJECT_ID="<your-gcp-project-id>"
export REGION="asia-south1"
export BUCKET="marscope-datasets-${PROJECT_ID}"

gcloud storage buckets create "gs://${BUCKET}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --uniform-bucket-level-access

# Dedicated service accounts
gcloud iam service-accounts create marscope-ingest-job --project="${PROJECT_ID}"
gcloud iam service-accounts create marscope-backend-sa --project="${PROJECT_ID}"

# Least-privilege bucket permissions:
# - Job SA: read/write objects in the dataset bucket
# - Backend SA: read-only object viewer
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:marscope-ingest-job@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:marscope-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

### 2. Build Container Image

```bash
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="gcr.io/${PROJECT_ID}/marscope-backend:latest" \
  -f backend/Dockerfile .
```

### 3. Deploy & Execute the One-Time Acquisition Cloud Run Job

```bash
gcloud run jobs deploy marscope-acquire-dems \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="gcr.io/${PROJECT_ID}/marscope-backend:latest" \
  --service-account="marscope-ingest-job@${PROJECT_ID}.iam.gserviceaccount.com" \
  --memory=2Gi \
  --cpu=1 \
  --task-timeout=3600s \
  --max-retries=2 \
  --command="python3" \
  --args="/app/backend/scripts/acquire_datasets_job.py" \
  --set-env-vars="MARSCOPE_DATASETS_DIR=/data/datasets,MARSCOPE_GCS_BUCKET=${BUCKET},MARSCOPE_GCS_PREFIX=datasets"

gcloud run jobs execute marscope-acquire-dems \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --wait
```

### 4. Deploy the Cloud Run Service (`marscope-backend`)

```bash
gcloud run deploy marscope-backend \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="gcr.io/${PROJECT_ID}/marscope-backend:latest" \
  --service-account="marscope-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --memory=2Gi \
  --cpu=1 \
  --set-env-vars="MARSCOPE_DATASETS_DIR=/data/datasets,MARSCOPE_GCS_BUCKET=${BUCKET},MARSCOPE_GCS_PREFIX=datasets,MARSCOPE_STARTUP_ACQUIRE_DEMS=false"
```

### 5. Verify Production HiRISE Mesh Manifest

```bash
curl -fsS "https://marscope-backend-294995531207.asia-south1.run.app/api/terrain/mesh/manifest/hirise_dteec_009149_1750"
```
