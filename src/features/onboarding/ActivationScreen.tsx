import { useEffect, useState } from 'react'
import { api } from '../../api'
import { useI18n } from '../../i18n'
import { Field } from '../../ui'
import { LocaleSwitcher } from '../../components/LocaleSwitcher'

export function ActivationScreen() {
  const { t } = useI18n()
  const [token, setToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '')
  const [password, setPassword] = useState(''), [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false), [done, setDone] = useState(false), [error, setError] = useState(false)
  useEffect(() => { history.replaceState(null, '', window.location.pathname) }, [])
  const valid = password.length >= 12 && new TextEncoder().encode(password).length <= 72 && password === confirm && !!token
  return <div className="login-wrap"><div className="login-card panel">
    <LocaleSwitcher /><h2>{t('setup.activate')}</h2>
    {done ? <><p role="status">{t('setup.activated')}</p><a className="btn primary" href="/">{t('auth.signIn')}</a></> :
      <form onSubmit={async e => {
        e.preventDefault(); if (!valid || busy) return
        setBusy(true); setError(false)
        try { await api.post('/auth/activate', { token, password }); setDone(true); setToken(''); setPassword(''); setConfirm('') }
        catch { setError(true) } finally { setBusy(false) }
      }}>
        <p>{t('setup.passwordHint')}</p>
        <Field label={t('auth.password')}><input type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} required /></Field>
        <Field label={t('setup.confirmPassword')}><input type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} required /></Field>
        {(!token || error) && <p role="alert" className="neg">{t('setup.activationError')}</p>}
        <button className="btn primary" disabled={!valid || busy}>{t('setup.activate')}</button>
      </form>}
  </div></div>
}
