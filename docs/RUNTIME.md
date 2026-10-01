# Runtime integration through E11

## Demo mode

From the repository root, run `npm ci` and `npm run dev`. Any
`VITE_CVE_DATA_MODE` value other than exactly `server` selects demo mode.
The demo uses its TypeScript reducer, seed, browser persistence and persona
switcher. It needs no backend and does not expose the entire E7–E11 API surface.

## Server mode

Follow [local PostgreSQL setup](EXTERNAL_POSTGRESQL_RUN.md), using a backend
virtual environment separate from the root Graphify `.venv`. Configure
`CVE_DATABASE_URL`, uploads, origins and authentication locally; never copy
actual credentials into tracked documentation. From `backend/`:

```sh
alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Current repository head: `eb01c9e2601`. Reachability: `/api/health` and `/docs`.
This does not assert that a local process or temporary public tunnel is running.
Development mode may seed an empty database. For a real pilot, use
[Pilot Runbook](PILOT_RUNBOOK.md): non-development startup never seeds and
requires an explicit strong JWT secret. Do not run development seed/reset tools
against pilot data.

From the root, `npm run dev:server` loads the server-mode Vite configuration.
`/api` is proxied to the configured backend (`CVE_API_PROXY_TARGET`, default
`http://localhost:8000`). For a separate-origin build, configure
`VITE_API_BASE_URL` and backend CORS deliberately. No availability auto-detection
changes the chosen runtime mode.

Server mode uses real login and authoritative bootstrap/mutation responses.
The auth token storage key is `cve-token` (`src/api.ts`); browser preferences are
also local, but persisted demo domain state is not server authority. Uploads
send multipart bytes; authenticated downloads use `/api/files/{id}`.
The test-account switcher requires Vite development mode, server mode and
`VITE_CVE_DEV_TOOLS=true`; it is not a production identity mechanism.

Managed, self-hosted and headless access share the same server contracts.
See [architecture](ARCHITECTURE.md) and [recorded validation](testing/README.md).
