# CVE Runtime Modes (M1-A)

The frontend has two explicit data runtimes, selected at build time by one
environment variable. **Nothing is auto-detected** — the mode is whatever
`VITE_CVE_DATA_MODE` says, and any value other than exactly `server` is demo.

## DEMO mode (default — Kimi sandbox preview, local static preview)

```
VITE_CVE_DATA_MODE=demo        # or simply unset
```

- Frozen M0-B reducer + seed + localStorage persistence (`cve-demo-state-v1`,
  `cve-demo-me-v1`). No network, no backend, no database.
- Persona switcher switches the demo identity locally.
- Attachments: metadata only; opening a chip shows the honest demo preview
  document.
- All 114 domain tests, TypeScript, production build, and the 13 demo E2E
  scenarios validate this mode. The demo build contains **zero `fetch` calls**
  (verified per build by bundle inspection).

## SERVER mode (external PostgreSQL-capable environment ONLY)

```
npm run dev:server        # vite dev --mode server → loads .env.server:
                          #   VITE_CVE_DATA_MODE=server
                          #   VITE_CVE_DEV_TOOLS=true   (dev switcher opt-in)
```

In `vite dev`, same-origin `/api/*` is proxied to the local backend
(`http://localhost:8000` by default; override with `CVE_API_PROXY_TARGET`),
so no `VITE_API_BASE_URL` is needed for local development. For a server-mode
**build** pointed at a backend on another origin, set
`VITE_API_BASE_URL=https://host` and every request (including file download)
goes to `${VITE_API_BASE_URL}/api/...`.

- Real sessions: `POST /api/auth/login`, token in localStorage (`cve-token`),
  `GET /api/auth/me` on boot, `GET /api/bootstrap` hydration; mutations map
  1:1 to domain endpoints and each response replaces the client state.
- The backend is authoritative for permissions, ownership, status, verified
  progress, payout, ledger, wallet, reward stock, visibility, and cycles.
  None of those calculations exist in React.
- Browser storage holds only the auth token — no domain state.
- No persona simulation anywhere: the login screen is a plain
  email/password form, and the account menu offers only Sign out. The single
  exception is the dev-only account switcher (M1-D D2), which exists solely
  in `npm run dev:server` (`vite dev` + `VITE_CVE_DEV_TOOLS=true` + server
  mode — all three required). It lists the seeded accounts from the
  backend's DEV_MODE-only `GET /api/dev/personas` endpoint and signs in
  through the real `POST /api/auth/login`. It is dead-code-eliminated from
  every production and demo build and never ships credentials.
- Seeded development credentials are documented in
  `docs/EXTERNAL_POSTGRESQL_RUN.md` for manual sign-in.
- Attachments upload as real multipart bytes and download via
  `GET /api/files/{id}` with the auth token (`Authorization: Bearer`),
  opened from the server-provided attachment `id` — never mixed with the
  demo metadata preview.
- Requires the dormant backend in `backend/` — see
  `docs/EXTERNAL_POSTGRESQL_RUN.md`. **SERVER mode runtime is NOT validated
  in the sandbox**; only a static contract audit (adapter ↔ routes) is done
  here.

## Boundary shape

- `src/runtime.ts` — the only place the mode is decided (`DATA_MODE`,
  `IS_DEMO`).
- `src/store.tsx` — the data boundary. `StoreProvider` selects
  `useDemoStore()` (the M0-B reducer/localStorage implementation, unchanged
  behavior) or `useServerStore()` (the API-backed implementation). Both
  expose the identical context contract (`state`, `dispatch`, `meId`,
  `setMeId`, `reset`, `persistError`, plus server-mode auth fields), so no
  view knows which mode is active.
- `src/api.ts` — the only network code in the app (inert in demo builds).
- `src/App.tsx` — the login gate renders **only** in server mode; demo mode
  renders the shell directly, exactly as M0-B.

## Domain file protection

`src/domain/reducer.ts` and its 114 tests are byte-untouched. The single
`model.ts` change (optional `Attachment.id` / `Attachment.file` fields) is
integration mechanics only — the reducer never reads or writes them.
