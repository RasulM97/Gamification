import { useState } from 'react'
import { useStore, useMe } from '../store'
import { capacityLimit, activeCount } from '../domain/engine'
import type { Audience } from '../domain/engine'
import { needsSensitivityConfirmation, routingAudience } from '../domain/taskAccess'
import { useI18n } from '../i18n'
import { SensitivityGuard } from './SensitivityGuard'

export function ReassignInline({ taskId, assigneeId, assignMode, audience }: {
  taskId: string; assigneeId: string | null; assignMode: string; audience: Audience
}) {
  const { state, dispatch } = useStore(), me = useMe(), { t } = useI18n()
  const [pending, setPending] = useState<string | null>(null), [confirmed, setConfirmed] = useState(false)
  const task = state.tasks.find(t => t.id === taskId)!
  const targets = state.users.filter(u => u.role !== 'ADMIN' && u.active !== false && !u.activationPending)
  const target = targets.find(u => u.id === pending)
  const nextAudience = routingAudience(task, target)
  const sensitive = pending !== null && needsSensitivityConfirmation(task, nextAudience, target)
  const apply = (value: string, confirmation: boolean) => dispatch({ type: 'REASSIGN', taskId, by: me.id,
    assigneeId: value === '__all' ? null : value, sensitivityConfirmed: confirmation })
  return <div><select value={pending ?? (assignMode === 'SPECIFIC_EMPLOYEE' ? assigneeId ?? '' : '__all')}
    aria-label={t('accessibility.reassignTask')} onChange={e => {
      const value = e.target.value, user = targets.find(u => u.id === value)
      if (needsSensitivityConfirmation(task, routingAudience(task, user), user)) { setPending(value); setConfirmed(false) }
      else { apply(value, false); setPending(null) }
    }}>
    {audience !== 'PRIVATE' && <option value="__all">{t(audience === 'MANAGEMENT' ? 'task.assignment.availableAllManagers' : 'task.assignment.availableAllEmployees')}</option>}
    {targets.map(u => <option key={u.id} value={u.id} disabled={activeCount(state, u.id) >= capacityLimit(u)}>
      {t('task.assignOption', { name: u.name, used: activeCount(state, u.id), max: capacityLimit(u) })}
    </option>)}
  </select>
    <SensitivityGuard required={sensitive} confirmed={confirmed} onConfirm={setConfirmed} />
    {pending !== null && <><button className="btn primary" disabled={sensitive && !confirmed} onClick={() => { apply(pending, confirmed); setPending(null) }}>{t('common.saveChanges')}</button>
      <button className="btn" onClick={() => setPending(null)}>{t('common.cancel')}</button></>}
  </div>
}
