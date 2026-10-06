/* Provenance drawer (WS2-A) — admin/auditor view: a business-language summary
 * first, then the complete technical chain on the same screen:
 * Event → Rule candidate → Policy decision → Safety → Approval → Effect.
 * One composed, admin-authorized read from the provenance projection; the
 * chain is rendered in the user's language without exposing internal IDs as
 * primary content. */
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { Coin, Drawer, ago } from '../../ui'
import { governance } from './source'
import { useGovData } from './hooks'
import { EventPhrase } from './ProvenanceText'

export function ChainDrawer({ candidateId, onClose }: { candidateId: string | null; onClose: () => void }) {
  const { state } = useStore()
  const { t } = useI18n()
  const { data, loading, error, reload } = useGovData(
    () => candidateId ? governance.getChain(candidateId) : Promise.resolve(null), [candidateId])
  const name = (id: string | null | undefined) =>
    id ? (state.users.find(u => u.id === id)?.name ?? id) : '—'
  const summary = data?.summary

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
      {data && summary && !loading && (
        <>
          {/* Business language first — a reader understands the outcome before
              any technical detail. */}
          <div className="dsec">
            <span className="eyebrow">{t('provenance.summary.title')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }}>
              <EventPhrase type={summary.eventType} />
              {summary.occurredAt && <span className="dim"> · {ago(summary.occurredAt)}</span>}
              {summary.subjectId && <div className="dim" style={{ marginTop: 4 }}>{name(summary.subjectId)}</div>}
            </div>
            <div style={{ marginTop: 8, fontSize: 13, display: 'grid', gap: 4 }}>
              {summary.ruleName && <span>{t('provenance.rule')}: <b dir="auto">{summary.ruleName}</b></span>}
              {summary.policyExplanation && <span className="dim" dir="auto">{summary.policyExplanation}</span>}
              {summary.safetyOutcome && <span>{t('provenance.safety.' + summary.safetyOutcome)}</span>}
              <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                {summary.proposedReward !== null && <Coin n={summary.proposedReward} />}
                {data.effects.length > 0
                  ? <span className={'bd ' + (data.effects[0].status === 'ISSUED' ? 'bd-normal' : 'bd-urgent')}>
                      {t('provenance.status.' + data.effects[0].status)}</span>
                  : <span className="bd bd-none">{t('incentives.chain.noPayout')}</span>}
              </span>
            </div>
          </div>

          {/* Technical depth on demand — the full authoritative chain. */}
          <span className="eyebrow">{t('provenance.technical')}</span>
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
