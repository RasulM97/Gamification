import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useMe, useStore } from '../store'
import { activeCount, capacityLimit, canEditCapacity, validCapacity, type User } from '../domain/engine'
import { useI18n } from '../i18n'
import { Field, Modal } from '../ui'

/** Shared compact control in the existing People/operations tables. */
export function CapacityControl({ user }: { user: User }) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const { t } = useI18n()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const limit = capacityLimit(user)
  const active = activeCount(state, user.id)
  const editable = canEditCapacity(me, user)
  if (user.role === 'ADMIN') return <span data-testid={`capacity-${user.id}`}>{t('capacity.notApplicable')}</span>
  return <div className="capacity-control" onClick={e => e.stopPropagation()} data-testid={`capacity-${user.id}`}>
    <span className={active >= limit ? 'warn num' : 'num'}>{t('capacity.usage', { active: '\u2066' + active, limit: limit + '\u2069' })}</span>
    {editable && <button className="btn"
      aria-label={t('capacity.editFor', { name: user.name })}
      onClick={() => { setValue(String(limit)); setEditing(true) }}>{t('capacity.label')}</button>}
    {createPortal(<Modal open={editing} onClose={() => setEditing(false)} title={<>{t('capacity.label')} · <bdi>{user.name}</bdi></>}>
      <Field label={t('capacity.label')} hint={t('capacity.range')}>
        <input type="number" min={1} max={100} step={1} value={value}
          aria-label={t('capacity.label')} onChange={e => setValue(e.target.value)} />
      </Field>
      <p className="dim">{t('capacity.preserveWork')}</p>
      <button className="btn primary" disabled={!validCapacity(Number(value)) || Number(value) === limit}
        onClick={() => { dispatch({ type: 'UPDATE_CAPACITY', by: me.id, userId: user.id, maxActiveTasks: Number(value) }); setEditing(false) }}>
        {t('common.saveChanges')}
      </button>
    </Modal>, document.body)}
  </div>
}
