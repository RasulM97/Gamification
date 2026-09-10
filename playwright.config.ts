import { defineConfig } from '@playwright/test'

/* Compact E2E smoke suite (M0-B) — critical flows only, not visual detail.
   Two dev servers: demo mode (4173, default) and server+devtools mode
   (4321, `vite --mode server` — its /api traffic is intercepted at the API
   contract by e2e/m1d-server.spec.ts, since PostgreSQL cannot run here). */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  workers: 1,
  use: { headless: true },
  webServer: [
    {
      command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173 --strictPort',
      url: 'http://127.0.0.1:4173',
      timeout: 60_000,
    },
    {
      command: 'node node_modules/vite/bin/vite.js --mode server --host 127.0.0.1 --port 4321 --strictPort',
      url: 'http://127.0.0.1:4321',
      timeout: 60_000,
    },
  ],
  projects: [
    {
      name: 'demo',
      testIgnore: '**/*-server.spec.ts',
      use: { baseURL: 'http://127.0.0.1:4173' },
    },
    {
      name: 'server-dev',
      testMatch: '**/*-server.spec.ts',
      use: { baseURL: 'http://127.0.0.1:4321' },
    },
  ],
})
