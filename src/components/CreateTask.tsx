import { useState } from 'react'
import { useStore, useMe } from '../store'
import { PRIORITIES, MAX_ACTIVE, activeCount } from '../domain/engine'
import type { Attachment, Audience, Priority } from '../domain/engine'
import { AttachField, Coin, DateInput, Field, Modal, PriBadge, Seg, fmtDate } from '../ui'
import { useI18n } from '../i18n'

/* Create Task follows the canonical four-question structure; economy never
   visually dominates the meaning of the work. */
export function CreateTaskModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t: tr } = useI18n()
  const { state, dispatch } = useStore()
  const me = useMe()
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [audience, setAudience] = useState<Audience>('EMPLOYEES')
  const [mode, setMode] = useState<'all' | 'specific'>('all')
  const [assignee, setAssignee] = useState('')
  const [priority, setPriority] = useState<Priority>('NORMAL')
  const [deadline, setDeadline] = useState('')
  const [reward, setReward] = useState('20')
  /* Confirmation step: ownership, deadline, priority and economic value are
     summarised before the task is actually created. */
  const [confirming, setConfirming] = useState(false)
  /* Reference files can travel with the brief from the very start. */
  const [files, setFiles] = useState<Attachment[]>([])

  /* Management tasks belong to managers only (the founder/admin arranges and
     reviews, never owns work); PRIVATE tasks are one-to-one with any chosen
     person — employee or manager — hidden from everyone else. */
  const targets = state.users.filter(u =>
    (audience === 'EMPLOYEES' ? u.role === 'EMPLOYEE'
      : audience === 'MANAGEMENT' ? u.role === 'MANAGER'
      : u.role !== 'ADMIN') && u.id !== me.id)
  const valid = title.trim().length > 0 && desc.trim().length > 0
    && (audience === 'PRIVATE' ? !!assignee : mode === 'all' || assignee) && +reward > 0

  const create = () => {
    dispatch({
      type: 'CREATE_TASK', by: me.id,
      title: title.trim(), description: desc.trim(),
      priority, deadline: deadline || null, reward: +reward, audience,
      assignMode: mode === 'all' && audience !== 'PRIVATE' ? 'ALL_EMPLOYEES' : 'SPECIFIC_EMPLOYEE',
      assigneeId: (mode === 'specific' || audience === 'PRIVATE') ? assignee : null,
      attachments: files,
    })
    setTitle(''); setDesc(''); setAudience('EMPLOYEES'); setMode('all'); setAssignee(''); setPriority('NORMAL'); setDeadline(''); setReward('20')
    setFiles([]); setConfirming(false)
    onClose()
  }

  const assigneeUser = targets.find(u => u.id === assignee)
  const closeAll = () => { setConfirming(false); onClose() }

  return (
    <Modal open={open} onClose={closeAll} wide
      dirty={!!(title.trim() || desc.trim() || files.length > 0)}
      title={<>{tr('task.action.create')}<small>{confirming ? tr('task.createSubConfirm') : tr('task.createSub')}</small></>}>
      {confirming ? (
        <div>
          <div className="panel" style={{ padding: '12px 14px', marginBottom: 14 }}>
            <b style={{ fontSize: 14 }} dir="auto">{title.trim()}</b>
            <div className="dim" dir="auto" style={{ fontSize: 12.5, marginTop: 6, lineHeight: 1.55, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{desc.trim()}</div>
          </div>
          <div className="summary">
            <div className="srow"><span>{tr('common.audience')}</span><b>{tr(audience === 'MANAGEMENT' ? 'task.audience.management' : audience === 'PRIVATE' ? 'task.audience.privateOnePerson' : 'task.audience.employees')}</b></div>
            <div className="srow"><span>{tr('task.field.ownership')}</span><b dir="auto">{audience === 'PRIVATE'
              ? tr('task.assignment.privateTo', { assignee: assigneeUser?.name ?? '—' })
              : mode === 'all'
                ? (audience === 'MANAGEMENT' ? tr('task.assignment.managementPoolFirst') : tr('task.assignment.marketplaceFirst'))
                : tr('task.assignment.assignedTo', { assignee: assigneeUser?.name ?? '—' })}</b></div>
            {files.length > 0 && (
              <div className="srow"><span>{tr('common.attachments')}</span>
                <span style={{ display: 'flex', gap: 5, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {files.map((f, i) => <span key={i} className="chip" dir="auto">📎 {f.name}</span>)}
                </span>
              </div>
            )}
            <div className="srow"><span>{tr('common.priority')}</span><PriBadge p={priority} /></div>
            <div className="srow"><span>{tr('common.deadline')}</span><b>{/^\d{4}-\d{2}-\d{2}$/.test(deadline) ? fmtDate(deadline) : tr('date.noDeadline')}</b></div>
            <div className="srow"><span>{tr('task.field.economicValue')}</span><Coin n={+reward} /></div>
          </div>
          <div className="actionbar" style={{ position: 'static', margin: '14px -18px -18px' }}>
            <button className="btn" onClick={() => setConfirming(false)}>{tr('task.action.backEdit')}</button>
            <button className="btn primary" onClick={create}>{tr('task.action.confirmCreate')}</button>
          </div>
        </div>
      ) : (
      <>
      <div className="form-sec">
        <span className="eyebrow">{tr('task.field.whatNeedsDone')}</span>
        <Field label={tr('common.title')}>
          <input type="text" value={title} onChange={e => setTitle(e.target.value)}
            placeholder={tr('task.placeholder.title')} autoFocus />
        </Field>
        <Field label={tr('common.description')} hint={tr('task.help.descriptionHint')}>
          <textarea value={desc} onChange={e => setDesc(e.target.value)} style={{ minHeight: 96 }}
            placeholder={tr('task.placeholder.description')} />
        </Field>
        {/* Brief files: specs, templates, source data — attached at creation,
            visible to everyone who works on the task. */}
        <AttachField files={files} onChange={setFiles} settings={state.settings}
          label={tr('task.field.briefAttachments', { maxFileSizeMb: state.settings.maxFileSizeMb })} />
      </div>

      <div className="form-sec">
        <span className="eyebrow">{tr('task.field.whoCanDo')}</span>
        <Seg value={audience} onChange={v => { setAudience(v as Audience); setAssignee('') }}
          options={[
            { v: 'EMPLOYEES', label: tr('task.audience.employees') },
            { v: 'PRIVATE', label: tr('task.audience.private') },
            { v: 'MANAGEMENT', label: tr('task.audience.management') },
          ]} />
        {audience === 'MANAGEMENT' && (
          <div className="faint" style={{ fontSize: 11.5, marginTop: 7 }}>
            {tr('task.audienceHint.managementEarn')}
          </div>
        )}
        {audience === 'PRIVATE' && (
          <div className="faint" style={{ fontSize: 11.5, marginTop: 7 }}>
            {tr('task.audienceHint.privateLists')}
          </div>
        )}
        {audience !== 'PRIVATE' && (
        <div className="choice" style={{ marginTop: 10 }}>
          <button className={mode === 'all' ? 'on' : ''} onClick={() => setMode('all')}>
            <b>{audience === 'MANAGEMENT' ? tr('task.assignment.availableManagers') : tr('task.assignment.availableEmployees')}</b>
            <small>{tr(audience === 'MANAGEMENT' ? 'task.assignment.publishedManagement' : 'task.assignment.publishedMarketplace')}</small>
          </button>
          <button className={mode === 'specific' ? 'on' : ''} onClick={() => setMode('specific')}>
            <b>{audience === 'MANAGEMENT' ? tr('task.assignment.specificManager') : tr('task.assignment.specificEmployee')}</b>
            <small>{tr('task.assignment.assignedDirectlyHint')}</small>
          </button>
        </div>
        )}
        {(mode === 'specific' || audience === 'PRIVATE') && (
          <div style={{ marginTop: 11 }}>
            <Field label={tr('common.assignee')} hint={tr('task.help.workloadShown')}>
              <select value={assignee} onChange={e => setAssignee(e.target.value)}>
                <option value="">{tr(audience === 'MANAGEMENT' ? 'task.chooseManager' : audience === 'PRIVATE' ? 'task.choosePersonEllipsis' : 'task.chooseEmployee')}</option>
                {targets.map(u => {
                  const n = activeCount(state, u.id)
                  return <option key={u.id} value={u.id}>
                    {tr(n >= MAX_ACTIVE ? 'task.assignOptionPosFull' : 'task.assignOptionPos', { name: u.name, position: u.position, used: n, max: MAX_ACTIVE })}
                  </option>
                })}
              </select>
            </Field>
          </div>
        )}
      </div>

      <div className="form-sec">
        <span className="eyebrow">{tr('task.field.whenImportance')}</span>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Field label={tr('common.deadline')}>
            <DateInput value={deadline} onChange={setDeadline} />
          </Field>
          <Field label={tr('common.priority')}>
            <select value={priority} onChange={e => setPriority(e.target.value as Priority)}>
              {PRIORITIES.map(p => <option key={p} value={p}>{tr('task.priority.' + p.toLowerCase())}</option>)}
            </select>
          </Field>
        </div>
      </div>

      <div className="form-sec">
        <span className="eyebrow">{tr('task.field.whatWorth')}</span>
        <Field label={tr('task.field.rewardCoins')} hint={tr('task.help.rewardPaidHint')}>
          <input type="number" min={1} step={1} value={reward} onChange={e => setReward(e.target.value)} style={{ width: 140 }} />
        </Field>
      </div>

      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={closeAll}>{tr('common.cancel')}</button>
        <button className="btn primary" disabled={!valid} onClick={() => setConfirming(true)}>{tr('task.action.reviewCreate')}</button>
      </div>
      </>
      )}
    </Modal>
  )
}
