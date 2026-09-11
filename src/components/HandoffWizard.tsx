import { useState } from 'react'
import { useStore, useMe } from '../store'
import { partialPayout, activeCount, capacityLimit, capacityReached } from '../domain/engine'
import type { Attachment, Audience, Task } from '../domain/engine'
import { AttachField, Coin, DateInput, Field, Modal, PriBadge, Seg, coins, fmtDate, roleKey } from '../ui'
import { useI18n, fmtPct } from '../i18n'

/* Handoff wizard — the five canonical steps ─────────────────────────── */
export function HandoffWizard({ open, onClose, task }: { open: boolean; onClose: () => void; task: Task }) {
  const { t: tr } = useI18n()
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
  /* The wizard stays mounted between tasks (modal swap) — reset all step
     state when a different task is opened, or a stale audience/mode from
     the previous task would gate the wrong people (founder UAT: manager
     handoff appeared to offer managers only). */
  const [openedFor, setOpenedFor] = useState(task.id)
  if (openedFor !== task.id) {
    setOpenedFor(task.id)
    setStep(0); setPct(0); setReason(''); setFiles([]); setPick('')
    setAudience(task.audience)
    setMode(task.audience === 'PRIVATE' ? 'SPECIFIC' : 'AVAILABLE')
    setNext(task.audience === 'PRIVATE' ? '' : 'AVAILABLE')
    setNewPriority(task.priority)
    setNewDeadline(task.deadline ? task.deadline.slice(0, 10) : '')
    setRewardOverride(null); setOverrideReason('')
  }

  const owner = state.users.find(u => u.id === task.ownerId)
  /* Targets follow the chosen audience; admins are never assignable. */
  const targets = state.users.filter(u =>
    (audience === 'EMPLOYEES' ? u.role === 'EMPLOYEE'
      : audience === 'MANAGEMENT' ? u.role === 'MANAGER'
      : u.role !== 'ADMIN') && u.id !== me.id)
  const shownTargets = pick.trim()
    ? targets.filter(u => (u.name + ' ' + u.position).toLowerCase().includes(pick.trim().toLowerCase()))
    : targets
  const poolLabel = audience === 'MANAGEMENT' ? tr('task.poolManagementShort') : tr('common.marketplace')
  /* N3: sentence-inline role words (lowercase in en: "Specific employee"),
     distinct from the standalone capitalized common.* labels. */
  const personLabel = audience === 'MANAGEMENT' ? tr('handoff.role.manager') : audience === 'PRIVATE' ? tr('handoff.role.person') : tr('handoff.role.employee')
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
    step === 2 ? (mode === 'AVAILABLE' && audience !== 'PRIVATE' ? true : !!next && !capacityReached(state, next)) :
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

  const steps = ['handoff.step.contribution', 'handoff.step.why', 'handoff.step.nextOwner', 'handoff.step.remaining', 'handoff.step.confirmation'].map(k => tr(k))

  return (
    <Modal open={open} onClose={onClose} wide
      dirty={!!(reason.trim() || overrideReason.trim())}
      title={<>{tr('handoff.title')} — <span dir="auto">{task.title}</span><small>{tr('handoff.stepOf', { n: step + 1, total: steps.length })} · {steps[step]}</small></>}>
      <div className="steps">
        {steps.map((_, i) => <i key={i} className={i < step ? 'done' : i === step ? 'on' : ''} />)}
      </div>

      {step === 0 && (
        <div>
          <p className="dim" style={{ fontSize: 12.5, marginBottom: 14 }} dir="auto">
            {tr('handoff.contributionPrompt', { name: owner?.name ?? '', percent: fmtPct(task.reported) })}
          </p>
          <div className="range-row">
            <input type="range" min={0} max={maxPct} step={5} value={pct} onChange={e => setPct(+e.target.value)} />
            <span className="range-val">{fmtPct(pct)}</span>
          </div>
          <div className="summary" style={{ marginTop: 16 }}>
            <div className="srow"><span>{tr('handoff.acceptedContribution')}</span><b className="num">{fmtPct(pct)}</b></div>
            <div className="srow"><span dir="auto">{tr('handoff.payoutTo', { name: owner?.name ?? '' })} <span className="faint">{tr('task.payoutFormulaLong')}</span></span><Coin n={payout} /></div>
            <div className="srow"><span>{tr('handoff.verifiedAfter')}</span><b className="num">{fmtPct(task.verified)} → {fmtPct(after)}</b></div>
          </div>
        </div>
      )}

      {step === 1 && (
        <Field label={tr('handoff.whyRequired')}>
          <textarea dir={reason ? 'auto' : undefined} value={reason} onChange={e => setReason(e.target.value)} autoFocus
            placeholder={tr('handoff.placeholder.why')} />
        </Field>
      )}

      {step === 2 && (
        <div>
          <Seg value={audience} onChange={v => chooseAudience(v as Audience)}
            options={[
              { v: 'EMPLOYEES', label: tr('task.audience.employees') },
              { v: 'PRIVATE', label: tr('task.audience.private') },
              { v: 'MANAGEMENT', label: tr('task.audience.management') },
            ]} />
          <div className="faint" style={{ fontSize: 11.5, marginTop: 7 }}>
            {audience === 'PRIVATE'
              ? tr('task.audienceHint.private')
              : audience === 'MANAGEMENT'
                ? tr('task.audienceHint.management')
                : tr('task.audienceHint.employees')}
          </div>
          {audience !== 'PRIVATE' && (
            <div className="choice" style={{ marginTop: 10 }}>
              <button className={mode === 'AVAILABLE' ? 'on' : ''} onClick={() => chooseMode('AVAILABLE')}>
                <b>{tr('handoff.returnPool', { pool: poolLabel })}</b>
                <small>{tr('handoff.returnPoolHint', { role: personLabel })}</small>
              </button>
              <button className={mode === 'SPECIFIC' ? 'on' : ''} onClick={() => chooseMode('SPECIFIC')}>
                <b>{tr('handoff.specificPerson', { role: personLabel })}</b>
                <small>{tr('handoff.specificPersonHint')}</small>
              </button>
            </div>
          )}
          {(mode === 'SPECIFIC' || audience === 'PRIVATE') && (
            <div style={{ marginTop: 11 }}>
              {targets.length > 3 && (
                <input dir={pick ? 'auto' : undefined} type="search" value={pick} onChange={e => setPick(e.target.value)}
                  placeholder={tr('handoff.searchPeople')} aria-label={tr('accessibility.searchNextOwner')}
                  style={{ width: '100%', marginBottom: 10 }} />
              )}
              <div className="choice choicelist" style={{ flexDirection: 'column' }}>
                {shownTargets.map(u => (
                  <button key={u.id} disabled={capacityReached(state, u.id)} className={next === u.id ? 'on' : ''} onClick={() => setNext(u.id)}>
                    <b dir="auto">{tr('handoff.assignTo', { name: u.name })}</b>
                    <small><span dir="auto">{u.position}</span> · <b data-testid={`role-tag-${u.role.toLowerCase()}`}>{tr(roleKey(u.role))}</b> · {tr('capacity.usage', { active: '\u2066' + activeCount(state, u.id), limit: capacityLimit(u) + '\u2069' })}{capacityReached(state, u.id) ? ' · ' + tr('capacity.full') : ''}
                      {u.id === task.ownerId ? ' · ' + tr('handoff.previousContributor') : ''}</small>
                  </button>
                ))}
                {shownTargets.length === 0 && <div className="faint" style={{ fontSize: 12.5, padding: 8 }} dir="auto">{tr('handoff.noMatches', { query: pick })}</div>}
              </div>
            </div>
          )}
        </div>
      )}

      {step === 3 && (
        <div>
          <div className="summary" style={{ marginBottom: 14 }}>
            <div className="srow"><span>{tr('handoff.verifiedCarried')}</span><b className="num">{fmtPct(after)}</b></div>
            <div className="srow"><span>{tr('handoff.suggestedRemainingReward')}</span><Coin n={remaining} /></div>
          </div>
          <Field label={tr('handoff.priorityRemaining')}>
            <select value={newPriority} onChange={e => setNewPriority(e.target.value as typeof newPriority)}>
              <option value="NONE">{tr('task.priority.none')}</option>
              <option value="NORMAL">{tr('task.priority.normal')}</option>
              <option value="IMPORTANT">{tr('task.priority.important')}</option>
              <option value="URGENT">{tr('task.priority.urgent')}</option>
            </select>
          </Field>
          <Field label={tr('handoff.deadlineRemaining')} hint={tr('task.help.noDeadlineHint')}>
            <DateInput value={newDeadline} onChange={setNewDeadline} />
          </Field>
          {/* Files the next owner needs — they join the task brief and stay
              visible in the history for everyone after them. */}
          <AttachField files={files} onChange={setFiles} settings={state.settings}
            label={tr('handoff.attachForNext')} />
          <Field label={tr('handoff.remainingRewardNext')}
            hint={tr('handoff.remainingRewardHint', { coins: coins(remaining) })}>
            <input type="number" min={0} step={0.5} value={effRemaining}
              onChange={e => setRewardOverride(+e.target.value)} />
          </Field>
          {overriding && (
            <Field label={tr('handoff.overrideReason')}>
              <textarea dir={overrideReason ? 'auto' : undefined} value={overrideReason} onChange={e => setOverrideReason(e.target.value)} autoFocus
                placeholder={tr('handoff.placeholder.override')} />
            </Field>
          )}
          {effRemaining < 0 && <div className="neg" style={{ fontSize: 12, marginBottom: 8 }}>⚠ {tr('handoff.negativeReward')}</div>}
        </div>
      )}

      {step === 4 && (
        <div className="summary">
          <div className="srow"><span>{tr('handoff.employeeReported')}</span><b className="num">{fmtPct(task.reported)}</b></div>
          <div className="srow"><span>{tr('handoff.managerAccepted')}</span><b className="num">{fmtPct(pct)}</b></div>
          <div className="srow"><span>{tr('task.field.verifiedProgress')}</span><b className="num">{fmtPct(task.verified)} → {fmtPct(after)}</b></div>
          <div className="srow"><span dir="auto">{tr('handoff.payoutTo', { name: owner?.name ?? '' })}</span><Coin n={payout} sign /></div>
          <div className="srow"><span>{tr('common.audience')}</span><b>{tr(audience === 'MANAGEMENT' ? 'task.audience.management' : audience === 'PRIVATE' ? 'task.audience.privateOnePerson' : 'task.audience.employees')}{audience !== task.audience ? ' (' + tr('common.changed') + ')' : ''}</b></div>
          <div className="srow"><span>{tr('handoff.nextOwner')}</span><b dir="auto">{nextUser ? nextUser.name : audience === 'MANAGEMENT' ? tr('task.assignment.managementPool') : tr('task.marketplaceAnyEmployee')}</b></div>
          <div className="srow"><span>{tr('handoff.remainingReward')}</span><Coin n={effRemaining} />{overriding && <span className="faint" style={{ fontSize: 11 }}> {tr('handoff.overrideNote', { coins: coins(remaining) })}</span>}</div>
          <div className="srow"><span>{tr('common.priority')}</span><PriBadge p={newPriority} /></div>
          <div className="srow"><span>{tr('common.deadline')}</span><b>{/^\d{4}-\d{2}-\d{2}$/.test(newDeadline) ? fmtDate(newDeadline) : tr('date.noDeadline')}</b></div>
          {/* Reason must remain fully readable (M1-C C / M1-D D5): its own
              full-width block, NOT a squeezed flex cell — left-aligned,
              pre-wrap, expands vertically without any height limit, so even
              a very long multi-line reason renders completely. */}
          <div className="srow" style={{ display: 'block' }}>
            <span style={{ display: 'block', color: 'var(--muted)', marginBottom: 5 }}>{tr('common.reason')}</span>
            <span dir="auto" data-testid="handoff-confirm-reason"
              style={{ display: 'block', textAlign: 'start', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', lineHeight: 1.55, color: 'var(--ink)' }}>{reason}</span>
          </div>
          {files.length > 0 && (
            <div className="srow"><span>{tr('handoff.filesToBrief')}</span>
              <span style={{ display: 'flex', gap: 5, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                {files.map((f, i) => <span key={i} className="chip" dir="auto">📎 {f.name}</span>)}
              </span>
            </div>
          )}
          {overriding && (
            <div className="srow" style={{ display: 'block' }}>
              <span style={{ display: 'block', color: 'var(--muted)', marginBottom: 5 }}>{tr('handoff.overrideExplanation')}</span>
              <span dir="auto" data-testid="handoff-confirm-override"
                style={{ display: 'block', textAlign: 'start', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', lineHeight: 1.55, color: 'var(--ink)' }}>{overrideReason}</span>
            </div>
          )}
        </div>
      )}

      <div className="actionbar" style={{ position: 'static', margin: '14px -18px -18px' }}>
        {step > 0 && <button className="btn" onClick={() => setStep(step - 1)}>{tr('handoff.back')}</button>}
        <div className="spacer" style={{ flex: 1 }} />
        {step < 4
          ? <button className="btn primary" disabled={!canNext} onClick={() => setStep(step + 1)}>{tr('handoff.continue')}</button>
          : <button className="btn primary" onClick={finish}>{tr('handoff.confirm')}</button>}
      </div>
    </Modal>
  )
}
