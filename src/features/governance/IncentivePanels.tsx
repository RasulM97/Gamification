/* Catalog and observation panels for the Incentives workspace (Cohesion F1).
 * Rules and Policies are admin configuration; Safety and Shadow are admin
 * observation surfaces; Payouts lists executed economic effects. All panels
 * share the loading/error/retry discipline from useGovData. */
import { useState } from 'react'
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { Coin, Empty, Modal, Panel, Field, ago } from '../../ui'
import { governance } from './source'
import { useGovData } from './hooks'
import type { AsyncState } from './hooks'

function panelState<T>(s: AsyncState<{ items: T[] }>, t: (k: string) => string) {
  if (s.loading) return <p role="status" style={{ padding: 16 }}>{t('common.loading')}</p>
  if (s.error) return <p role="alert" style={{ padding: 16 }}>{t('incentives.error')} <button className="btn" onClick={s.reload}>{t('incentives.retry')}</button></p>
  return null
}

export function RulesPanel({ onChain }: { onChain: (candidateId: string) => void }) {
  const { t } = useI18n()
  const rules = useGovData(() => governance.listRules())
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [eventType, setEventType] = useState('')
  const [reward, setReward] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState(false)

  const create = async () => {
    setBusy(true); setFormError(false)
    try {
      await governance.createRule({
        name: name.trim(), eventType: eventType.trim(), active: true, priority: 0,
        outcome: { kind: 'INCENTIVE', data: { proposedReward: Number(reward) } },
      })
      setCreateOpen(false); setName(''); setEventType(''); setReward('')
      rules.reload()
    } catch { setFormError(true) } finally { setBusy(false) }
  }
  const toggle = async (id: string, active: boolean) => {
    try { await governance.setRuleActive(id, active); rules.reload() } catch { rules.reload() }
  }

  return (
    <Panel pad={false} title={t('incentives.rules.title')}
      right={<button className="btn primary" onClick={() => setCreateOpen(true)}>+ {t('incentives.rules.create')}</button>}>
      {panelState(rules, t)}
      {rules.data && rules.data.items.length === 0 &&
        <Empty title={t('incentives.rules.empty')} hint={t('incentives.rules.emptyHint')} />}
      {rules.data?.items.map(r => (
        <div className="aitem" key={r.id}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <b dir="auto">{r.name}</b>
              <span className={'bd ' + (r.active ? 'bd-normal' : 'bd-none')}>
                {t(r.active ? 'common.active' : 'common.inactive')}</span>
              <span className="bd bd-none">v{r.version}</span>
              {typeof r.outcome?.data?.proposedReward === 'number' &&
                <Coin n={r.outcome.data.proposedReward as number} />}
            </div>
            <div className="dim" style={{ fontSize: 12, marginTop: 4 }}>
              {t('incentives.rules.listensFor')}: <code>{r.eventType}</code> · {ago(r.updatedAt)}
            </div>
            {r.description && <div className="dim" style={{ fontSize: 12 }} dir="auto">{r.description}</div>}
          </div>
          <button className="btn" onClick={() => toggle(r.id, !r.active)}>
            {t(r.active ? 'incentives.action.deactivate' : 'incentives.action.activate')}</button>
        </div>
      ))}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={t('incentives.rules.create')}>
        {formError && <p role="alert">{t('incentives.error')}</p>}
        <Field label={t('common.title')}>
          <input value={name} maxLength={120} onChange={e => setName(e.target.value)} autoFocus />
        </Field>
        <Field label={t('incentives.rules.eventType')}>
          <input value={eventType} maxLength={128} onChange={e => setEventType(e.target.value)}
            placeholder="github.pull_request.merged" dir="ltr" />
        </Field>
        <Field label={t('incentives.rules.proposedReward')}>
          <input type="number" min="0.5" step="0.5" value={reward} onChange={e => setReward(e.target.value)} />
        </Field>
        <div className="actionbar" style={{ position: 'static', margin: '4px -18px -18px' }}>
          <button className="btn" onClick={() => setCreateOpen(false)}>{t('common.cancel')}</button>
          <button className="btn primary" disabled={busy || !name.trim() || !eventType.trim() || !(Number(reward) > 0)}
            onClick={create}>{t('common.create')}</button>
        </div>
      </Modal>
    </Panel>
  )
}

export function PoliciesPanel() {
  const { t } = useI18n()
  const policies = useGovData(() => governance.listPolicies())
  return (
    <Panel pad={false} title={t('incentives.policies.title')}>
      {panelState(policies, t)}
      {policies.data && policies.data.items.length === 0 && <Empty title={t('incentives.policies.empty')} />}
      {policies.data?.items.map(p => (
        <div className="aitem" key={p.id}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <b dir="auto">{p.name}</b>
              <span className={'bd ' + (p.decision === 'ALLOW' ? 'bd-normal' : p.decision === 'BLOCK' ? 'bd-urgent' : 'bd-important')}>
                {t('incentives.decision.' + p.decision)}</span>
              <span className={'bd ' + (p.active ? 'bd-normal' : 'bd-none')}>
                {t(p.active ? 'common.active' : 'common.inactive')}</span>
              <span className="bd bd-none">v{p.version}</span>
            </div>
            <div className="dim" style={{ fontSize: 12, marginTop: 4 }}>
              {p.eventType ? <code>{p.eventType}</code> : t('incentives.policies.allEvents')} · {ago(p.updatedAt)}
            </div>
            {p.description && <div className="dim" style={{ fontSize: 12 }} dir="auto">{p.description}</div>}
          </div>
        </div>
      ))}
    </Panel>
  )
}

