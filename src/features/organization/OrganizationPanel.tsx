/* F3/F4 (System Cohesion Sweep): organization management is a first-class
 * panel — it auto-loads on mount (no hidden "manage" button), renders honest
 * loading / empty / error states, and classifies failures:
 *   403/409 → authority or state rejection (final, no retry — retrying the
 *             same command cannot succeed);
 *   other   → transient/infrastructure error (explicit retry control).
 * Demo mode renders the deterministic fixture units read-only with a visible
 * note instead of returning null (F3: demo must not silently hide modules).
 */
import { useState } from 'react'
import { api, ApiError } from '../../api'
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { IS_DEMO } from '../../runtime'
import { Panel } from '../../ui'
import { governance } from '../governance/source'
import { useGovData } from '../governance/hooks'

export type WorkScope = { kind: 'COMPANY' } | { kind: 'TEAM' | 'PROJECT'; id: string }
export type OrganizationUnit = { id: string; kind: 'TEAM' | 'PROJECT'; name: string; status: 'ACTIVE' | 'CLOSED';
  memberships: { userId: string; manager: boolean; joinedAt: number; leftAt: number | null }[] }

const isRejection = (e: unknown) => e instanceof ApiError && (e.status === 403 || e.status === 409)

export function OrganizationPanel() {
  const { state } = useStore(), { t } = useI18n()
  const { data: units, loading, error, reload } = useGovData(() => governance.listOrgUnits())
  const [kind, setKind] = useState<'TEAM' | 'PROJECT'>('TEAM'), [name, setName] = useState('')
  const [busy, setBusy] = useState(false), [opError, setOpError] = useState<'reject' | 'error' | null>(null)
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true); setOpError(null)
    try { await work(); reload() }
    catch (e) { setOpError(isRejection(e) ? 'reject' : 'error') }
    finally { setBusy(false) }
  }
  return <Panel title={t('organization.title')}>
    {IS_DEMO && <p className="dim" role="note">{t('organization.demoNote')}</p>}
    {!!error && <p role="alert">
      {t(isRejection(error) ? 'organization.rejected' : 'organization.error')}
      {!isRejection(error) && <> <button className="btn" onClick={reload}>{t('common.retry')}</button></>}
    </p>}
    {loading && !error && <p role="status">{t('common.loading')}</p>}
    {!!opError && <p role="alert">{t(opError === 'reject' ? 'organization.rejected' : 'organization.error')}</p>}
    {units && !loading && !error && <>
      {units.length === 0 && <p className="dim">{t('organization.empty')}</p>}
      {!IS_DEMO && <form onSubmit={e => { e.preventDefault(); void run(async () => { await api.post('/organization/' + kind, { name }); setName('') }) }}>
        <label>{t('organization.kind')} <select value={kind} disabled={busy} onChange={e => setKind(e.target.value as typeof kind)}>
          <option value="TEAM">{t('organization.TEAM')}</option><option value="PROJECT">{t('organization.PROJECT')}</option>
        </select></label>
        <label>{t('common.title')} <input value={name} maxLength={120} disabled={busy} onChange={e => setName(e.target.value)} /></label>
        <button className="btn" disabled={busy || !name.trim()}>{t('organization.create')}</button>
      </form>}
      {units.map(unit => <section key={unit.id} style={{ paddingBlock: 12 }}>
        <h3>{unit.name} · {t('organization.' + unit.kind)}</h3>
        {unit.status === 'CLOSED' ? <p>{t('organization.closed')}</p> : <>
          {!IS_DEMO && <button className="btn" disabled={busy} onClick={() => run(() => api.post(`/organization/${unit.kind}/${unit.id}/close`))}>{t('organization.close')}</button>}
          {state.users.filter(u => u.active !== false && !u.activationPending).map(user => {
            const member = unit.memberships.find(m => m.userId === user.id && m.leftAt === null)
            const update = (active: boolean, manager: boolean) => run(() => api.put(`/organization/${unit.kind}/${unit.id}/members/${user.id}`, { active, manager }))
            return <div key={user.id} style={{ display: 'flex', gap: 12, paddingBlock: 4 }}>
              <label><input type="checkbox" checked={!!member} disabled={busy || IS_DEMO} onChange={e => update(e.target.checked, false)} /> {user.name}</label>
              {member && user.role !== 'EMPLOYEE' && <label><input type="checkbox" checked={member.manager} disabled={busy || IS_DEMO}
                onChange={e => update(true, e.target.checked)} /> {t('organization.manager')}</label>}
            </div>
          })}
        </>}
      </section>)}
    </>}
  </Panel>
}
