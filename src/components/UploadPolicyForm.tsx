import { useState } from 'react'
import { useStore, useMe } from '../store'
import { useI18n } from '../i18n'
import { Field } from '../ui'

/* Company-level upload policy editor (§18). */
export function UploadPolicyForm() {
  const { state, dispatch } = useStore()
  const me = useMe()
  const { t } = useI18n()
  const [perFile, setPerFile] = useState(String(state.settings.maxFileSizeMb))
  const [total, setTotal] = useState(String(state.settings.maxSubmissionTotalMb))
  const dirty = +perFile !== state.settings.maxFileSizeMb || +total !== state.settings.maxSubmissionTotalMb
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <Field label={t('admin.maxFileSize')}>
        <input type="number" min={1} max={100} value={perFile} onChange={e => setPerFile(e.target.value)} style={{ width: 130 }} />
      </Field>
      <Field label={t('admin.maxSubmissionTotal')}>
        <input type="number" min={1} max={500} value={total} onChange={e => setTotal(e.target.value)} style={{ width: 130 }} />
      </Field>
      <button className="btn primary" disabled={!dirty || !(+perFile > 0) || !(+total > 0)}
        style={{ marginBottom: 13 }}
        onClick={() => dispatch({
          type: 'UPDATE_SETTINGS', by: me.id,
          settings: { maxFileSizeMb: +perFile, maxSubmissionTotalMb: +total },
        })}>{t('admin.action.savePolicy')}</button>
    </div>
  )
}
