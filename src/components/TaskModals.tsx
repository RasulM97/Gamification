import { useEffect, useRef, useState } from 'react'
import { useStore, useMe } from '../store'
import { MAX_ACTIVE, activeCount, partialPayout, validateAttachments, claimPenalty } from '../domain/engine'
import type { Audience, Task, Attachment } from '../domain/engine'
import { AttachField, Coin, DateInput, Field, Modal, coins } from '../ui'

/* Task action modals — submit / reject / decline / cancel / return /
 * reactivate / reopen. Each is a small controlled form that dispatches one
 * canonical engine action. */
/* ─────────────────────────────────────────────────────────────── */
export function SubmitModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
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
    <Modal open={open} onClose={onClose} title={<>Submit work<small>{task.title}</small></>}>
      <Field label="Submission note">
        <textarea value={note} onChange={e => setNote(e.target.value)}
          placeholder="What did you deliver? What should the reviewer look at?" />
      </Field>
      {/* Employee-reported completion: defaults to 100%, informational only —
          the manager's decision sets verified progress. */}
      <Field label="How complete is the work? (your estimate)" hint="Informational only — the reviewer sets verified progress.">
        <div className="range-row">
          <input type="range" min={0} max={100} step={5} value={pct} onChange={e => setPct(+e.target.value)} />
          <span className="range-val">{pct}%</span>
        </div>
      </Field>
      <Field label={`Attachments — up to ${st.maxFileSizeMb} MB per file, ${st.maxSubmissionTotalMb} MB total`}
        hint="No executables or scripts. Click a file to remove it before submitting.">
        <input ref={inputRef} type="file" multiple style={{ display: 'none' }}
          onChange={e => addFiles(e.target.files)} />
        <div className={'dropzone' + (dragOver ? ' over' : '')}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) }}>
          <span className="dim" style={{ fontSize: 12 }}>Drop files here, or</span>
          <button className="btn" type="button" onClick={() => inputRef.current?.click()}>📎 Choose files…</button>
        </div>
      </Field>
      {errors.map(e => <div key={e} className="neg" style={{ fontSize: 12, marginBottom: 6 }}>⚠ {e}</div>)}
      {files.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 13 }}>
          {files.map((f, i) => (
            <span key={i} className="chip" onClick={() => remove(i)}
              title="Click to remove">📎 {f.name}{f.size > 0 ? ` · ${mb(f.size)} MB` : ''} ✕</span>
          ))}
        </div>
      )}
      <div className="actionbar" style={{ position: 'static', margin: '8px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={errors.length > 0} onClick={() => {
          dispatch({ type: 'SUBMIT_WORK', taskId: task.id, userId: me.id, note, attachments: files, pct })
          onClose()
        }}>Submit for review</button>
      </div>
    </Modal>
  )
}

export function RejectModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { dispatch } = useStore()
  const me = useMe()
  const [reason, setReason] = useState('')
  return (
    <Modal open={open} onClose={onClose} title={<>Reject submission<small>{task.title} — the employee can resume and resubmit</small></>}>
      <Field label="Rejection reason (required)">
        <textarea value={reason} onChange={e => setReason(e.target.value)}
          placeholder="What is insufficient, and what does good look like?" autoFocus />
      </Field>
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Back</button>
        <button className="btn primary" disabled={!reason.trim()} onClick={() => {
          dispatch({ type: 'REJECT', taskId: task.id, managerId: me.id, reason: reason.trim() })
          onClose()
        }}>Reject — send to rework</button>
      </div>
    </Modal>
  )
}

export function DeclineModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { dispatch } = useStore()
  const me = useMe()
  const [reason, setReason] = useState('')
  return (
    <Modal open={open} onClose={onClose} title={<>Decline assignment<small>{task.title} — no penalty; your manager is informed</small></>}>
      <Field label="Reason (required)">
        <textarea value={reason} onChange={e => setReason(e.target.value)}
          placeholder="Why can't you take this on?" autoFocus />
      </Field>
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Back</button>
        <button className="btn primary" disabled={!reason.trim()} onClick={() => {
          dispatch({ type: 'DECLINE_ASSIGNMENT', taskId: task.id, userId: me.id, reason: reason.trim() })
          onClose()
        }}>Decline assignment</button>
      </div>
    </Modal>
  )
}

