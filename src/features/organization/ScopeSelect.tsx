import { useI18n } from '../../i18n'
import { IS_DEMO } from '../../runtime'
import type { OrganizationUnit, WorkScope } from './OrganizationPanel'

/* WS4 round 2 (F2): the scope selector must not advertise authority the
 * backend refuses. Company-wide creation is admin-only; a manager creates
 * work only inside Teams/Projects they actively manage (active membership
 * with the manager flag). The backend stays authoritative — this is honest UI. */
export function creatableScopes(units: OrganizationUnit[], viewer: { id: string; role: string }) {
  const active = units.filter(u => u.status === 'ACTIVE')
  if (viewer.role !== 'MANAGER')
    return { units: active, allowCompany: true }
  return {
    units: active.filter(u =>
      u.memberships.some(m => m.userId === viewer.id && m.manager && m.leftAt === null)),
    allowCompany: false,
  }
}

export function ScopeSelect({ value, onChange, units, error, allowCompany }: {
  value: WorkScope; onChange: (scope: WorkScope) => void
  units: OrganizationUnit[]; error: boolean; allowCompany: boolean
}) {
  const { t } = useI18n()
  if (IS_DEMO) return null
  return <label>{t('organization.scope')}
    <select value={value.kind === 'COMPANY' ? '' : value.id} onChange={e => {
      const unit = units.find(u => u.id === e.target.value)
      onChange(unit ? { kind: unit.kind, id: unit.id } : { kind: 'COMPANY' })
    }}>
      {allowCompany
        ? <option value="">{t('organization.COMPANY')}</option>
        : <option value="" disabled>{t('organization.chooseScope')}</option>}
      {units.map(u => <option key={u.id} value={u.id}>{t('organization.' + u.kind)} · {u.name}</option>)}
    </select>
    {error && <span role="status">{t('organization.error')}</span>}
  </label>
}
