import { useEffect, useRef, useState } from 'react'
import { useStore, useMe } from '../store'
import { MAX_ACTIVE, activeCount, partialPayout, validateAttachments, claimPenalty } from '../domain/engine'
import type { Audience, Task, Attachment } from '../domain/engine'
import { AttachField, Coin, DateInput, Field, Modal, coins } from '../ui'
import { useI18n, fmtPct, fmtInt } from '../i18n'
import { roleKey } from '../ui'

/* Task action modals — submit / reject / decline / cancel / return /
 * reactivate / reopen. Each is a small controlled form that dispatches one
 * canonical engine action. */
/* ─────────────────────────────────────────────────────────────── */
export function SubmitModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { t: tr } = useI18n()
  const { state, dispatch } = useStore()
  const me = useMe()
  const [note, setNote] = useState('')
  const [files, setFiles] = useState<Attachment[]>([])
  const [errors, setErrors] = useState<string[]>([])
  const [pct, setPct] = useState(100)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const st = state.settings
  /* The estimate follows the live self-report: if the drawer slider says
     70%, this form opens at 70% (100% only when nothing was reported). */
  useEffect(() => {
    if (open) { setPct(task.reported > 0 ? task.reported : 100); setNote(''); setFiles([]); setErrors([]) }
  }, [open])

  /* Real multi-select with a removable queue plus drag & drop; per-file
     validation happens at pick time and the whole set is re-validated
     atomically at submit time. */
  const addFiles = (list: FileList | null) => {
    if (!list) return
    /* Keep the real File object for the server-mode multipart upload on
       submit (inert in demo mode). */
    const incoming: Attachment[] = Array.from(list).map(f => ({ name: f.name, size: f.size, type: f.type, file: f }))
    const next = [...files, ...incoming]
    setErrors(validateAttachments(next, st))
    setFiles(next)
    if (inputRef.current) inputRef.current.value = ''
  }
  const remove = (i: number) => {
    const next = files.filter((_, j) => j !== i)
    setFiles(next); setErrors(validateAttachments(next, st))
  }
  const mb = (n: number) => (n / 1048576).toFixed(1)

  return (
    <Modal open={open} onClose={onClose} title={<>{tr('task.action.submit')}<small dir="auto">{task.title}</small></>}>
      <Field label={tr('task.field.submissionNote')}>
        <textarea dir="auto" value={note} onChange={e => setNote(e.target.value)}
          placeholder={tr('task.placeholder.submissionNote')} />
      </Field>
      {/* Employee-reported completion: defaults to 100%, informational only —
          the manager's decision sets verified progress. */}
      <Field label={tr('task.field.completionEstimate')} hint={tr('task.help.reportInformational')}>
        <div className="range-row">
          <input type="range" min={0} max={100} step={5} value={pct} onChange={e => setPct(+e.target.value)} />
          <span className="range-val">{fmtPct(pct)}</span>
        </div>
      </Field>
      <Field label={tr('task.field.attachmentsLimit', { maxFileSizeMb: st.maxFileSizeMb, maxSubmissionTotalMb: st.maxSubmissionTotalMb })}
        hint={tr('task.help.noExecutablesSubmit')}>
        <input ref={inputRef} type="file" multiple style={{ display: 'none' }}
          onChange={e => addFiles(e.target.files)} />
        <div className={'dropzone' + (dragOver ? ' over' : '')}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) }}>
          <span className="dim" style={{ fontSize: 12 }}>{tr('file.dropHere')}</span>
          <button className="btn" type="button" onClick={() => inputRef.current?.click()}>📎 {tr('file.choose')}</button>
        </div>
      </Field>
      {errors.map(e => <div key={e} className="neg" style={{ fontSize: 12, marginBottom: 6 }} dir="auto">⚠ {e}</div>)}
      {files.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 13 }}>
          {files.map((f, i) => (
            <span key={i} className="chip" onClick={() => remove(i)}
              title={tr('file.clickRemove')}>📎 <span dir="auto">{f.name}</span>{f.size > 0 ? ` · ${mb(f.size)} MB` : ''} ✕</span>
          ))}
        </div>
      )}
      <div className="actionbar" style={{ position: 'static', margin: '8px -18px -18px' }}>
        <button className="btn" onClick={onClose}>{tr('common.cancel')}</button>
        <button className="btn primary" disabled={errors.length > 0} onClick={() => {
          dispatch({ type: 'SUBMIT_WORK', taskId: task.id, userId: me.id, note, attachments: files, pct })
          onClose()
        }}>{tr('task.action.submitReview')}</button>
      </div>
    </Modal>
  )
}

