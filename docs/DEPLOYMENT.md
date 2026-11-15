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
