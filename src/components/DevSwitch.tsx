import { useI18n } from '../i18n'
import { errorText } from '../presentation/errorText'
import { useEffect, useState } from 'react'
import { fetchDevPersonas } from '../api'
import type { DevPersona } from '../api'
import { useStore } from '../store'
import { Avatar } from '../ui'

export function DevAccountSwitcher({ onSwitched }: { onSwitched: () => void }) {
  const { switchDevAccount, me } = useStore()
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [personas, setPersonas] = useState<DevPersona[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setPersonas(null)
    fetchDevPersonas()
      .then(r => setPersonas(r.personas))
      .catch(e => setError(errorText(e)))
  }, [open])

  const choose = (p: DevPersona) => {
    if (busy) return
    setBusy(p.id); setError(null)
    switchDevAccount(p.id)
      .then(() => { setOpen(false); onSwitched() })
      .catch(e => setError(errorText(e)))
      .finally(() => setBusy(null))
  }

  return (
    <div style={{ marginBottom: 8 }}>
      <button style={{ width: '100%' }} onClick={() => setOpen(o => !o)}
        title={t('integrity.devSwitch')}>
        {t('integrity.devSwitch')} <span className="faint">dev</span>
      </button>
      {open && (
        <div className="user-pick" style={{ padding: 6 }} data-testid="dev-account-switcher">
          {!personas && !error && <div className="faint" style={{ padding: 8, fontSize: 12 }}>{t('common.loading')}</div>}
          {error && <div className="neg" style={{ padding: 8, fontSize: 12 }}>⚠ {error}</div>}
          {personas?.map(p => (
            <button key={p.id} className={p.id === me?.id ? 'on' : ''} disabled={busy !== null}
              onClick={() => choose(p)}>
              <Avatar name={p.name} size={24} />
              <span className="meta"><b>{p.name}</b><small>{p.role} — {p.position}</small></span>
              {busy === p.id && <span className="faint" style={{ fontSize: 11 }}>{t('common.loading')}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
