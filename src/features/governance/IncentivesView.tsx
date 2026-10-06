/* Incentives workspace (Cohesion F1, WS2) — one discoverable surface for the
 * governed incentive pipeline instead of isolated engineering concepts.
 * Tabs are authority-scoped: management sees its scoped approval queue;
 * admins additionally see Rules, Policies, Safety and Shadow. Payouts
 * (executed economic history) live in the Admin control plane under
 * Audit & economics (WS2-B). Provenance drill-down is role-specific:
 * managers get business-language decision context, admins the full chain.
 * All data flows through the governance source (server API or demo
 * fixtures) — views never call fetch directly. */
import { useState } from 'react'
import { useStore, useMe } from '../../store'
import { useI18n } from '../../i18n'
import { Empty, Panel, Seg, ago } from '../../ui'
import { governance } from './source'
import { useGovData } from './hooks'
import { RulesPanel, PoliciesPanel, SafetyPanel, ShadowPanel } from './IncentivePanels'
import { ChainDrawer } from './ChainDrawer'
import { ApprovalContextDrawer } from './ApprovalContextDrawer'

type Tab = 'approvals' | 'rules' | 'policies' | 'safety' | 'shadow'

const REASON_CODES = ['MERIT', 'REVIEWED', 'POLICY_OK', 'INSUFFICIENT_EVIDENCE', 'POLICY_VIOLATION', 'OTHER']

function ApprovalsPanel({ onOpen }: { onOpen: (approvalId: string, candidateId: string) => void }) {
  const { state } = useStore()
  const { t } = useI18n()
  const [status, setStatus] = useState('PENDING')
  const [busy, setBusy] = useState<string | null>(null)
  const [reason, setReason] = useState('MERIT')
  const [note, setNote] = useState('')
  const { data, loading, error, reload } = useGovData(() => governance.listApprovals(status), [status])
  const name = (id: string) => state.users.find(u => u.id === id)?.name ?? id

  const decide = async (id: string, decision: 'APPROVED' | 'REJECTED') => {
    setBusy(id)
    try { await governance.decideApproval(id, decision, reason, note.trim() || undefined); reload() }
    catch { /* error state surfaces via reload/list refresh */ reload() }
    finally { setBusy(null) }
  }

  return (
    <Panel pad={false} title={t('incentives.approvals.title')}
      right={<Seg value={status} onChange={setStatus} options={[
        { v: 'PENDING', label: t('incentives.approvals.pending') },
        { v: 'APPROVED', label: t('incentives.approvals.approved') },
        { v: 'REJECTED', label: t('incentives.approvals.rejected') },
      ]} />}>
      {loading && <p role="status" style={{ padding: 16 }}>{t('common.loading')}</p>}
      {error && <p role="alert" style={{ padding: 16 }}>{t('incentives.error')} <button className="btn" onClick={reload}>{t('incentives.retry')}</button></p>}
      {data && data.items.length === 0 && <Empty title={t('incentives.approvals.empty')} hint={t('incentives.approvals.emptyHint')} />}
      {data?.items.map(a => (
        <div className="aitem" key={a.id}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <b>{t(a.trigger === 'INCENTIVE_SAFETY' ? 'incentives.approvals.safetyReview' : 'incentives.approvals.incentiveRequest')}</b>
              <span className="bd bd-normal">{t('incentives.authority.' + a.requiredAuthority)}</span>
              <span className={'bd ' + (a.status === 'PENDING' ? 'bd-important' : a.status === 'APPROVED' ? 'bd-normal' : 'bd-urgent')}>
                {t('incentives.status.' + a.status)}</span>
            </div>
            <div className="dim" style={{ fontSize: 12, marginTop: 4 }}>
              {t('common.requestedAgo', { time: ago(a.requestedAt) })} · {name(a.requestedBy)}
              {a.finalDecision && <> · {t('incentives.decidedBy', { name: name(a.finalDecision.decidedBy) })} {ago(a.finalDecision.decidedAt)}</>}
            </div>
            {a.finalDecision?.note && <div className="dim" style={{ fontSize: 12 }} dir="auto">{a.finalDecision.note}</div>}
          </div>
          <button className="btn" onClick={() => onOpen(a.id, a.candidateId)}>{t('incentives.viewChain')}</button>
          {a.status === 'PENDING' && (
            <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <select className="btn" value={reason} onChange={e => setReason(e.target.value)} aria-label={t('common.reason')}>
                {REASON_CODES.map(c => <option key={c} value={c}>{t('incentives.reason.' + c)}</option>)}
              </select>
              <input className="btn" style={{ minWidth: 120 }} value={note} placeholder={t('incentives.noteOptional')}
                onChange={e => setNote(e.target.value)} />
              <button className="btn primary" disabled={busy === a.id} onClick={() => decide(a.id, 'APPROVED')}>
                {t('incentives.action.approve')}</button>
              <button className="btn" disabled={busy === a.id} onClick={() => decide(a.id, 'REJECTED')}>
                {t('incentives.action.reject')}</button>
            </span>
          )}
        </div>
      ))}
    </Panel>
  )
}

export function IncentivesView() {
  const me = useMe()
  const { state } = useStore()
  const { t } = useI18n()
  const isAdmin = me.role === 'ADMIN'
  const shadowEnabled = state.capabilities?.SHADOW_MODE !== false
  const tabs: Tab[] = isAdmin
    ? ['approvals', 'rules', 'policies', 'safety', ...(shadowEnabled ? ['shadow' as Tab] : [])]
    : ['approvals']
  const [tab, setTab] = useState<Tab>('approvals')
  const [chainCandidate, setChainCandidate] = useState<string | null>(null)
  const [contextApproval, setContextApproval] = useState<string | null>(null)
  const active = tabs.includes(tab) ? tab : 'approvals'
  /* WS2-A: the drill-down follows the caller's authority — admins open the
     full provenance chain; managers open business-language decision context
     backed by an endpoint they are actually authorized to read. */
  const open = (approvalId: string, candidateId: string) =>
    isAdmin ? setChainCandidate(candidateId) : setContextApproval(approvalId)

  return (
    <div className="wrap">
      <div className="toolbar" style={{ marginBottom: 12 }}>
        <Seg value={active} onChange={v => setTab(v as Tab)} options={tabs.map(v => ({ v, label: t('incentives.tab.' + v) }))} />
      </div>
      {active === 'approvals' && <ApprovalsPanel onOpen={open} />}
      {active === 'rules' && isAdmin && <RulesPanel onChain={setChainCandidate} />}
      {active === 'policies' && isAdmin && <PoliciesPanel />}
      {active === 'safety' && isAdmin && <SafetyPanel onChain={setChainCandidate} />}
      {active === 'shadow' && isAdmin && shadowEnabled && <ShadowPanel onChain={setChainCandidate} />}
      <ChainDrawer candidateId={chainCandidate} onClose={() => setChainCandidate(null)} />
      <ApprovalContextDrawer approvalId={contextApproval} onClose={() => setContextApproval(null)} />
    </div>
  )
}
