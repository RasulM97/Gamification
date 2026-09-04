/* Runtime mode (M1-A) — the ONLY place the data mode is decided.
 *
 *   VITE_CVE_DATA_MODE=demo    → DemoAdapter: frozen reducer + seed +
 *                                localStorage persistence (the sandbox
 *                                preview; no backend involved at all)
 *   VITE_CVE_DATA_MODE=server  → ApiAdapter: every mutation is a domain
 *                                endpoint call against the FastAPI backend;
 *                                PostgreSQL is authoritative (external env)
 *
 * Explicit configuration ONLY — never auto-detected from backend
 * availability. Anything that is not exactly the string "server" resolves
 * to demo, so the sandbox preview can never accidentally require a backend.
 */
export type DataMode = 'demo' | 'server'

export const DATA_MODE: DataMode =
  (import.meta.env.VITE_CVE_DATA_MODE as string | undefined) === 'server' ? 'server' : 'demo'

export const IS_DEMO = DATA_MODE === 'demo'

/* Dev-only test-account switcher (M1-D D2). All three conditions are
 * build-time constants, so in any production or demo build this folds to
 * false and the whole feature is dead-code-eliminated:
 *   import.meta.env.DEV          → only `vite dev`, never `vite build`
 *   VITE_CVE_DEV_TOOLS=true      → explicit opt-in
 *   DATA_MODE === 'server'       → never in the demo preview
 * The switcher holds NO credentials: it fetches the seeded account list from
 * the backend's DEV_MODE-only /dev/personas endpoint (404 in production) and
 * signs in through the real /auth/login endpoint. */
export const DEV_TOOLS =
  import.meta.env.DEV &&
  (import.meta.env.VITE_CVE_DEV_TOOLS as string | undefined) === 'true' &&
  DATA_MODE === 'server'

