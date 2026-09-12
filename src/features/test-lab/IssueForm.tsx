import { useState } from 'react'
import { Field } from '../../ui'
import { useI18n } from '../../i18n'
import { operationLabel } from './testlab.presentation'
import type { UatEvent, IssueSeverity } from './testlab.types'
import type { NewIssue } from './testlab.store'

export function IssueForm({ events, onSave, onCancel }: { events: UatEvent[]; onSave: (issue: NewIssue) => void; onCancel: () => void }) {
  const { t } = useI18n()
  const [severity, setSeverity] = useState<IssueSeverity>('P2'), [title, setTitle] = useState(''), [description, setDescription] = useState(''), [related, setRelated] = useState('')
  return <form onSubmit={e => { e.preventDefault(); if (title.trim()) onSave({ severity, title: title.trim(), description: description.trim(), relatedOperation: related ? Number(related) : null }) }}>
    <Field label={t('testLab.severity')}><select value={severity} onChange={e => setSeverity(e.target.value as IssueSeverity)}>{(['P0','P1','P2','P3'] as const).map(sev => <option key={sev} value={sev}>{sev} — {t('testLab.severity.' + sev)}</option>)}</select></Field>
    <Field label={t('common.title')}><input required dir={title ? 'auto' : undefined} value={title} onChange={e => setTitle(e.target.value)}/></Field>
    <Field label={t('common.description')}><textarea dir={description ? 'auto' : undefined} value={description} onChange={e => setDescription(e.target.value)}/></Field>
    <Field label={t('testLab.related')}><select value={related} onChange={e => setRelated(e.target.value)}><option value="">—</option>{events.map(e => <option key={e.seq} value={e.seq}>#{e.seq} · {operationLabel(e.operationType ?? e.action)} · {e.actorName}</option>)}</select></Field>
    <div className="testlab-actions"><button className="btn" type="button" onClick={onCancel}>{t('common.cancel')}</button><button className="btn primary" disabled={!title.trim()}>{t('testLab.addIssue')}</button></div>
  </form>
}
