import { useState } from 'react'
import { useStore } from '../store'
import { Field } from '../ui'

/* Login screen (server mode, M1-A) — real authentication only. No demo
   personas, no one-click language, no role simulation: this screen renders
   exclusively in server mode, where identity must look and be real.
   Seeded development credentials remain documented in
   docs/EXTERNAL_POSTGRESQL_RUN.md for manual sign-in — not presented here. */
export function LoginScreen() {
  const { login } = useStore()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const doLogin = (e: string, p: string) => {
    setBusy(true); setError(null)
    login(e, p)
      .catch(err => setError(err?.message ?? 'Login failed'))
      .finally(() => setBusy(false))
  }

  return (
    <div className="login-wrap">
      <div className="login-card panel">
        <div className="brand" style={{ marginBottom: 4 }}>
          <div className="logo"><span className="mark">◈</span>Corporate Virtual Economy</div>
          <div className="co">Aster Dynamics · pilot</div>
        </div>
        <p className="dim" style={{ fontSize: 13, margin: '10px 0 18px' }}>
          Sign in to your workspace. Coins, tasks and reviews live on the server now —
          every action is verified there.
        </p>
        <form onSubmit={e => { e.preventDefault(); if (!busy && email && password) doLogin(email, password) }}>
          <Field label="Email">
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@company.com" autoFocus autoComplete="username" />
          </Field>
          <Field label="Password">
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="••••••••" autoComplete="current-password" />
          </Field>
          {error && <div className="neg" style={{ fontSize: 12.5, marginBottom: 10 }}>⚠ {error}</div>}
          <button className="btn primary" type="submit" disabled={busy || !email || !password}
            style={{ width: '100%' }}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
