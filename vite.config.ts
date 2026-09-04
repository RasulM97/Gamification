import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { version } from './package.json'

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  /* Dev-server only (never shipped in any build): same-origin /api/* calls
     are proxied to the local FastAPI backend so the D1 URL contract
     ("VITE_API_BASE_URL unset → same-origin /api") works out of the box in
     `vite dev`. Target overridable via CVE_API_PROXY_TARGET. Demo mode makes
     zero /api requests, so this is inert there. */
  server: {
    proxy: {
      '/api': {
        target: process.env.CVE_API_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
