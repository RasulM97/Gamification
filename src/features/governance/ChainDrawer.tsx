/* Provenance drawer (Cohesion F1) — one immutable chain from activity to
 * governed outcome: Event → Rule candidate → Policy decision → Safety →
 * Approval → Economic effect. Read-only reconstruction through the
 * governance source; the chain is rendered in the user's language without
 * exposing internal IDs as primary content. */
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { Coin, Drawer, ago } from '../../ui'
import { governance } from './source'
import { useGovData } from './hooks'
import type {
  ApprovalItem, CandidateItem, DecisionItem, EffectItem, EventItem, SafetyEvalItem,
} from './types'

interface Chain {
  candidate: CandidateItem | null; event: EventItem | null; decision: DecisionItem | null
  safety: SafetyEvalItem | null; approvals: ApprovalItem[]; effects: EffectItem[]
}

async function loadChain(candidateId: string): Promise<Chain> {
  const candidate = await governance.getCandidate(candidateId)
  const [event, decisions, safety, pending, approved, rejected] = await Promise.all([
    candidate ? governance.getEvent(candidate.canonicalEventId) : Promise.resolve(null),
    governance.listDecisions(candidateId),
    governance.listSafetyEvaluations(),
    governance.listApprovals('PENDING'),
    governance.listApprovals('APPROVED'),
    governance.listApprovals('REJECTED'),
  ])
  const decision = decisions.items[0] ?? null
  const effects = decision ? (await governance.listEffects(decision.decisionId)).items : []
  return {
    candidate, event, decision,
    safety: safety.items.find(s => s.candidateId === candidateId) ?? null,
    approvals: [...pending.items, ...approved.items, ...rejected.items]
      .filter(a => a.candidateId === candidateId),
    effects,
  }
}

export function ChainDrawer({ candidateId, onClose }: { candidateId: string | null; onClose: () => void }) {
  const { state } = useStore()
  const { t } = useI18n()
  const { data, loading, error, reload } = useGovData(
    () => candidateId ? loadChain(candidateId) : Promise.resolve(null), [candidateId])
  const name = (id: string | null | undefined) =>
    id ? (state.users.find(u => u.id === id)?.name ?? id) : '—'
  const reward = data?.candidate && typeof data.candidate.data?.proposedReward === 'number'
    ? data.candidate.data.proposedReward as number : null

  const step = (label: string, ok: boolean, detail: React.ReactNode) => (
    <div className="dsec" style={{ display: 'flex', gap: 10 }}>
      <span aria-hidden style={{ color: ok ? 'var(--info)' : 'var(--faint)' }}>{ok ? '●' : '○'}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <b style={{ fontSize: 13 }}>{label}</b>
        <div className="dim" style={{ fontSize: 12.5 }}>{detail}</div>
      </div>
    </div>
  )

  return (
    <Drawer open={!!candidateId} onClose={onClose} title={t('incentives.chain.title')}>
      {loading && <p role="status">{t('common.loading')}</p>}
      {error && <p role="alert">{t('incentives.error')} <button className="btn" onClick={reload}>{t('incentives.retry')}</button></p>}
      {data && !loading && (
        <>
          {reward !== null && (
            <div className="dsec" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Coin n={reward} />
              <span className="dim" style={{ fontSize: 12.5 }}>{t('incentives.chain.proposedFor', { name: name(data.event?.subjectId) })}</span>
            </div>
          )}
          {step(t('incentives.chain.event'), !!data.event,
            data.event ? <><code>{data.event.type}</code> · {ago(data.event.occurredAt)}
              {data.event.sourceKind === 'TRUSTED_CONNECTOR' && <> · GitHub</>}</> : t('incentives.chain.none'))}
          {step(t('incentives.chain.rule'), !!data.candidate,
            data.candidate ? <><span dir="auto">{String(data.candidate.ruleSnapshot?.name ?? '')}</span> · v{data.candidate.ruleVersion}</> : t('incentives.chain.none'))}
          {step(t('incentives.chain.policy'), !!data.decision,
            data.decision ? <>{t('incentives.decision.' + data.decision.effectiveDecision)} · {ago(data.decision.createdAt)}
              {data.decision.explanation && <div dir="auto">{data.decision.explanation}</div>}</> : t('incentives.chain.none'))}
          {step(t('incentives.chain.safety'), !!data.safety,
            data.safety ? t('incentives.safety.outcome.' + data.safety.outcome) : t('incentives.chain.none'))}
          {step(t('incentives.chain.approval'), data.approvals.length > 0,
            data.approvals.length === 0 ? t('incentives.chain.notRequired') :
              data.approvals.map(a => (
                <div key={a.id}>
                  {t('incentives.status.' + a.status)}
                  {a.finalDecision && <> · {name(a.finalDecision.decidedBy)} · {ago(a.finalDecision.decidedAt)}</>}
                </div>
              )))}
          {step(t('incentives.chain.payout'), data.effects.length > 0,
            data.effects.length === 0 ? t('incentives.chain.noPayout') :
              data.effects.map(e => (
                <div key={e.id}>
                  <Coin n={Number(e.amount)} sign /> {name(e.beneficiaryUserId)} · {t('incentives.payouts.status.' + e.status)}
                  {e.reversal && <> · {t('incentives.payouts.reversedNote', { reason: e.reversal.reasonCode })}</>}
                </div>
              )))}
        </>
      )}
    </Drawer>
  )
}
