import { useState } from 'react'
import { useStore } from '../store'
import { Field } from '../ui'
import { useI18n } from '../i18n'
import { LocaleSwitcher } from './LocaleSwitcher'

/* Login screen (server mode, M1-A) — real authentication only. No demo
   personas, no one-click language, no role simulation: this screen renders
   exclusively in server mode, where identity must look and be real.
   Seeded development credentials remain documented in
   docs/EXTERNAL_POSTGRESQL_RUN.md for manual sign-in — not presented here. */
export function LoginScreen() {
  const { t: tr } = useI18n()
  const { login } = useStore()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const doLogin = (e: string, p: string) => {
    setBusy(true); setError(null)
    login(e, p)
      .catch(err => setError(err?.message ?? tr('auth.loginFailed')))
      .finally(() => setBusy(false))
  }

  return (
    <div className="login-wrap">
      <div style={{ position: 'fixed', top: 14, insetInlineEnd: 14, zIndex: 5 }}><LocaleSwitcher /></div>
      <div className="login-card panel">
        <div className="brand" style={{ marginBottom: 4 }}>
          <div className="logo"><span className="mark">◈</span>{tr('app.name')}</div>
          <div className="co"><span dir="auto">Aster Dynamics</span> · {tr('app.pilotBuild')}</div>
        </div>
        <p className="dim" style={{ fontSize: 13, margin: '10px 0 18px' }}>
          {tr('auth.intro')}
        </p>
        <form onSubmit={e => { e.preventDefault(); if (!busy && email && password) doLogin(email, password) }}>
          <Field label={tr('auth.email')}>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              placeholder={tr('auth.emailPlaceholder')} autoFocus autoComplete="username" />
          </Field>
          <Field label={tr('auth.password')}>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="••••••••" autoComplete="current-password" />
          </Field>
          {error && <div className="neg" style={{ fontSize: 12.5, marginBottom: 10 }} dir="auto">⚠ {error}</div>}
          <button className="btn primary" type="submit" disabled={busy || !email || !password}
            style={{ width: '100%' }}>
            {busy ? tr('auth.signingIn') : tr('auth.signIn')}
          </button>
        </form>
      </div>
    </div>
  )
}
