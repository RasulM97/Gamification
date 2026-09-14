import { useState } from 'react'
import { useStore, IS_DEMO } from '../../store'
import { useI18n } from '../../i18n'
import { Field, roleKey } from '../../ui'
import type { PersonInput } from './operations'

const blank: PersonInput = { name: '', email: '', position: '', role: 'EMPLOYEE', capacity: 2 }
export function PeopleSetup() {
  const { state, setup } = useStore(), { t } = useI18n()
  const [person, setPerson] = useState(blank), [link, setLink] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState(false), [saved, setSaved] = useState(false)
  const run = async (userId?: string) => {
    setBusy(true); setError(false); setSaved(false); setLink('')
    try {
      const token = await setup(userId ? { type: 'activation', userId } : { type: 'person', person })
      if (token) setLink(`${window.location.origin}/activate#token=${encodeURIComponent(token)}`)
      setSaved(true); if (!userId) setPerson(blank)
    } catch { setError(true) } finally { setBusy(false) }
  }
  return <>
    <p className="dim">{t(IS_DEMO ? 'setup.demoPeople' : 'setup.peopleHint')}</p>
    <form onSubmit={e => { e.preventDefault(); if (!busy) void run() }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))', gap: 12 }}>
        <Field label={t('setup.name')}><input dir="auto" required maxLength={120} value={person.name} onChange={e => setPerson({ ...person, name: e.target.value })} /></Field>
        <Field label={t('auth.email')}><input type="email" dir="ltr" required maxLength={200} value={person.email} onChange={e => setPerson({ ...person, email: e.target.value })} /></Field>
        <Field label={t('common.position')}><input dir="auto" maxLength={120} value={person.position} onChange={e => setPerson({ ...person, position: e.target.value })} /></Field>
        <Field label={t('admin.systemRole')}><select value={person.role} onChange={e => setPerson({ ...person, role: e.target.value as PersonInput['role'] })}>
          <option value="EMPLOYEE">{t(roleKey('EMPLOYEE'))}</option><option value="MANAGER">{t(roleKey('MANAGER'))}</option>
        </select></Field>
        <Field label={t('capacity.label')}><input type="number" min={1} max={100} step={1} required value={person.capacity} onChange={e => setPerson({ ...person, capacity: +e.target.value })} /></Field>
      </div>
      <button className="btn primary" disabled={busy || !person.name.trim()}>{t('setup.addPerson')}</button>
    </form>
    {error && <p role="alert" className="neg">{t('setup.error')}</p>}
    {saved && <p role="status">{t('setup.saved')}</p>}
    {link && <div style={{ marginBlock: 16 }}><p>{t('setup.linkHint')}</p>
      <Field label={t('setup.activationLink')}><input readOnly dir="ltr" value={link} onFocus={e => e.target.select()} /></Field>
      <button className="btn" onClick={() => setLink('')}>{t('common.close')}</button>
    </div>}
    <ul>{state.users.map(u => <li key={u.id} style={{ marginBlock: 8 }}><b dir="auto">{u.name}</b> · {t(roleKey(u.role))}
      {u.activationPending && <> · {t('setup.pending')} <button className="btn" disabled={busy} onClick={() => void run(u.id)}>{t('setup.reissue')}</button></>}
    </li>)}</ul>
  </>
}