export function RejectModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { t: tr } = useI18n()
  const { dispatch } = useStore()
  const me = useMe()
  const [reason, setReason] = useState('')
  return (
    <Modal open={open} onClose={onClose} title={<>{tr('task.rejectTitle')}<small dir="auto">{tr('task.rejectSub', { title: task.title })}</small></>}>
      <Field label={tr('task.rejectReasonRequired')}>
        <textarea dir="auto" value={reason} onChange={e => setReason(e.target.value)}
          placeholder={tr('task.placeholder.rejectLooksLike')} autoFocus />
      </Field>
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>{tr('common.back')}</button>
        <button className="btn primary" disabled={!reason.trim()} onClick={() => {
          dispatch({ type: 'REJECT', taskId: task.id, managerId: me.id, reason: reason.trim() })
          onClose()
        }}>{tr('review.reject')}</button>
      </div>
    </Modal>
  )
}

export function DeclineModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { t: tr } = useI18n()
  const { dispatch } = useStore()
  const me = useMe()
  const [reason, setReason] = useState('')
  return (
    <Modal open={open} onClose={onClose} title={<>{tr('task.action.decline')}<small dir="auto">{tr('task.declineSub', { title: task.title })}</small></>}>
      <Field label={tr('common.reasonRequired')}>
        <textarea dir="auto" value={reason} onChange={e => setReason(e.target.value)}
          placeholder={tr('task.placeholder.declineReason')} autoFocus />
      </Field>
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>{tr('common.back')}</button>
        <button className="btn primary" disabled={!reason.trim()} onClick={() => {
          dispatch({ type: 'DECLINE_ASSIGNMENT', taskId: task.id, userId: me.id, reason: reason.trim() })
          onClose()
        }}>{tr('task.action.decline')}</button>
      </div>
    </Modal>
  )
}

export function CancelModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { t: tr } = useI18n()
  const { state, dispatch } = useStore()
  const me = useMe()
  const [reason, setReason] = useState('')
  const [pct, setPct] = useState(0)
  const owner = state.users.find(u => u.id === task.ownerId)
  const maxPct = 100 - task.verified
  const payout = pct > 0 ? Math.min(partialPayout(task.reward, pct), Math.max(0, task.reward - task.paid)) : 0
  return (
    <Modal open={open} onClose={onClose} title={<>{tr('task.action.cancel')}<small dir="auto">{tr('task.cancelSub', { title: task.title })}</small></>}>
      {owner && maxPct > 0 && (
        <Field label={tr('task.partialCredit', { name: owner.name })}
          hint={tr('task.partialCreditHint')}>
          <div className="range-row">
            <input type="range" min={0} max={maxPct} step={5} value={pct} onChange={e => setPct(+e.target.value)} />
            <span className="range-val">{fmtPct(pct)}</span>
          </div>
          <div className="summary" style={{ marginTop: 10 }}>
            <div className="srow"><span dir="auto">{tr('handoff.payoutTo', { name: owner.name })} <span className="faint">{tr('task.payoutFormula')}</span></span><Coin n={payout} /></div>
            <div className="srow"><span>{tr('handoff.verifiedAfter')}</span><b className="num">{fmtPct(task.verified)} → {fmtPct(Math.min(100, task.verified + pct))}</b></div>
          </div>
        </Field>
      )}
      <Field label={tr('common.reasonRequired')}>
        <textarea dir="auto" value={reason} onChange={e => setReason(e.target.value)} placeholder={tr('task.placeholder.cancelReason')} autoFocus />
      </Field>
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>{tr('common.back')}</button>
        <button className="btn primary" disabled={!reason.trim()} onClick={() => {
          dispatch({ type: 'CANCEL_TASK', taskId: task.id, by: me.id, reason: reason.trim(), acceptedPct: pct })
          onClose()
        }}>{pct > 0 ? tr('task.action.cancelCredit', { coins: coins(payout) }) : tr('task.action.cancel')}</button>
      </div>
    </Modal>
  )
}

