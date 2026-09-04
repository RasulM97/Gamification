import { useEffect, useState } from 'react'
import { fetchDevPersonas } from '../api'
import type { DevPersona } from '../api'
import { useStore } from '../store'
import { Avatar } from '../ui'

/* DEV-ONLY test-account switcher (M1-D D2).
 *
 * Rendered only when runtime.DEV_TOOLS is true — import.meta.env.DEV &&
 * VITE_CVE_DEV_TOOLS=true && server mode. All three are build-time constants,
 * so production and demo builds dead-code-eliminate this entire feature.
 *
 * Security contract:
 *  - NO credentials ship in the bundle. The seeded account list (incl. the
 *    deterministic dev password) comes from the backend's DEV_MODE-only
 *    GET /api/dev/personas endpoint, which returns 404 when the server is not
 *    in dev mode.
 *  - Switching signs in through the REAL POST /api/auth/login endpoint — a
 *    genuine backend-authenticated session, never a master token or bypass.
 *  - It can never appear in the demo preview (DATA_MODE !== 'server'). */
export function DevAccountSwitcher({ onSwitched }: { onSwitched: () => void }) {
  const { login, me } = useStore()
  const [open, setOpen] = useState(false)
  const [personas, setPersonas] = useState<DevPersona[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    if (!open || personas) return
    fetchDevPersonas()
      .then(r => setPersonas(r.personas))
      .catch(e => setError(e instanceof Error ? e.message : 'Dev endpoint unavailable'))
  }, [open, personas])

  const choose = (p: DevPersona) => {
    if (busy) return
    setBusy(p.id); setError(null)
    login(p.email, p.password)
      .then(() => { setOpen(false); onSwitched() })
      .catch(e => setError(e instanceof Error ? e.message : 'Sign-in failed'))
      .finally(() => setBusy(null))
  }

  return (
    <div style={{ marginBottom: 8 }}>
      <button style={{ width: '100%' }} onClick={() => setOpen(o => !o)}
        title="Development tool — real sign-ins against the dev backend">
        ⇄ Switch test account <span className="faint" style={{ fontSize: 10.5 }}>dev</span>
      </button>
      {open && (
        <div className="user-pick" style={{ padding: 6 }} data-testid="dev-account-switcher">
          {!personas && !error && <div className="faint" style={{ padding: 8, fontSize: 12 }}>Loading seeded accounts…</div>}
          {error && <div className="neg" style={{ padding: 8, fontSize: 12 }}>⚠ {error}</div>}
          {personas?.map(p => (
            <button key={p.id} className={p.id === me?.id ? 'on' : ''} disabled={busy !== null}
              onClick={() => choose(p)}>
              <Avatar name={p.name} size={24} />
              <span className="meta"><b>{p.name}</b><small>{p.role} — {p.position}</small></span>
              {busy === p.id && <span className="faint" style={{ fontSize: 11 }}>signing in…</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
