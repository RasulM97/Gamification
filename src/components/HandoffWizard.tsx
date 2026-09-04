import { useState } from 'react'
import { useStore, useMe } from '../store'
import { partialPayout, activeCount } from '../domain/engine'
import type { Attachment, Audience, Task } from '../domain/engine'
import { AttachField, Coin, DateInput, Field, Modal, PriBadge, Seg, fmtDate } from '../ui'

/* Handoff wizard — the five canonical steps ─────────────────────────── */
export function HandoffWizard({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { state, dispatch } = useStore()
  const me = useMe()
  const [step, setStep] = useState(0)
  const [pct, setPct] = useState(0)
  const [reason, setReason] = useState('')
  const [next, setNext] = useState<'AVAILABLE' | string>('AVAILABLE')
  /* Next ownership is decided like task creation: first the audience (the
     situation decides, per task), then marketplace vs a specific person.
     PRIVATE work is always one-to-one — no marketplace. The admin never
     appears as a target: the founder arranges work, never owns it. */
  const [audience, setAudience] = useState<Audience>(task.audience)
  const [mode, setMode] = useState<'AVAILABLE' | 'SPECIFIC'>(task.audience === 'PRIVATE' ? 'SPECIFIC' : 'AVAILABLE')
  /* Step 3 adjustments: the manager can change priority/deadline for the
     remaining work and override the suggested remaining reward — an override
     always requires an audited explanation (enforced by the engine too). */
  const [newPriority, setNewPriority] = useState(task.priority)
  const [newDeadline, setNewDeadline] = useState(task.deadline ? task.deadline.slice(0, 10) : '')
  const [rewardOverride, setRewardOverride] = useState<number | null>(null)
  const [overrideReason, setOverrideReason] = useState('')
  /* Context files can travel with the handoff to the next owner. */
  const [files, setFiles] = useState<Attachment[]>([])
  /* Larger orgs: the next-owner picker is searchable, not a wall of buttons. */
  const [pick, setPick] = useState('')

  const owner = state.users.find(u => u.id === task.ownerId)
  /* Targets follow the chosen audience; admins are never assignable. */
  const targets = state.users.filter(u =>
    (audience === 'EMPLOYEES' ? u.role === 'EMPLOYEE'
      : audience === 'MANAGEMENT' ? u.role === 'MANAGER'
      : u.role !== 'ADMIN') && u.id !== me.id)
  const shownTargets = pick.trim()
    ? targets.filter(u => (u.name + ' ' + u.position).toLowerCase().includes(pick.trim().toLowerCase()))
    : targets
  const poolLabel = audience === 'MANAGEMENT' ? 'management pool' : 'marketplace'
  const personLabel = audience === 'MANAGEMENT' ? 'manager' : audience === 'PRIVATE' ? 'person' : 'employee'
  const maxPct = 100 - task.verified
  const payout = pct > 0 ? Math.min(partialPayout(task.reward, pct), Math.max(0, task.reward - task.paid)) : 0
  const after = Math.min(100, task.verified + pct)
  const remaining = Math.max(0, task.reward - task.paid - payout)
  const effRemaining = rewardOverride ?? remaining
  const overriding = rewardOverride != null && Math.round(rewardOverride) !== Math.round(remaining)
  const nextUser = next === 'AVAILABLE' || !next ? null : state.users.find(u => u.id === next)

  const chooseAudience = (v: Audience) => {
    setAudience(v); setPick('')
    if (v === 'PRIVATE') { setMode('SPECIFIC'); setNext('') }
    else setNext(mode === 'AVAILABLE' ? 'AVAILABLE' : '')
  }
  const chooseMode = (m: 'AVAILABLE' | 'SPECIFIC') => { setMode(m); setNext(m === 'AVAILABLE' ? 'AVAILABLE' : '') }

  const canNext =
    step === 0 ? true :
    step === 1 ? reason.trim().length > 0 :
    step === 2 ? (mode === 'AVAILABLE' && audience !== 'PRIVATE' ? true : !!next) :
    step === 3 ? (!overriding || overrideReason.trim().length > 0) && effRemaining >= 0 : true

  const finish = () => {
    dispatch({
      type: 'HANDOFF', taskId: task.id, managerId: me.id, acceptedPct: pct, reason: reason.trim(),
      next: next === 'AVAILABLE' ? { kind: 'AVAILABLE' } : { kind: 'EMPLOYEE', id: next },
      audience: audience !== task.audience ? audience : undefined,
      priority: newPriority !== task.priority ? newPriority : undefined,
      /* Canonical deadline format is date-only 'YYYY-MM-DD' — never ISO. */
      deadline: (newDeadline || null) !== (task.deadline ? task.deadline.slice(0, 10) : null)
        ? (newDeadline || null) : undefined,
      remainingReward: overriding ? effRemaining : undefined,
      overrideReason: overriding ? overrideReason.trim() : undefined,
      attachments: files.length > 0 ? files : undefined,
    })
    onClose()
  }

  const steps = ['Contribution decision', 'Why handoff?', 'Next ownership', 'Remaining work', 'Confirmation']

  return (
    <Modal open={open} onClose={onClose} wide
      dirty={!!(reason.trim() || overrideReason.trim())}
      title={<>Handoff — {task.title}<small>Step {step + 1} of 5 · {steps[step]}</small></>}>
      <div className="steps">
        {steps.map((_, i) => <i key={i} className={i < step ? 'done' : i === step ? 'on' : ''} />)}
      </div>

      {step === 0 && (
        <div>
          <p className="dim" style={{ fontSize: 12.5, marginBottom: 14 }}>
            How much of <b>{owner?.name}</b>'s work do you accept as verified contribution?
            Accepted contribution pays out now and moves the task's verified progress.
            Self-reported: {task.reported}% — informational only.
          </p>
          <div className="range-row">
            <input type="range" min={0} max={maxPct} step={5} value={pct} onChange={e => setPct(+e.target.value)} />
            <span className="range-val">{pct}%</span>
          </div>
          <div className="summary" style={{ marginTop: 16 }}>
            <div className="srow"><span>Accepted contribution</span><b className="num">{pct}%</b></div>
            <div className="srow"><span>Payout to {owner?.name} <span className="faint">(formula: ceil(reward × % × 2) / 2)</span></span><Coin n={payout} /></div>
            <div className="srow"><span>Verified progress after</span><b className="num">{task.verified}% → {after}%</b></div>
          </div>
        </div>
      )}

      {step === 1 && (
        <Field label="Why is this a handoff? (required — recorded in history)">
          <textarea value={reason} onChange={e => setReason(e.target.value)} autoFocus
            placeholder="e.g. contributor pulled onto an escalation; remaining work needs field access…" />
        </Field>
      )}

      {step === 2 && (
        <div>
          <Seg value={audience} onChange={v => chooseAudience(v as Audience)}
            options={[
              { v: 'EMPLOYEES', label: 'Employees' },
              { v: 'PRIVATE', label: 'Private' },
              { v: 'MANAGEMENT', label: 'Management only' },
            ]} />
          <div className="faint" style={{ fontSize: 11.5, marginTop: 7 }}>
            {audience === 'PRIVATE'
              ? 'Private work is one-to-one: only the chosen person — employee or manager — and management can see it.'
              : audience === 'MANAGEMENT'
                ? 'Management work stays between admin and managers — employees never see it.'
                : 'Employee work is visible to everyone and claimed from the marketplace, or assigned directly.'}
          </div>
          {audience !== 'PRIVATE' && (
            <div className="choice" style={{ marginTop: 10 }}>
              <button className={mode === 'AVAILABLE' ? 'on' : ''} onClick={() => chooseMode('AVAILABLE')}>
                <b>Return to {poolLabel}</b>
                <small>Any eligible {personLabel} can claim the remaining work. First valid claim wins.</small>
              </button>
              <button className={mode === 'SPECIFIC' ? 'on' : ''} onClick={() => chooseMode('SPECIFIC')}>
                <b>Specific {personLabel}</b>
                <small>Assigned directly — they can accept and start, or decline with a reason (no penalty).</small>
              </button>
            </div>
          )}
          {(mode === 'SPECIFIC' || audience === 'PRIVATE') && (
            <div style={{ marginTop: 11 }}>
              {targets.length > 3 && (
                <input type="search" value={pick} onChange={e => setPick(e.target.value)}
                  placeholder="Search people by name or role…" aria-label="Search next owner"
                  style={{ width: '100%', marginBottom: 10 }} />
              )}
              <div className="choice choicelist" style={{ flexDirection: 'column' }}>
                {shownTargets.map(u => (
                  <button key={u.id} className={next === u.id ? 'on' : ''} onClick={() => setNext(u.id)}>
                    <b>Assign to {u.name}</b>
                    <small>{u.position} · {u.role.toLowerCase()} · {activeCount(state, u.id)} active task{activeCount(state, u.id) === 1 ? '' : 's'}
                      {u.id === task.ownerId ? ' · previous contributor (allowed)' : ''}</small>
                  </button>
                ))}
                {shownTargets.length === 0 && <div className="faint" style={{ fontSize: 12.5, padding: 8 }}>Nobody matches “{pick}”.</div>}
              </div>
            </div>
          )}
        </div>
      )}

      {step === 3 && (
        <div>
          <div className="summary" style={{ marginBottom: 14 }}>
            <div className="srow"><span>Verified progress carried over</span><b className="num">{after}%</b></div>
            <div className="srow"><span>Suggested remaining reward</span><Coin n={remaining} /></div>
          </div>
          <Field label="Priority for the remaining work">
            <select value={newPriority} onChange={e => setNewPriority(e.target.value as typeof newPriority)}>
              <option value="NONE">No priority</option>
              <option value="NORMAL">Normal</option>
              <option value="IMPORTANT">Important</option>
              <option value="URGENT">Urgent</option>
            </select>
          </Field>
          <Field label="Deadline for the remaining work" hint="Leave empty for no deadline.">
            <DateInput value={newDeadline} onChange={setNewDeadline} />
          </Field>
          {/* Files the next owner needs — they join the task brief and stay
              visible in the history for everyone after them. */}
          <AttachField files={files} onChange={setFiles} settings={state.settings}
            label="Attach files for the next owner (optional)" />
          <Field label="Remaining reward for the next owner (Coins)"
            hint={`Suggested: ${remaining} Coins (reward − already paid − this payout). Change only with an explanation below.`}>
            <input type="number" min={0} step={0.5} value={effRemaining}
              onChange={e => setRewardOverride(+e.target.value)} />
          </Field>
          {overriding && (
            <Field label="Why override the suggested amount? (required — recorded in history)">
              <textarea value={overrideReason} onChange={e => setOverrideReason(e.target.value)} autoFocus
                placeholder="e.g. scope grew after the field visit; budget approved by finance…" />
            </Field>
          )}
          {effRemaining < 0 && <div className="neg" style={{ fontSize: 12, marginBottom: 8 }}>⚠ Remaining reward can't be negative.</div>}
        </div>
      )}

      {step === 4 && (
        <div className="summary">
          <div className="srow"><span>Employee reported</span><b className="num">{task.reported}%</b></div>
          <div className="srow"><span>Manager accepted</span><b className="num">{pct}%</b></div>
          <div className="srow"><span>Verified progress</span><b className="num">{task.verified}% → {after}%</b></div>
          <div className="srow"><span>Payout to {owner?.name}</span><Coin n={payout} sign /></div>
          <div className="srow"><span>Audience</span><b>{audience === 'MANAGEMENT' ? 'Management only' : audience === 'PRIVATE' ? 'Private — one person' : 'Employees'}{audience !== task.audience ? ' (changed)' : ''}</b></div>
          <div className="srow"><span>Next owner</span><b>{nextUser ? nextUser.name : audience === 'MANAGEMENT' ? 'Management pool' : 'Marketplace (any employee)'}</b></div>
          <div className="srow"><span>Remaining reward</span><Coin n={effRemaining} />{overriding && <span className="faint" style={{ fontSize: 11 }}> (override — suggested {remaining})</span>}</div>
          <div className="srow"><span>Priority</span><PriBadge p={newPriority} /></div>
          <div className="srow"><span>Deadline</span><b>{/^\d{4}-\d{2}-\d{2}$/.test(newDeadline) ? fmtDate(newDeadline) : 'No deadline'}</b></div>
          {/* Reason must remain fully readable (M1-C C / M1-D D5): its own
              full-width block, NOT a squeezed flex cell — left-aligned,
              pre-wrap, expands vertically without any height limit, so even
              a very long multi-line reason renders completely. */}
          <div className="srow" style={{ display: 'block' }}>
            <span style={{ display: 'block', color: 'var(--muted)', marginBottom: 5 }}>Reason</span>
            <span data-testid="handoff-confirm-reason"
              style={{ display: 'block', textAlign: 'left', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', lineHeight: 1.55, color: 'var(--ink)' }}>{reason}</span>
          </div>
          {files.length > 0 && (
            <div className="srow"><span>Files to the brief</span>
              <span style={{ display: 'flex', gap: 5, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {files.map((f, i) => <span key={i} className="chip">📎 {f.name}</span>)}
              </span>
            </div>
          )}
          {overriding && (
            <div className="srow" style={{ display: 'block' }}>
              <span style={{ display: 'block', color: 'var(--muted)', marginBottom: 5 }}>Override explanation</span>
              <span data-testid="handoff-confirm-override"
                style={{ display: 'block', textAlign: 'left', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', lineHeight: 1.55, color: 'var(--ink)' }}>{overrideReason}</span>
            </div>
          )}
        </div>
      )}

      <div className="actionbar" style={{ position: 'static', margin: '14px -18px -18px' }}>
        {step > 0 && <button className="btn" onClick={() => setStep(step - 1)}>Back</button>}
        <div className="spacer" style={{ flex: 1 }} />
        {step < 4
          ? <button className="btn primary" disabled={!canNext} onClick={() => setStep(step + 1)}>Continue</button>
          : <button className="btn primary" onClick={finish}>Confirm handoff</button>}
      </div>
    </Modal>
  )
}
