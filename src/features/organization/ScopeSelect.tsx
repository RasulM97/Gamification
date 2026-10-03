import { useEffect, useState } from 'react'
import { api } from '../../api'
import { IS_DEMO } from '../../runtime'
import { useI18n } from '../../i18n'
import type { OrganizationUnit, WorkScope } from './OrganizationPanel'

export function ScopeSelect({ open, value, onChange }: { open: boolean; value: WorkScope; onChange: (scope: WorkScope) => void }) {
  const { t } = useI18n()
  const [units, setUnits] = useState<OrganizationUnit[]>([]), [error, setError] = useState(false)
  useEffect(() => {
    if (IS_DEMO || !open) return
    let live = true
    api.get<{ units: OrganizationUnit[] }>('/organization').then(result => { if (live) { setUnits(result.units); setError(false) } })
      .catch(() => { if (live) setError(true) })
    return () => { live = false }
  }, [open])
  if (IS_DEMO) return null
  return <label>{t('organization.scope')}
    <select value={value.kind === 'COMPANY' ? '' : value.id} onChange={e => {
      const unit = units.find(u => u.id === e.target.value)
      onChange(unit ? { kind: unit.kind, id: unit.id } : { kind: 'COMPANY' })
    }}>
      <option value="">{t('organization.COMPANY')}</option>
      {units.filter(u => u.status === 'ACTIVE').map(u => <option key={u.id} value={u.id}>{t('organization.' + u.kind)} · {u.name}</option>)}
    </select>
    {error && <span role="status">{t('organization.error')}</span>}
  </label>
}
