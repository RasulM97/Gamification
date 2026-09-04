# Running the CVE Backend Externally (Windows + PostgreSQL)

This document covers running the recovered M1 backend (`backend/`) on your own
Windows machine with a real PostgreSQL server. **None of these steps are for the
Kimi sandbox** — the sandbox preview runs frontend-only with the demo adapter and
must never start PostgreSQL, Alembic, or FastAPI.

## 1. Prerequisites

- **Python 3.12** (3.11+ works; 3.12 is what the backend was developed and tested on)
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
$env:CVE_JWT_SECRET = "generate-a-long-random-string"

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
CVE_JWT_SECRET=generate-a-long-random-string
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

Expected head revision: `bce2aa82978d` (initial schema).

## 6. Seed deterministic demo data

```powershell
python -c "from app.seed import run; run()"
```

This creates the demo company, the 5 personas (dana/marcus/priya/jonas/aisha,
password `demo1234`), 10 tasks and 6 rewards.

## 7. Run the backend test suite

```powershell
cd backend
python -m pytest tests/ -v
```

This runs all 30 backend tests (domain parity, API lifecycle, economy/tenant
isolation) against `CVE_TEST_DATABASE_URL`.

## 8. Concurrency tests only

```powershell
python -m pytest tests/test_concurrency.py -v
```

These 5 tests exercise first-valid-claim races, partial-payout atomicity and
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
  (e.g. `dana@aster.demo` / `demo1234`), or use the account menu's
  **Switch test account** dev tool, which performs real logins through
  `/api/auth/login`. The switcher exists only in this dev mode — never in
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
- The frozen M0-B domain rules remain the canonical behavior spec; the backend's
  `app/domain.py` is the server-side port of those rules, parity-tested by
  `tests/test_domain.py`.
