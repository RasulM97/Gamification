import { useState } from 'react'
import { useMe, useStore } from '../store'
import { WORKSPACE_TOOLS } from '../runtime'
import { Field, Modal } from '../ui'
import { useI18n } from '../i18n'

export function WorkspaceControls() {
  const { dispatch } = useStore(), me = useMe(), { t } = useI18n()
  const [open, setOpen] = useState(false), [confirmation, setConfirmation] = useState('')
  if (!WORKSPACE_TOOLS || me.role !== 'ADMIN') return null
  return <div data-testid="workspace-controls" style={{ marginTop: 20 }}>
    <p className="dim">{t('admin.clearTestWorkspaceDescription')}</p>
    <button className="btn danger" onClick={() => { setConfirmation(''); setOpen(true) }}>{t('admin.clearTestWorkspace')}</button>
    <Modal open={open} onClose={() => setOpen(false)} title={t('admin.clearTestWorkspace')}>
      <p>{t('admin.clearTestWorkspaceWarning')}</p>
      <Field label={t('admin.clearTestWorkspaceConfirmLabel')}>
        <input type="text" autoFocus dir="ltr" autoComplete="off" value={confirmation} onChange={event => setConfirmation(event.target.value)}/>
      </Field>
      <div className="testlab-actions">
        <button className="btn" onClick={() => setOpen(false)}>{t('common.cancel')}</button>
        <button className="btn danger" disabled={confirmation !== 'CLEAR'} onClick={() => {
          dispatch({ type: 'CLEAR_TEST_WORKSPACE', by: me.id }); setOpen(false)
        }}>{t('admin.clearWorkspace')}</button>
      </div>
    </Modal>
  </div>
}