export function CancelModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const [reason, setReason] = useState('')
  const [pct, setPct] = useState(0)
  const owner = state.users.find(u => u.id === task.ownerId)
  const maxPct = 100 - task.verified
  const payout = pct > 0 ? Math.min(partialPayout(task.reward, pct), Math.max(0, task.reward - task.paid)) : 0
  return (
    <Modal open={open} onClose={onClose} title={<>Cancel task<small>{task.title} — past payouts stay immutable</small></>}>
      {owner && maxPct > 0 && (
        <Field label={`Partial credit for ${owner.name} — work already done`}
          hint="Cancelled mid-work: contributors keep credit for accepted work. Paid now by the canonical formula, clamped to the remaining budget.">
          <div className="range-row">
            <input type="range" min={0} max={maxPct} step={5} value={pct} onChange={e => setPct(+e.target.value)} />
            <span className="range-val">{pct}%</span>
          </div>
          <div className="summary" style={{ marginTop: 10 }}>
            <div className="srow"><span>Payout to {owner.name} <span className="faint">(ceil(reward × % × 2) / 2)</span></span><Coin n={payout} /></div>
            <div className="srow"><span>Verified progress after</span><b className="num">{task.verified}% → {Math.min(100, task.verified + pct)}%</b></div>
          </div>
        </Field>
      )}
      <Field label="Reason (required)">
        <textarea value={reason} onChange={e => setReason(e.target.value)} placeholder="Why is this task cancelled?" autoFocus />
      </Field>
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Back</button>
        <button className="btn primary" disabled={!reason.trim()} onClick={() => {
          dispatch({ type: 'CANCEL_TASK', taskId: task.id, by: me.id, reason: reason.trim(), acceptedPct: pct })
          onClose()
        }}>{pct > 0 ? `Cancel — credit ${coins(payout)} Coins` : 'Cancel task'}</button>
      </div>
    </Modal>
  )
}

