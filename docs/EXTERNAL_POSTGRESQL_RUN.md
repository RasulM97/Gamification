# Running the CVE Backend Externally (Windows + PostgreSQL)

This guide runs the current FastAPI backend (`backend/`) on Windows with
PostgreSQL. The implementation baseline includes WS1–WS4; see [current status](PRODUCT.md#status).
Standalone demo mode needs none of these services. For pilot deployment, use
the [Pilot Runbook](OPERATIONS.md#contract-pilot-runbook) instead of development seeding.

## 1. Prerequisites

- **Python 3.12** (the verified backend runtime)
- **PostgreSQL 15+** installed and running (e.g. the EDB Windows installer), with a
  superuser you can log in as (default below: `postgres`)
- Git (to clone/copy this repository)

## 2. Virtual environment + dependencies

From the repository root, in PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Create the databases

Using `psql` (or pgAdmin):

```powershell
psql -U postgres -c "CREATE DATABASE cve;"
psql -U postgres -c "CREATE DATABASE cve_test;"
```

## 4. Environment variables

All settings use the `CVE_` prefix (see `backend/app/config.py`). Set them in
PowerShell (session-scoped) or create a `.env` file inside `backend/` (it is loaded
automatically):

```powershell
# Runtime database
$env:CVE_DATABASE_URL = "postgresql+psycopg2://postgres:YOURPASSWORD@localhost:5432/cve"

# Test database (used by pytest; without it tests try to start a user-space
# pgserver cluster, which is a Linux-oriented convenience — set this on Windows)
$env:CVE_TEST_DATABASE_URL = "postgresql+psycopg2://postgres:YOURPASSWORD@localhost:5432/cve_test"

# Security — REQUIRED outside development
$env:CVE_JWT_SECRET = "<locally-generated-secret-at-least-32-bytes>"

# Uploads (any writable folder)
$env:CVE_UPLOAD_DIR = "C:\cve-uploads"

# Demo persona quick-login + seed endpoint (dev/demo only; set to "false" in any real deployment)
$env:CVE_DEV_MODE = "true"

# Allowed frontend origins (comma-separated)
$env:CVE_CORS_ORIGINS = "http://localhost:5173,http://localhost:4173"
```

Equivalent `.env` file (place in `backend/.env`):

```
CVE_DATABASE_URL=postgresql+psycopg2://postgres:YOURPASSWORD@localhost:5432/cve
CVE_TEST_DATABASE_URL=postgresql+psycopg2://postgres:YOURPASSWORD@localhost:5432/cve_test
CVE_JWT_SECRET=<locally-generated-secret-at-least-32-bytes>
CVE_UPLOAD_DIR=C:\cve-uploads
CVE_DEV_MODE=true
CVE_CORS_ORIGINS=http://localhost:5173,http://localhost:4173
```

## 5. Run migrations (Alembic)

From `backend/` (with the venv activated):

```powershell
cd backend
alembic upgrade head
```

Expected repository head at E11: `eb01c9e2601`. Verify with `alembic heads` and
`alembic current`; this guide does not assert the state of an existing database.
The commands in each section assume its stated working directory; do not repeat
`cd backend` if already there.

## 6. Development data

With `CVE_DEV_MODE=true`, API startup calls `seed_if_empty` in a transaction.
Only an empty development database should be seeded. The current fixture is
maintained in `backend/app/seed.py`; do not call `run()` without its required
Session or use seed/reset commands against founder or pilot data. Development
accounts are test identities, not production credentials. For a real pilot,
use the provisioning workflow in [Pilot Runbook](OPERATIONS.md#contract-pilot-runbook).

## 7. Run the backend test suite

```powershell
cd backend
python -m pytest tests/ -v
```

This runs the backend suite against the disposable `CVE_TEST_DATABASE_URL`.
The latest recorded E11 result is 985 unique passing checks (982 full-suite
checks plus 3 workload cases run separately). See [testing](TESTING_ACCEPTANCE.md#contract-testing-readme)
for the exact recorded split and additional dedicated runners.

## 8. Concurrency tests only

```powershell
python -m pytest tests/test_concurrency.py -v
```

These tests exercise first-valid-claim races, partial-payout atomicity and
ledger invariants under parallel workers — they require the real PostgreSQL
test database.

## 9. Start the API server

```powershell
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or the convenience dev script (uses `CVE_DATABASE_URL` if set):

```powershell
python scripts/run_dev.py
```

## 10. URLs

- **Backend API:** http://localhost:8000 (API routes under `/api`, e.g. `/api/auth/login`)
- **Frontend demo mode (no backend needed):** `npm install && npm run dev` → http://localhost:5173
- **Frontend SERVER dev mode (talks to the backend above):**

  ```powershell
  npm run dev:server     # = vite dev --mode server
  ```

  This loads `.env.server` (`VITE_CVE_DATA_MODE=server` +
  `VITE_CVE_DEV_TOOLS=true`) and proxies same-origin `/api/*` to
  http://localhost:8000 (override with `$env:CVE_API_PROXY_TARGET`), so no
  other frontend configuration is needed. Sign in with a seeded account
  (using the development seed only), or use the account menu's
  **Switch test account** dev tool, which exchanges the authenticated development session through
  `/api/dev/switch/{user_id}`. The switcher exists only in this dev mode — never in
  demo mode, never without `VITE_CVE_DEV_TOOLS=true`, never in any
  production build.
- Server-mode attachments: task/review chips download the real stored bytes
  via `GET /api/files/{id}` with your auth token and open them in a new tab.
  The seed stores small real placeholder files, so this works immediately
  (e.g. open the approved "Q3 inventory audit" task and click
  `warehouse-A-map.pdf`).

## Notes

- `DEV_MODE=true` exposes `/api/dev/personas` and `/api/dev/reseed`. Never enable it
  outside development.
- The M0-B rule freeze is historical. Current behavior is defined by source,
  migrations and tests, including later approved capacity, visibility and signed
  ledger rules. See [architecture](ARCHITECTURE.md#contract-architecture) and [testing](TESTING_ACCEPTANCE.md#contract-testing-readme).
- The root `.venv` belongs to Graphify; preserve it and use `backend/.venv`.
- Automated fixtures truncate data. Use a dedicated disposable test database,
  never founder or pilot data. Do not commit local environment files or secrets.
