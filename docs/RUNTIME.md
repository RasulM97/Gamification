# Runtime integration

## Demo mode

Run `npm install` and `npm run dev` with no backend or database. This is the
default (`VITE_CVE_DATA_MODE=demo`) and preserves the deterministic reducer,
seed, persistence, and persona switcher.

## Server mode

Start PostgreSQL, then from `backend/` run `alembic upgrade head`, seed with
`python -c "from app.seed import run; run()"`, and start FastAPI with
`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
Run the frontend with `VITE_CVE_DATA_MODE=server VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev`
(PowerShell: `$env:VITE_CVE_DATA_MODE="server"; $env:VITE_API_BASE_URL="http://127.0.0.1:8000"; npm run dev`).
Use `CVE_DATABASE_URL` for the backend PostgreSQL URL and `cve_test` only for
automated tests.

Seeded development accounts are `dana@aster.demo` (ADMIN), `marcus@aster.demo`
(MANAGER), `priya@aster.demo`, `jonas@aster.demo`, and `aisha@aster.demo`
(EMPLOYEE); all use password `demo1234`. The API is at
`http://127.0.0.1:8000`; the frontend is normally at `http://127.0.0.1:5173`.

Server responses replace the store with authoritative bootstrap data after
every action. Bearer tokens are kept under `cve-server-token-v1`.

Use `useStore().login(email, password)` and `.logout()` for server sessions.
Uploads are sent as multipart form data when a browser `File` is selected;
server attachment IDs use `GET /api/files/{id}` for authenticated downloads.
