import { useState } from 'react'
import { useMe, useStore } from '../../store'
import { useI18n, fmtDateL } from '../../i18n'
import { Field, Panel, roleKey } from '../../ui'
import { coinsInCirculation } from '../../domain/engine'
import { CapacityControl } from '../../components/CapacityControl'
import { UploadPolicyForm } from '../../components/UploadPolicyForm'
import { PeopleSetup } from './PeopleSetup'
import { readiness } from './operations'

const steps = ['company', 'people', 'capacity', 'rewardOps', 'uploads', 'review']
export function OnboardingView({ onRewards }: { onRewards?: () => void }) {
  const { state, setup, dispatch } = useStore(), me = useMe(), { t } = useI18n()
  const complete = !state.onboarding || state.onboarding.status === 'COMPLETED'
  const [open, setOpen] = useState(!complete), [step, setStep] = useState(complete ? 5 : 0)
  const [name, setName] = useState(state.company), [busy, setBusy] = useState(false), [error, setError] = useState(false)
  const checks = readiness(state)
  const run = async (kind: 'begin' | 'complete' | 'company') => {
    setBusy(true); setError(false)
    try { await setup(kind === 'company' ? { type: kind, name } : { type: kind }) }
    catch { setError(true) } finally { setBusy(false) }
  }
  if (me.role !== 'ADMIN') return null
  return <Panel title={t('setup.title')} right={<button className="btn" onClick={() => setOpen(!open)}>{t(open ? 'common.close' : 'setup.open')}</button>}>
    <p>{t(complete ? 'setup.completed' : 'setup.intro')}</p>
    {state.onboarding?.completedAt && <p>{fmtDateL(state.onboarding.completedAt)}</p>}
    {open && <>
      <nav aria-label={t('setup.title')} style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBlock: 16 }}>
        {steps.map((s, i) => <button key={s} className={`btn ${i === step ? 'primary' : ''}`} aria-current={i === step ? 'step' : undefined} onClick={() => { setStep(i); setError(false) }}>{i + 1}. {t(`setup.step.${s}`)}</button>)}
      </nav>
      <h3>{t(`setup.step.${steps[step]}`)}</h3>
      {step === 0 && <form onSubmit={e => { e.preventDefault(); if (!busy) void run('company') }}>
        <Field label={t('setup.companyName')}><input dir="auto" required maxLength={200} value={name} onChange={e => setName(e.target.value)} /></Field>
        <button className="btn primary" disabled={busy || !name.trim()}>{t('setup.save')}</button>
      </form>}
      {step === 1 && <PeopleSetup />}
      {step === 2 && <><p>{t('setup.capacityHint')}</p>{state.users.map(u => <div key={u.id} style={{ display: 'flex', gap: 16, alignItems: 'center', marginBlock: 12 }}><span dir="auto">{u.name}</span><span>{t(roleKey(u.role))}</span><CapacityControl user={u} /></div>)}</>}
      {step === 3 && <><p>{t('setup.rewardHint')}</p>{state.users.filter(u => u.role !== 'ADMIN').map(u => <div key={u.id} style={{ display: 'flex', gap: 16, marginBlock: 12 }}>
        <span dir="auto">{u.name}</span><button className="btn" aria-label={t('admin.fulfillToggleAria', { name: u.name })} onClick={() => dispatch({ type: 'TOGGLE_FULFILL_PERMISSION', by: me.id, userId: u.id })}>{t(u.canFulfillRewards ? 'admin.grantedRevoke' : 'admin.grant')}</button>
      </div>)}<button className="btn" onClick={onRewards} disabled={!onRewards}>{t('setup.optionalReward')}</button></>}
      {step === 4 && <><p>{t('admin.uploadPolicyNote')}</p><UploadPolicyForm /></>}
      {step === 5 && <>
        <dl className="kv">
          <dt>{t('setup.step.company')}</dt><dd dir="auto">{state.company}</dd>
          {(['ADMIN', 'MANAGER', 'EMPLOYEE'] as const).map(role => <div key={role} style={{ display: 'contents' }}><dt>{t(roleKey(role))}</dt><dd>{state.users.filter(u => u.role === role).length}</dd></div>)}
          <dt>{t('setup.step.capacity')}</dt><dd>{state.users.filter(u => u.role !== 'ADMIN').map(u => <div key={u.id}><bdi>{u.name}</bdi>: {u.maxActiveTasks ?? 2}</div>)}</dd>
          <dt>{t('setup.step.rewardOps')}</dt><dd>{state.users.filter(u => u.role === 'ADMIN' || u.canFulfillRewards).length}</dd>
          <dt>{t('common.rewards')}</dt><dd>{state.rewards.length}</dd>
          <dt>{t('admin.maxFileSize')}</dt><dd>{state.settings.maxFileSizeMb}</dd>
          <dt>{t('admin.maxSubmissionTotal')}</dt><dd>{state.settings.maxSubmissionTotalMb}</dd>
          <dt>{t('common.tasks')}</dt><dd>{state.tasks.length}</dd>
          <dt>{t('common.coins')}</dt><dd>{coinsInCirculation(state)}</dd>
        </dl>
        <p>{t('setup.zero')}</p>
        <h4>{t('setup.blockers')}</h4>{checks.blockers.length ? <ul>{checks.blockers.map(k => <li key={k}>{t(`setup.blocker.${k}`)}</li>)}</ul> : <p>{t('setup.ready')}</p>}
        <h4>{t('setup.warnings')}</h4><ul>{checks.warnings.map(k => <li key={k}>{t(`setup.warning.${k}`)}</li>)}</ul>
        {!complete && <button className="btn primary" disabled={busy || !!checks.blockers.length} onClick={() => void run('complete')}>{t('setup.finish')}</button>}
      </>}
      {error && <p className="neg" role="alert">{t('setup.error')}</p>}
      <div style={{ display: 'flex', gap: 12, marginBlockStart: 20 }}>
        <button className="btn" disabled={step === 0} onClick={() => setStep(step - 1)}>{t('setup.back')}</button>
        <button className="btn" disabled={step === 5 || busy} onClick={async () => { if (!complete) await run('begin'); setStep(Math.min(5, step + 1)) }}>{t('setup.next')}</button>
      </div>
    </>}
  </Panel>
}