export function ReturnModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { t: tr } = useI18n()
  const { dispatch } = useStore()
  const me = useMe()
  const [reason, setReason] = useState('')
  /* Priority-scaled claim penalty (base 5 × multiplier); the engine clamps
     so the balance can never go below zero. */
  const pen = claimPenalty(task.priority)
  return (
    <Modal open={open} onClose={onClose} title={<>{tr('task.action.returnMarketplace')}<small dir="auto">{tr('task.returnSub', { title: task.title })}</small></>}>
      <div className="neg" style={{ fontSize: 13, marginBottom: 12 }}>
        ⚠ {tr('task.returnPenalty', { coins: fmtInt(pen) })}{' '}
        {task.priority !== 'NORMAL' && task.priority !== 'NONE' ? tr('task.returnPenaltyPriority', { priority: tr('task.priority.' + task.priority.toLowerCase()), mult: task.priority === 'URGENT' ? 2 : 1.5 }) : ''}.{' '}
        {tr('task.returnPenaltyCap')}
      </div>
      <Field label={tr('common.reasonRequired')}>
        <textarea dir="auto" value={reason} onChange={e => setReason(e.target.value)}
          placeholder={tr('task.placeholder.returnReason')} autoFocus />
      </Field>
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>{tr('common.back')}</button>
        <button className="btn primary" disabled={!reason.trim()} onClick={() => {
          dispatch({ type: 'RETURN_CLAIM', taskId: task.id, userId: me.id, reason: reason.trim() })
          onClose()
        }}>{tr('task.action.returnPenalty', { coins: fmtInt(pen) })}</button>
      </div>
    </Modal>
  )
}

/* Reopen & Reactivate share the brief question: run again with the previous
   information and files, or update the description and attach new files for
   the fresh cycle. New files join the brief; past cycles stay immutable. */
function BriefChoice({ task, update, setUpdate, desc, setDesc, files, setFiles }: {
  task: Task; update: boolean; setUpdate: (b: boolean) => void
  desc: string; setDesc: (s: string) => void
  files: Attachment[]; setFiles: (f: Attachment[]) => void
}) {
  const { t: tr } = useI18n()
  const { state } = useStore()
  return (
    <div style={{ marginBottom: 14 }}>
      <Field label={tr('task.briefNewCycle')}>
        <div className="choice">
          <button className={!update ? 'on' : ''} onClick={() => setUpdate(false)}>
            <b>{tr('task.usePreviousBrief')}</b>
            <small>{tr('task.usePreviousBriefHint')}</small>
          </button>
          <button className={update ? 'on' : ''} onClick={() => setUpdate(true)}>
            <b>{tr('task.updateBrief')}</b>
            <small>{tr('task.updateBriefHint')}</small>
          </button>
        </div>
      </Field>
      {update && (
        <>
          <Field label={tr('common.description')}>
            <textarea dir="auto" value={desc} onChange={e => setDesc(e.target.value)} style={{ minHeight: 88 }} />
          </Field>
          <AttachField files={files} onChange={setFiles} settings={state.settings}
            label={tr('task.addFilesBrief')} />
        </>
      )}
    </div>
  )
}

/* New-cycle routing (M1-D D7): a reopened/reactivated cycle is NEW work.
   The previous cycle's worker type must not restrict the new cycle —
   management picks the audience and optionally a specific person; the admin
   is never a target. Shared by Reopen and Reactivate. */