export function SafetyPanel({ onChain }: { onChain: (candidateId: string) => void }) {
  const { t } = useI18n()
  const evals = useGovData(() => governance.listSafetyEvaluations())
  return (
    <Panel pad={false} title={t('incentives.safety.title')}>
      <p className="dim" style={{ padding: '0 16px', fontSize: 12.5 }}>{t('incentives.safety.note')}</p>
      {panelState(evals, t)}
      {evals.data && evals.data.items.length === 0 && <Empty title={t('incentives.safety.empty')} />}
      {evals.data?.items.map(ev => (
        <div className="aitem" key={ev.id}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span className={'bd ' + (ev.outcome === 'CLEAR' ? 'bd-normal' : ev.outcome === 'OBSERVE' ? 'bd-none' : 'bd-urgent')}>
                {t('incentives.safety.outcome.' + ev.outcome)}</span>
              <span className="dim" style={{ fontSize: 12 }}>{ago(ev.createdAt)}</span>
            </div>
            {ev.findings.length > 0 && (
              <div className="dim" style={{ fontSize: 12, marginTop: 4 }}>
                {ev.findings.map(f => t('incentives.safety.finding.' + String(f.findingType), {})).join(' · ')}
              </div>
            )}
          </div>
          <button className="btn" onClick={() => onChain(ev.candidateId)}>{t('incentives.viewChain')}</button>
        </div>
      ))}
    </Panel>
  )
}

export function ShadowPanel({ onChain }: { onChain: (candidateId: string) => void }) {
  const { state } = useStore()
  const { t } = useI18n()
  const shadow = useGovData(() => governance.listShadow())
  const name = (id: string | null) => id ? (state.users.find(u => u.id === id)?.name ?? id) : '—'
  return (
    <Panel pad={false} title={t('incentives.shadow.title')}>
      <p className="dim" style={{ padding: '0 16px', fontSize: 12.5 }}>{t('incentives.shadow.note')}</p>
      {panelState(shadow, t)}
      {shadow.data && shadow.data.items.length === 0 && <Empty title={t('incentives.shadow.empty')} hint={t('incentives.shadow.emptyHint')} />}
      {shadow.data?.items.map(s => (
        <div className="aitem" key={s.id}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span className={'bd ' + (s.outcome === 'AUTHORIZED' ? 'bd-normal' : s.outcome === 'BLOCKED' ? 'bd-urgent' : 'bd-important')}>
                {t('incentives.shadow.outcome.' + s.outcome)}</span>
              <span className="bd bd-none">{t('incentives.shadow.hypothetical')}</span>
              {s.proposedAmount && <Coin n={Number(s.proposedAmount)} />}
            </div>
            <div className="dim" style={{ fontSize: 12, marginTop: 4 }}>
              {name(s.recipientUserId)} · {ago(s.createdAt)}
            </div>
          </div>
          <button className="btn" onClick={() => onChain(s.candidateId)}>{t('incentives.viewChain')}</button>
        </div>
      ))}
    </Panel>
  )
}

export function PayoutsPanel({ onChain }: { onChain: (candidateId: string) => void }) {
  const { state } = useStore()
  const { t } = useI18n()
  const effects = useGovData(() => governance.listEffects())
  const name = (id: string) => state.users.find(u => u.id === id)?.name ?? id
  return (
    <Panel pad={false} title={t('incentives.payouts.title')}>
      {panelState(effects, t)}
      {effects.data && effects.data.items.length === 0 && <Empty title={t('incentives.payouts.empty')} />}
      {effects.data?.items.map(e => (
        <div className="aitem" key={e.id}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <Coin n={Number(e.amount)} sign />
              <b dir="auto">{name(e.beneficiaryUserId)}</b>
              <span className={'bd ' + (e.status === 'ISSUED' ? 'bd-normal' : 'bd-urgent')}>
                {t('incentives.payouts.status.' + e.status)}</span>
            </div>
            <div className="dim" style={{ fontSize: 12, marginTop: 4 }}>
              {ago(e.createdAt)}
              {e.reversal && <> · {t('incentives.payouts.reversedNote', { reason: e.reversal.reasonCode })}</>}
            </div>
          </div>
          <button className="btn" onClick={() => onChain(e.candidateId)}>{t('incentives.viewChain')}</button>
        </div>
      ))}
    </Panel>
  )
}
