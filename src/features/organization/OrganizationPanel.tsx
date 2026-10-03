import { useState } from 'react'
import { api } from '../../api'
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { IS_DEMO } from '../../runtime'
import { Panel } from '../../ui'

export type WorkScope = { kind: 'COMPANY' } | { kind: 'TEAM' | 'PROJECT'; id: string }
export type OrganizationUnit = { id: string; kind: 'TEAM' | 'PROJECT'; name: string; status: 'ACTIVE' | 'CLOSED';
  memberships: { userId: string; manager: boolean; joinedAt: number; leftAt: number | null }[] }

export function OrganizationPanel() {
  const { state } = useStore(), { t } = useI18n()
  const [units, setUnits] = useState<OrganizationUnit[] | null>(null)
  const [kind, setKind] = useState<'TEAM' | 'PROJECT'>('TEAM'), [name, setName] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState(false)
  const load = async () => setUnits((await api.get<{ units: OrganizationUnit[] }>('/organization')).units)
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true); setError(false)
    try { await work(); await load() } catch { setError(true) } finally { setBusy(false) }
  }
  if (IS_DEMO) return null
  return <Panel title={t('organization.title')}>
    {error && <p role="alert">{t('organization.error')}</p>}
    {!units ? <button className="btn" disabled={busy} onClick={() => run(load)}>{t('organization.manage')}</button> : <>
      <form onSubmit={e => { e.preventDefault(); void run(async () => { await api.post('/organization/' + kind, { name }); setName('') }) }}>
        <label>{t('organization.kind')} <select value={kind} disabled={busy} onChange={e => setKind(e.target.value as typeof kind)}>
          <option value="TEAM">{t('organization.TEAM')}</option><option value="PROJECT">{t('organization.PROJECT')}</option>
        </select></label>
        <label>{t('common.title')} <input value={name} maxLength={120} disabled={busy} onChange={e => setName(e.target.value)} /></label>
        <button className="btn" disabled={busy || !name.trim()}>{t('organization.create')}</button>
      </form>
      {units.map(unit => <section key={unit.id} style={{ paddingBlock: 12 }}>
        <h3>{unit.name} · {t('organization.' + unit.kind)}</h3>
        {unit.status === 'CLOSED' ? <p>{t('organization.closed')}</p> : <>
          <button className="btn" disabled={busy} onClick={() => run(() => api.post(`/organization/${unit.kind}/${unit.id}/close`))}>{t('organization.close')}</button>
          {state.users.filter(u => u.active !== false && !u.activationPending).map(user => {
            const member = unit.memberships.find(m => m.userId === user.id && m.leftAt === null)
            const update = (active: boolean, manager: boolean) => run(() => api.put(`/organization/${unit.kind}/${unit.id}/members/${user.id}`, { active, manager }))
            return <div key={user.id} style={{ display: 'flex', gap: 12, paddingBlock: 4 }}>
              <label><input type="checkbox" checked={!!member} disabled={busy} onChange={e => update(e.target.checked, false)} /> {user.name}</label>
              {member && user.role !== 'EMPLOYEE' && <label><input type="checkbox" checked={member.manager} disabled={busy}
                onChange={e => update(true, e.target.checked)} /> {t('organization.manager')}</label>}
            </div>
          })}
        </>}
      </section>)}
    </>}
  </Panel>
}