function NewCycleRouting({ task, audience, setAudience, assigneeId, setAssigneeId }: {
  task: Task; audience: Audience; setAudience: (a: Audience) => void
  assigneeId: string; setAssigneeId: (id: string) => void
}) {
  const { t: tr } = useI18n()
  const { state } = useStore()
  const targets = state.users.filter(u =>
    (audience === 'EMPLOYEES' ? u.role === 'EMPLOYEE'
      : audience === 'MANAGEMENT' ? u.role === 'MANAGER'
      : u.role !== 'ADMIN'))
  const pool = audience === 'MANAGEMENT' ? tr('task.poolManagement') : tr('task.poolMarketplace')
  return (
    <Field label={tr('task.routeNewCycle')}
      hint={tr('task.routeNewCycleHint')}>
      <>
        <select value={audience} aria-label={tr('accessibility.newCycleAudience')}
          onChange={e => { setAudience(e.target.value as Audience); setAssigneeId('') }}>
          <option value="EMPLOYEES">{tr('task.audience.employees')}</option>
          <option value="MANAGEMENT">{tr('task.audience.management')}</option>
          <option value="PRIVATE">{tr('task.audience.privateOnePerson')}</option>
        </select>
        <select value={assigneeId} aria-label={tr('accessibility.newCycleAssignee')} style={{ marginTop: 8 }} onChange={e => setAssigneeId(e.target.value)}>
          {audience !== 'PRIVATE' && <option value="">{tr('task.availablePool', { pool })}</option>}
          {audience === 'PRIVATE' && <option value="">{tr('task.choosePerson')}</option>}
          {targets.map(u => {
            const n = activeCount(state, u.id)
            return <option key={u.id} value={u.id}>
              {tr(n >= MAX_ACTIVE ? 'task.assignOptionRoleFull' : 'task.assignOptionRole', { name: u.name, role: tr(roleKey(u.role)), used: n, max: MAX_ACTIVE })}
            </option>
          })}
        </select>
      </>
    </Field>
  )
}

export function ReopenModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { t: tr } = useI18n()
  const { dispatch } = useStore()
  const me = useMe()
  const [update, setUpdate] = useState(false)
  const [desc, setDesc] = useState(task.description)
  const [files, setFiles] = useState<Attachment[]>([])
  const [audience, setAudience] = useState<Audience>(task.audience)
  const [assigneeId, setAssigneeId] = useState('')
  const routeBad = audience === 'PRIVATE' && !assigneeId
  return (
    <Modal open={open} onClose={onClose} title={<>{tr('task.reopenTitle')}<small dir="auto">{tr('task.reopenSub', { title: task.title, cycle: task.cycle + 1 })}</small></>}>
      <div style={{ fontSize: 13, marginBottom: 14, lineHeight: 1.6 }}>
        {tr('task.reopenExplainer')}
      </div>
      <NewCycleRouting task={task} audience={audience} setAudience={setAudience}
        assigneeId={assigneeId} setAssigneeId={setAssigneeId} />
      <BriefChoice task={task} update={update} setUpdate={setUpdate} desc={desc} setDesc={setDesc} files={files} setFiles={setFiles} />
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>{tr('common.back')}</button>
        <button className="btn primary" disabled={routeBad} onClick={() => {
          dispatch({ type: 'REOPEN', taskId: task.id, by: me.id,
            description: update ? desc : undefined, attachments: files.length > 0 ? files : undefined,
            audience: audience !== task.audience ? audience : undefined,
            assigneeId: assigneeId || undefined })
          onClose()
        }}>{tr('task.action.reopenCycle', { cycle: task.cycle + 1 })}</button>
      </div>
    </Modal>
  )
}

