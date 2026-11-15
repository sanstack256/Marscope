# MARSCOPE Split Deployment Guide (Vercel Frontend + Railway Backend)

This guide documents the production split-hosting architecture for MARSCOPE:
- **Vercel** hosts **only** the Next.js frontend (`frontend/`).
- **Railway** hosts the FastAPI backend (`backend/`) using `backend/Dockerfile`, `railway.json`, and a single persistent volume mounted at `/data`.

All API calls, `HttpOnly` session cookies (`marscope_session`), double-submit CSRF cookies (`marscope_csrf` + `X-CSRF-Token`), and Server-Sent Events (`/api/missions/{id}/stream`, `/api/tracking/stream`) are proxied same-origin by Next.js `/api/:path*` rewrites (`BACKEND_INTERNAL_URL`).

---

## 1. Railway Backend Setup

### 1.1 Create Service & Attach Persistent Volume
1. In Railway, create a new project from the `Marscope` GitHub repository.
2. Railway automatically reads root [`railway.json`](../railway.json), which builds [`backend/Dockerfile`](../backend/Dockerfile) and health-checks `/api/health`.
3. Keep **Replicas = 1** (SQLite WAL files reside on a single mounted volume and do not support multi-replica concurrent writers).
4. Attach a **Persistent Volume** to the service:
   - **Mount Path:** `/data`
   - **Recommended Size:** At least `10 GB` (more if acquiring full optional HiRISE/CRISM imagery)

On container boot, [`backend/start.sh`](../backend/start.sh):
- Creates `/data/datasets/{catalog,manifests,raw,processed,index,private_attachments}`.
- Seeds tracked catalog metadata (`bootstrap_manifest.json` and `catalog/*.json`) from `/app/seed_datasets` into `$MARSCOPE_DATASETS_DIR` **only if missing** (never fabricates raw/processed NASA data).
- Starts `uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"`.

### 1.2 Railway Environment Variables
Generate strong secrets locally before pasting them into Railway:
```bash
python3 -c "import secrets; print('MARSCOPE_SECRET_KEY=' + secrets.token_hex(32)); print('MARSCOPE_OPERATOR_TOKEN=' + secrets.token_hex(24)); print('TRACKING_INGEST_TOKEN=' + secrets.token_hex(24))"
```

Set these variables in the Railway service **Variables** tab:

| Variable | Value | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | Enforces `MARSCOPE_SECRET_KEY` fail-closed check at startup |
| `MARSCOPE_DATASETS_DIR` | `/data/datasets` | Persistent root for catalogs, raw/processed NASA files, indexes, and attachments |
| `DATABASE_URL` | `sqlite:////data/datasets/index/marscope_mission.sqlite` | Persistent SQLite WAL database on volume |
| `MARSCOPE_SECRET_KEY` | `<64-hex-char secret>` | Required in production; signs tokens and private attachment URLs |
| `MARSCOPE_OPERATOR_TOKEN` | `<48-hex-char secret>` | Protects operator dataset acquisition & mission readiness mutations |
| `TRACKING_INGEST_TOKEN` | `<48-hex-char secret>` | Optional bearer token for external telemetry ingest |
| `AUTH_COOKIE_SECURE` | `true` | Vercel serves HTTPS externally |
| `AUTH_COOKIE_SAMESITE` | `lax` | Same-origin through Vercel `/api/*` rewrite |
| `CORS_ORIGINS` | `["https://<your-vercel-app>.vercel.app"]` | Explicit origin list (wildcards `*` are rejected) |

Do **not** hardcode `PORT`; Railway injects `PORT` dynamically and `start.sh` binds `0.0.0.0:${PORT:-8000}`.

### 1.3 Generate Public Domain & Bootstrap NASA Datasets on Volume
1. In Railway **Settings -> Networking**, click **Generate Domain** (for example `https://marscope-backend-production.up.railway.app`).
2. Verify backend health:
   ```bash
   curl -fsS https://<your-railway-domain>/api/health
   curl -fsS https://<your-railway-domain>/api/health/readiness
   ```
3. Run the dataset bootstrap CLI inside the Railway service shell (`railway run` or Railway SSH) so real NASA products are acquired and indexed onto `/data/datasets`:
   ```bash
   python3 /app/scripts/bootstrap_datasets.py --verify --json
   python3 /app/scripts/bootstrap_datasets.py --acquire --mandatory-only
   python3 /app/scripts/bootstrap_datasets.py --process --mandatory-only
   python3 /app/scripts/bootstrap_datasets.py --rebuild-index
   python3 /app/scripts/bootstrap_datasets.py --verify --strict --json
   ```

---

## 2. Vercel Frontend Setup

### 2.1 Project Configuration
1. In Vercel, import the `Marscope` GitHub repository.
2. Root [`vercel.json`](../vercel.json) configures Vercel to install and build **only** `frontend/` (`outputDirectory: frontend/.next`). Keep **Root Directory** at repository root (or if set to `frontend`, clear custom build/output overrides so `frontend/next.config.ts` runs directly).

### 2.2 Vercel Environment Variables
Set these in **Project Settings -> Environment Variables**:

| Variable | Value | Notes |
|---|---|---|
| `BACKEND_INTERNAL_URL` | `https://<your-railway-domain>` | **No trailing slash.** Used by `frontend/next.config.ts` to rewrite `/api/:path*` |
| `NEXT_PUBLIC_API_BASE_URL` | `/api` | Keeps browser requests same-origin so `HttpOnly` & CSRF cookies work |
| `NEXT_PUBLIC_APP_NAME` | `MARSCOPE` | Optional display title |

> **Important:** `BACKEND_INTERNAL_URL` is evaluated at Next.js build/route-manifest time (`next.config.ts`). Whenever you change `BACKEND_INTERNAL_URL` in Vercel, trigger a fresh deployment (**Redeploy**).

---

## 3. Post-Deploy End-to-End Verification

Once both services are deployed:
1. Check proxied health & readiness through Vercel:
   ```bash
   curl -fsS https://<your-vercel-domain>/api/health
   curl -fsS https://<your-vercel-domain>/api/health/readiness
   ```
2. Open `https://<your-vercel-domain>` in a browser, register an astronaut account, create a mission, and confirm:
   - `marscope_session` (`HttpOnly`) and `marscope_csrf` cookies are set on the Vercel origin.
   - Mutating requests succeed with `X-CSRF-Token`.
   - Mission stream (`/api/missions/{id}/stream`) connects and receives live updates.
   - Restarting the Railway container preserves astronaut accounts, missions, and bootstrapped datasets on `/data/datasets`.

---

## 4. Known Architecture Limitations
1. **Single-Replica SQLite Persistence:** SQLite WAL on a Railway volume requires `replicas = 1`. Horizontal multi-instance scaling would require implementing and testing PostgreSQL compatibility (explicitly out of scope here).
2. **Vercel Rewrite Proxy Timeout for Long-Lived SSE:** Vercel's serverless/edge rewrite proxy imposes response duration limits (platform plan dependent). `EventSource` automatically reconnects on timeout, or for multi-hour uninterrupted streams an operator can connect directly to the Railway origin if CORS/cookies are configured for cross-site use.
3. **Large Dataset Acquisition Time/Bandwidth:** Running `--acquire` downloads real NASA PDS / UArizona / JPL GeoTIFFs onto the Railway volume; ensure the Railway volume has sufficient free space before acquiring optional products.