export function ReturnModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { dispatch } = useStore()
  const me = useMe()
  const [reason, setReason] = useState('')
  /* Priority-scaled claim penalty (base 5 × multiplier); the engine clamps
     so the balance can never go below zero. */
  const pen = claimPenalty(task.priority)
  return (
    <Modal open={open} onClose={onClose} title={<>Return to marketplace<small>{task.title} — another employee can claim it</small></>}>
      <div className="neg" style={{ fontSize: 13, marginBottom: 12 }}>
        ⚠ Returning a claimed task costs a <b>−{pen} Coins</b> penalty
        {task.priority !== 'NORMAL' && task.priority !== 'NONE' ? ` (${task.priority.toLowerCase()} priority ×${task.priority === 'URGENT' ? 2 : 1.5})` : ''}.
        If your wallet can't cover it, the penalty is limited to your balance — it never goes negative.
      </div>
      <Field label="Reason (required)">
        <textarea value={reason} onChange={e => setReason(e.target.value)}
          placeholder="Why are you returning this task?" autoFocus />
      </Field>
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Back</button>
        <button className="btn primary" disabled={!reason.trim()} onClick={() => {
          dispatch({ type: 'RETURN_CLAIM', taskId: task.id, userId: me.id, reason: reason.trim() })
          onClose()
        }}>Return task (−{pen} Coins)</button>
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
  const { state } = useStore()
  return (
    <div style={{ marginBottom: 14 }}>
      <Field label="Brief for the new cycle">
        <div className="choice">
          <button className={!update ? 'on' : ''} onClick={() => setUpdate(false)}>
            <b>Use previous brief</b>
            <small>Same description and brief files — just start running again.</small>
          </button>
          <button className={update ? 'on' : ''} onClick={() => setUpdate(true)}>
            <b>Update brief</b>
            <small>Revise the description and add files before the new cycle starts.</small>
          </button>
        </div>
      </Field>
      {update && (
        <>
          <Field label="Description">
            <textarea value={desc} onChange={e => setDesc(e.target.value)} style={{ minHeight: 88 }} />
          </Field>
          <AttachField files={files} onChange={setFiles} settings={state.settings}
            label="Add files to the brief (optional)" />
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
  const { state } = useStore()
  const targets = state.users.filter(u =>
    (audience === 'EMPLOYEES' ? u.role === 'EMPLOYEE'
      : audience === 'MANAGEMENT' ? u.role === 'MANAGER'
      : u.role !== 'ADMIN'))
  const pool = audience === 'MANAGEMENT' ? 'management pool — any manager can claim' : 'marketplace — any employee can claim'
  return (
    <Field label="Route the new cycle"
      hint="Cycle history stays untouched — the new cycle may go to an employee or a manager, regardless of who worked on it before.">
      <>
        <select value={audience} aria-label="New cycle audience"
          onChange={e => { setAudience(e.target.value as Audience); setAssigneeId('') }}>
          <option value="EMPLOYEES">Employees</option>
          <option value="MANAGEMENT">Management only</option>
          <option value="PRIVATE">Private — one person</option>
        </select>
        <select value={assigneeId} aria-label="New cycle assignee" style={{ marginTop: 8 }} onChange={e => setAssigneeId(e.target.value)}>
          {audience !== 'PRIVATE' && <option value="">Available — {pool}</option>}
          {audience === 'PRIVATE' && <option value="">Choose a person…</option>}
          {targets.map(u => {
            const n = activeCount(state, u.id)
            return <option key={u.id} value={u.id}>
              Assign: {u.name} · {u.role.toLowerCase()} · {n}/{MAX_ACTIVE} active{n >= MAX_ACTIVE ? ' · at capacity' : ''}
            </option>
          })}
        </select>
      </>
    </Field>
  )
}

export function ReopenModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { dispatch } = useStore()
  const me = useMe()
  const [update, setUpdate] = useState(false)
  const [desc, setDesc] = useState(task.description)
  const [files, setFiles] = useState<Attachment[]>([])
  const [audience, setAudience] = useState<Audience>(task.audience)
  const [assigneeId, setAssigneeId] = useState('')
  const routeBad = audience === 'PRIVATE' && !assigneeId
  return (
    <Modal open={open} onClose={onClose} title={<>Reopen task<small>{task.title} — starts cycle {task.cycle + 1}</small></>}>
      <div style={{ fontSize: 13, marginBottom: 14, lineHeight: 1.6 }}>
        Re-opening starts a <b>new cycle</b>: progress, payouts and submissions reset, and the task is routed
        again with a refreshed reward budget. Past cycles stay untouched in the history.
      </div>
      <NewCycleRouting task={task} audience={audience} setAudience={setAudience}
        assigneeId={assigneeId} setAssigneeId={setAssigneeId} />
      <BriefChoice task={task} update={update} setUpdate={setUpdate} desc={desc} setDesc={setDesc} files={files} setFiles={setFiles} />
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Back</button>
        <button className="btn primary" disabled={routeBad} onClick={() => {
          dispatch({ type: 'REOPEN', taskId: task.id, by: me.id,
            description: update ? desc : undefined, attachments: files.length > 0 ? files : undefined,
            audience: audience !== task.audience ? audience : undefined,
            assigneeId: assigneeId || undefined })
          onClose()
        }}>Reopen — start cycle {task.cycle + 1}</button>
      </div>
    </Modal>
  )
}

export function ReactivateModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
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
    <Modal open={open} onClose={onClose} title={<>Reactivate task<small>{task.title} — restarts from scratch as cycle {task.cycle + 1}</small></>}>
      <div style={{ fontSize: 13, marginBottom: 14, lineHeight: 1.6 }}>
        Reactivation starts the task <b>from scratch</b>: verified progress and paid Coins reset to zero,
        the task is routed again, and a new cycle is recorded. Past cycles stay immutable.
      </div>
      <Field label="Reason (required)">
        <textarea value={reason} onChange={e => setReason(e.target.value)}
          placeholder="Why is this task being reactivated?" autoFocus />
      </Field>
      <NewCycleRouting task={task} audience={audience} setAudience={setAudience}
        assigneeId={assigneeId} setAssigneeId={setAssigneeId} />
      <BriefChoice task={task} update={update} setUpdate={setUpdate} desc={desc} setDesc={setDesc} files={files} setFiles={setFiles} />
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Back</button>
        <button className="btn primary" disabled={!reason.trim() || routeBad} onClick={() => {
          dispatch({ type: 'REACTIVATE', taskId: task.id, by: me.id, reason: reason.trim(),
            description: update ? desc : undefined, attachments: files.length > 0 ? files : undefined,
            audience: audience !== task.audience ? audience : undefined,
            assigneeId: assigneeId || undefined })
          onClose()
        }}>Reactivate task</button>
      </div>
    </Modal>
  )
}

export function EditTaskModal({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
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
    <Modal open={open} onClose={onClose} title={<>Edit task<small>{task.title} — the owner is notified of changes</small></>}>
      <Field label="Title">
        <input value={title} onChange={e => setTitle(e.target.value)} />
      </Field>
      <Field label="Description">
        <textarea value={description} onChange={e => setDescription(e.target.value)} rows={4} />
      </Field>
      <Field label="Priority">
        <select value={priority} onChange={e => setPriority(e.target.value as typeof priority)}>
          <option value="NONE">No priority</option>
          <option value="NORMAL">Normal</option>
          <option value="IMPORTANT">Important</option>
          <option value="URGENT">Urgent</option>
        </select>
      </Field>
      <Field label="Deadline" hint="Leave empty for no deadline.">
        <DateInput value={deadline} onChange={setDeadline} />
      </Field>
      <Field label={`Reward (Coins) — at least ${coins(minReward)} already paid`}>
        <input type="number" min={minReward} step={0.5} value={reward}
          onChange={e => setReward(+e.target.value)} />
      </Field>
      {rewardBad && <div className="neg" style={{ fontSize: 12, marginBottom: 8 }}>⚠ {coins(minReward)} Coins are already paid — the reward can't go below that.</div>}
      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={onClose}>Back</button>
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
        }}>Save changes</button>
      </div>
    </Modal>
  )
}
