/* WS2-A employee provenance — "why did I get this?" for incentive wallet
 * entries. Business language only: what happened, why, the result, and what
 * it means. Engine nouns (candidate/policy/safety internals) never render.
 * Data comes from the role-scoped /provenance/me projection (server) or the
 * deterministic demo fixtures — matched to the wallet row by ledger id. */
import { useStore, useMe } from '../../store'
import { useI18n } from '../../i18n'
import { Coin, Drawer, ago } from '../../ui'
import { governance } from './source'
import { useGovData } from './hooks'
import { EventPhrase } from './ProvenanceText'
import type { LedgerEntry } from '../../domain/model'

export function MyIncentiveDrawer({ entry, onClose }: { entry: LedgerEntry | null; onClose: () => void }) {
  const { state } = useStore()
  const me = useMe()
  const { t } = useI18n()
  const { data, loading, error, reload } = useGovData(
    () => entry ? governance.myIncentives(me.id) : Promise.resolve(null), [entry?.id])
  const name = (id: string | null | undefined) =>
    id ? (state.users.find(u => u.id === id)?.name ?? id) : '—'
  const item = data?.items.find(i =>
    i.ledgerTransactionId === entry?.id || entry?.ref === 'economic-reversal:' + i.effectId) ?? null

  return (
    <Drawer open={!!entry} onClose={onClose} title={t('provenance.drawer.title')}>
      {loading && <p role="status">{t('common.loading')}</p>}
      {error && <p role="alert">{t('incentives.error')} <button className="btn" onClick={reload}>{t('incentives.retry')}</button></p>}
      {data && !item && <p className="dim">{t('provenance.noData')}</p>}
      {item && (
        <>
          <div className="dsec" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Coin n={Number(item.amount)} sign />
            <span className={'bd ' + (item.status === 'ISSUED' ? 'bd-normal' : 'bd-urgent')}>
              {t('provenance.status.' + item.status)}</span>
            <span className="dim" style={{ fontSize: 12 }}>{ago(item.createdAt)}</span>
          </div>
          <div className="dsec">
            <span className="eyebrow">{t('provenance.what')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }}>
              <EventPhrase type={item.eventType} />
              {item.occurredAt && <span className="dim"> · {ago(item.occurredAt)}</span>}
            </div>
          </div>
          <div className="dsec">
            <span className="eyebrow">{t('provenance.why')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }}>
              {item.ruleName && <b dir="auto">{item.ruleName}</b>}
              {item.policyExplanation && <div className="dim" dir="auto" style={{ marginTop: 4 }}>{item.policyExplanation}</div>}
            </div>
          </div>
          <div className="dsec">
            <span className="eyebrow">{t('provenance.result')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }}>
              {item.approval && <div>{t('provenance.approvedBy', { name: name(item.approval.decidedBy) })} · {ago(item.approval.decidedAt)}</div>}
              {item.reversal
                ? <div>{t('provenance.reversedNote', { reason: t('provenance.reversalReason.' + item.reversal.reasonCode) })} · {ago(item.reversal.createdAt)}</div>
                : item.approval === null && <div className="dim">{t('provenance.noApprovalNeeded')}</div>}
            </div>
          </div>
          <div className="dsec">
            <span className="eyebrow">{t('provenance.next')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }} className="dim">
              {t(item.reversal ? 'provenance.next.reversed' : 'provenance.next.issued')}
            </div>
          </div>
        </>
      )}
    </Drawer>
  )
}
