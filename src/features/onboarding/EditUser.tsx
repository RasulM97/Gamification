import { useState } from 'react'
import { useStore, useMe } from '../../store'
import type { User, Role } from '../../domain/engine'
import { userLifecycleRefusal } from '../../domain/userLifecycle'
import { useI18n } from '../../i18n'
import { Field, Modal, roleKey } from '../../ui'

export function EditUserButton({ user }: { user: User }) {
  const [open, setOpen] = useState(false), { t } = useI18n()
  return <><button className="btn" onClick={() => setOpen(true)}>{t('common.edit')}</button>
    {open && <EditUser user={user} onClose={() => setOpen(false)} />}</>
}

function EditUser({ user, onClose }: { user: User; onClose: () => void }) {
  const { state, dispatch } = useStore(), me = useMe(), { t } = useI18n()
  const [name, setName] = useState(user.name), [position, setPosition] = useState(user.position)
  const [role, setRole] = useState(user.role), [active, setActive] = useState(user.active !== false)
  const refusal = userLifecycleRefusal(state, user, role, active)
  return <Modal open onClose={onClose} title={t('integrity.editUser')}>
    <Field label={t('setup.name')}><input dir="auto" maxLength={120} value={name} onChange={e => setName(e.target.value)} /></Field>
    <Field label={t('common.position')}><input dir="auto" maxLength={120} value={position} onChange={e => setPosition(e.target.value)} /></Field>
    <Field label={t('admin.systemRole')}><select value={role} onChange={e => setRole(e.target.value as Role)}>
      {(['ADMIN', 'MANAGER', 'EMPLOYEE'] as const).map(r => <option key={r} value={r}>{t(roleKey(r))}</option>)}
    </select></Field>
    <label><input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)} />{t('integrity.accountActive')}</label>
    <p>{t('integrity.accountLifecycleHint')}</p>
    {refusal && <p role="alert" className="neg">{t(`integrity.error.${refusal}`)}</p>}
    <button className="btn primary" disabled={!name.trim() || !!refusal} onClick={() => {
      dispatch({ type: 'UPDATE_USER', by: me.id, userId: user.id, name, position, role, active }); onClose()
    }}>{t('common.saveChanges')}</button>
  </Modal>
}