export function ReactivateModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { t: tr } = useI18n()
  const { dispatch } = useStore()
  const me = useMe()
  const [reason, setReason] = useState('')
  const [update, setUpdate] = useState(false)
  const [desc, setDesc] = useState(task.description)
  const [files, setFiles] = useState<Attachment[]>([])
  const [audience, setAudience] = useState<Audience>(task.audience)
  const [assigneeId, setAssigneeId] = useState('')
  const routeBad = audience === 'PRIVATE' && !assigneeId
  return (
    <Modal open={open} onClose={onClose} title={<>{tr('task.action.reactivateTask')}<small dir="auto">{tr('task.reactivateSub', { title: task.title, cycle: task.cycle + 1 })}</small></>}>
      <div style={{ fontSize: 13, marginBottom: 14, lineHeight: 1.6 }}>
        {tr('task.reactivateExplainer')}
      </div>
      <Field label={tr('common.reasonRequired')}>
        <textarea dir="auto" value={reason} onChange={e => setReason(e.target.value)}
          placeholder={tr('task.placeholder.reactivateReason')} autoFocus />
      </Field>
      <NewCycleRouting task={task} audience={audience} setAudience={setAudience}
        assigneeId={assigneeId} setAssigneeId={setAssigneeId} />
      <BriefChoice task={task} update={update} setUpdate={setUpdate} desc={desc} setDesc={setDesc} files={files} setFiles={setFiles} />
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>{tr('common.back')}</button>
        <button className="btn primary" disabled={!reason.trim() || routeBad} onClick={() => {
          dispatch({ type: 'REACTIVATE', taskId: task.id, by: me.id, reason: reason.trim(),
            description: update ? desc : undefined, attachments: files.length > 0 ? files : undefined,
            audience: audience !== task.audience ? audience : undefined,
            assigneeId: assigneeId || undefined })
          onClose()
        }}>{tr('task.action.reactivateTask')}</button>
      </div>
    </Modal>
  )
}

export function EditTaskModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { t: tr } = useI18n()
  const { dispatch } = useStore()
  const me = useMe()
  const [title, setTitle] = useState(task.title)
  const [description, setDescription] = useState(task.description)
  const [priority, setPriority] = useState(task.priority)
  const [deadline, setDeadline] = useState(task.deadline ? task.deadline.slice(0, 10) : '')
  const [reward, setReward] = useState(task.reward)
  /* Paid Coins are final: the reward can never drop below what is already
     paid out (engine enforces the same guard). */
  const minReward = task.paid
  const rewardBad = reward < minReward
  const unchanged = title.trim() === task.title && description.trim() === task.description &&
    priority === task.priority && (deadline || null) === (task.deadline ? task.deadline.slice(0, 10) : null) &&
    reward === task.reward
  return (
    <Modal open={open} onClose={onClose} title={<>{tr('task.editTitle')}<small dir="auto">{tr('task.editSub', { title: task.title })}</small></>}>
      <Field label={tr('common.title')}>
        <input dir="auto" type="text" value={title} onChange={e => setTitle(e.target.value)} />
      </Field>
      <Field label={tr('common.description')}>
        <textarea dir="auto" value={description} onChange={e => setDescription(e.target.value)} rows={4} />
      </Field>
      <Field label={tr('common.priority')}>
        <select value={priority} onChange={e => setPriority(e.target.value as typeof priority)}>
          <option value="NONE">{tr('task.priority.none')}</option>
          <option value="NORMAL">{tr('task.priority.normal')}</option>
          <option value="IMPORTANT">{tr('task.priority.important')}</option>
          <option value="URGENT">{tr('task.priority.urgent')}</option>
        </select>
      </Field>
      <Field label={tr('common.deadline')} hint={tr('task.help.noDeadlineHint')}>
        <DateInput value={deadline} onChange={setDeadline} />
      </Field>
      <Field label={tr('task.field.rewardMinPaid', { coins: coins(minReward) })}>
        <input type="number" min={minReward} step={0.5} value={reward}
          onChange={e => setReward(+e.target.value)} />
      </Field>
      {rewardBad && <div className="neg" style={{ fontSize: 12, marginBottom: 8 }}>⚠ {tr('task.help.rewardBelowPaid', { coins: coins(minReward) })}</div>}
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>{tr('common.back')}</button>
        <button className="btn primary" disabled={rewardBad || unchanged || !title.trim()} onClick={() => {
          dispatch({
            type: 'EDIT_TASK', taskId: task.id, by: me.id,
            title: title.trim() !== task.title ? title.trim() : undefined,
            description: description.trim() !== task.description ? description.trim() : undefined,
            priority: priority !== task.priority ? priority : undefined,
            deadline: (deadline || null) !== (task.deadline ? task.deadline.slice(0, 10) : null)
              ? (deadline || null) : undefined,
            reward: reward !== task.reward ? reward : undefined,
          })
          onClose()
        }}>{tr('common.saveChanges')}</button>
      </div>
    </Modal>
  )
}
