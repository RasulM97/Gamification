/* WS2-A employee provenance — "why did I get this?" for incentive wallet
 * entries and non-payout outcomes. Business language only: what happened,
 * why, the result, and what it means. Engine nouns (candidate/policy/safety
 * internals) never render. The caller resolves the item from the role-scoped
 * /provenance/me projection (server) or the deterministic demo fixtures. */
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { Coin, Drawer, ago } from '../../ui'
import { EventPhrase } from './ProvenanceText'
import type { IncentiveProvenanceItem, IncentiveStatus } from './types'

const BADGE: Record<IncentiveStatus, string> = {
  ISSUED: 'bd-normal',
  AUTHORIZED_PENDING: 'bd-normal',
  PENDING_REVIEW: 'bd-important',
  SAFEGUARDED: 'bd-important',
  NOT_APPROVED: 'bd-urgent',
  NOT_AUTHORIZED: 'bd-urgent',
  REVERSED: 'bd-urgent',
}

/* What this means next — one honest line per business status. */
const NEXT: Record<IncentiveStatus, string> = {
  ISSUED: 'provenance.next.issued',
  REVERSED: 'provenance.next.reversed',
  AUTHORIZED_PENDING: 'provenance.nextFor.AUTHORIZED_PENDING',
  PENDING_REVIEW: 'provenance.nextFor.PENDING_REVIEW',
  NOT_APPROVED: 'provenance.nextFor.NOT_APPROVED',
  NOT_AUTHORIZED: 'provenance.nextFor.NOT_AUTHORIZED',
  SAFEGUARDED: 'provenance.nextFor.SAFEGUARDED',
}

export function MyIncentiveDrawer({ item, open, loading, onClose }: {
  item: IncentiveProvenanceItem | null
  open?: boolean
  loading?: boolean
  onClose: () => void
}) {
  const { state } = useStore()
  const { t } = useI18n()
  const name = (id: string | null | undefined) =>
    id ? (state.users.find(u => u.id === id)?.name ?? id) : '—'

  return (
    <Drawer open={open ?? !!item} onClose={onClose} title={t('provenance.drawer.title')}>
      {loading && <p role="status">{t('common.loading')}</p>}
      {!loading && !item && <p className="dim">{t('provenance.noData')}</p>}
      {item && (
        <>
          <div className="dsec" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {item.amount !== null && <Coin n={Number(item.amount)} sign />}
            <span className={'bd ' + BADGE[item.status]}>
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
              {item.policyReason && <div className="dim" style={{ marginTop: 4 }}>{t('provenance.policyReason.' + item.policyReason)}</div>}
            </div>
          </div>
          <div className="dsec">
            <span className="eyebrow">{t('provenance.result')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }}>
              {item.status === 'NOT_APPROVED' && item.decidedBy &&
                <div>{t('provenance.notApprovedBy', { name: name(item.decidedBy) })} · {ago(item.decidedAt!)}</div>}
              {item.status !== 'NOT_APPROVED' && item.decidedBy &&
                <div>{t('provenance.approvedBy', { name: name(item.decidedBy) })} · {ago(item.decidedAt!)}</div>}
              {item.reversal
                ? <div>{t('provenance.reversedNote', { reason: t('provenance.reversalReason.' + item.reversal.reasonCode) })} · {ago(item.reversal.createdAt)}</div>
                : item.status === 'ISSUED' && !item.decidedBy && <div className="dim">{t('provenance.noApprovalNeeded')}</div>}
            </div>
          </div>
          <div className="dsec">
            <span className="eyebrow">{t('provenance.next')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }} className="dim">
              {t(NEXT[item.status])}
            </div>
          </div>
        </>
      )}
    </Drawer>
  )
}
