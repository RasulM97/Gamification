import { useState } from 'react'
import { useStore, useMe } from '../store'
import { PRIORITIES, MAX_ACTIVE, activeCount } from '../domain/engine'
import type { Attachment, Audience, Priority } from '../domain/engine'
import { AttachField, Coin, DateInput, Field, Modal, PriBadge, Seg, fmtDate } from '../ui'

/* Create Task follows the canonical four-question structure; economy never
   visually dominates the meaning of the work. */
export function CreateTaskModal({ open, onClose }: { open: boolean; onClose: () => void }) {
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
      title={<>Create task<small>{confirming ? 'Check the summary, then confirm.' : 'One task, one owner at a time — the economy follows the work, not the other way around.'}</small></>}>
      {confirming ? (
        <div>
          <div className="panel" style={{ padding: '12px 14px', marginBottom: 14 }}>
            <b style={{ fontSize: 14 }}>{title.trim()}</b>
            <div className="dim" style={{ fontSize: 12.5, marginTop: 6, lineHeight: 1.55, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{desc.trim()}</div>
          </div>
          <div className="summary">
            <div className="srow"><span>Audience</span><b>{audience === 'MANAGEMENT' ? 'Management only' : audience === 'PRIVATE' ? 'Private — one person' : 'Employees'}</b></div>
            <div className="srow"><span>Ownership</span><b>{audience === 'PRIVATE'
              ? `Private assignment to ${assigneeUser?.name ?? '—'}`
              : mode === 'all'
                ? (audience === 'MANAGEMENT' ? 'Management pool — first valid claim wins' : 'Marketplace — first valid claim wins')
                : `Assigned to ${assigneeUser?.name ?? '—'}`}</b></div>
            {files.length > 0 && (
              <div className="srow"><span>Attached files</span>
                <span style={{ display: 'flex', gap: 5, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {files.map((f, i) => <span key={i} className="chip">📎 {f.name}</span>)}
                </span>
              </div>
            )}
            <div className="srow"><span>Priority</span><PriBadge p={priority} /></div>
            <div className="srow"><span>Deadline</span><b>{/^\d{4}-\d{2}-\d{2}$/.test(deadline) ? fmtDate(deadline) : 'No deadline'}</b></div>
            <div className="srow"><span>Economic value</span><Coin n={+reward} /></div>
          </div>
          <div className="actionbar" style={{ position: 'static', margin: '14px -18px -18px' }}>
            <button className="btn" onClick={() => setConfirming(false)}>Back to edit</button>
            <button className="btn primary" onClick={create}>Confirm & create</button>
          </div>
        </div>
      ) : (
      <>
      <div className="form-sec">
        <span className="eyebrow">What needs to be done?</span>
        <Field label="Title">
          <input type="text" value={title} onChange={e => setTitle(e.target.value)}
            placeholder="e.g. Reconcile October supplier invoices" autoFocus />
        </Field>
        <Field label="Description" hint="What does done look like? What evidence should the reviewer expect?">
          <textarea value={desc} onChange={e => setDesc(e.target.value)} style={{ minHeight: 96 }}
            placeholder="Scope, deliverables, definition of done…" />
        </Field>
        {/* Brief files: specs, templates, source data — attached at creation,
            visible to everyone who works on the task. */}
        <AttachField files={files} onChange={setFiles} settings={state.settings}
          label={`Brief attachments — up to ${state.settings.maxFileSizeMb} MB per file`} />
      </div>

      <div className="form-sec">
        <span className="eyebrow">Who can do it?</span>
        <Seg value={audience} onChange={v => { setAudience(v as Audience); setAssignee('') }}
          options={[
            { v: 'EMPLOYEES', label: 'Employees' },
            { v: 'PRIVATE', label: 'Private' },
            { v: 'MANAGEMENT', label: 'Management only' },
          ]} />
        {audience === 'MANAGEMENT' && (
          <div className="faint" style={{ fontSize: 11.5, marginTop: 7 }}>
            Management work stays between admin and managers — employees never see it, and managers earn Coins from it. Nobody reviews their own submission.
          </div>
        )}
        {audience === 'PRIVATE' && (
          <div className="faint" style={{ fontSize: 11.5, marginTop: 7 }}>
            Private work is one-to-one: only the chosen person — employee or manager — and management can see it. It never appears in anyone else's lists or notifications.
          </div>
        )}
        {audience !== 'PRIVATE' && (
        <div className="choice" style={{ marginTop: 10 }}>
          <button className={mode === 'all' ? 'on' : ''} onClick={() => setMode('all')}>
            <b>{audience === 'MANAGEMENT' ? 'Available to managers' : 'Available to employees'}</b>
            <small>Published to the {audience === 'MANAGEMENT' ? 'management pool' : 'marketplace'}. One task — the first valid claim wins, everyone else sees it as taken.</small>
          </button>
          <button className={mode === 'specific' ? 'on' : ''} onClick={() => setMode('specific')}>
            <b>{audience === 'MANAGEMENT' ? 'Specific manager' : 'Specific employee'}</b>
            <small>Assigned directly. They can accept and start, or decline with a reason (no penalty — even after starting).</small>
          </button>
        </div>
        )}
        {(mode === 'specific' || audience === 'PRIVATE') && (
          <div style={{ marginTop: 11 }}>
            <Field label="Assignee" hint="Workload shown so you don't overload one person — the claim limit is enforced by the engine.">
              <select value={assignee} onChange={e => setAssignee(e.target.value)}>
                <option value="">Choose {audience === 'MANAGEMENT' ? 'a manager…' : audience === 'PRIVATE' ? 'a person…' : 'an employee…'}</option>
                {targets.map(u => {
                  const n = activeCount(state, u.id)
                  return <option key={u.id} value={u.id}>
                    {u.name} — {u.position} · {n}/{MAX_ACTIVE} active{n >= MAX_ACTIVE ? ' · at capacity' : ''}
                  </option>
                })}
              </select>
            </Field>
          </div>
        )}
      </div>

      <div className="form-sec">
        <span className="eyebrow">When & how important?</span>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Field label="Deadline">
            <DateInput value={deadline} onChange={setDeadline} />
          </Field>
          <Field label="Priority">
            <select value={priority} onChange={e => setPriority(e.target.value as Priority)}>
              {PRIORITIES.map(p => <option key={p} value={p}>{p === 'NONE' ? 'None' : p[0] + p.slice(1).toLowerCase()}</option>)}
            </select>
          </Field>
        </div>
      </div>

      <div className="form-sec">
        <span className="eyebrow">What is it worth?</span>
        <Field label="Reward (Coins)" hint="Paid on approval. Partial contributions pay proportionally: ceil(reward × % × 2) / 2.">
          <input type="number" min={1} step={1} value={reward} onChange={e => setReward(e.target.value)} style={{ width: 140 }} />
        </Field>
      </div>

      <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
        <button className="btn" onClick={closeAll}>Cancel</button>
        <button className="btn primary" disabled={!valid} onClick={() => setConfirming(true)}>Review & create</button>
      </div>
      </>
      )}
    </Modal>
  )
}
