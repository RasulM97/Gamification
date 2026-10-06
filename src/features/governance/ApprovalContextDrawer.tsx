/* WS2-A manager provenance — business-language context for an approval the
 * caller is authorized to decide: what happened, who is affected, why their
 * decision is required, the evidence, and the consequence of approve/reject.
 * No engine architecture required. Data comes from the authority-checked
 * /provenance/approvals/:id projection (same gate as deciding). */
import { useStore } from '../../store'
import { useI18n } from '../../i18n'
import { Coin, Drawer, ago, roleKey } from '../../ui'
import { governance } from './source'
import { useGovData } from './hooks'
import { EventPhrase } from './ProvenanceText'

export function ApprovalContextDrawer({ approvalId, onClose }: { approvalId: string | null; onClose: () => void }) {
  const { state } = useStore()
  const { t } = useI18n()
  const { data, loading, error, reload } = useGovData(
    () => approvalId ? governance.getApprovalContext(approvalId) : Promise.resolve(null), [approvalId])
  const units = useGovData(() => approvalId ? governance.listOrgUnits() : Promise.resolve([]), [approvalId])
  const name = (id: string | null | undefined) =>
    id ? (state.users.find(u => u.id === id)?.name ?? id) : '—'
  const ctx = data?.context
  const unitName = (scope: { kind: string; id: string } | null) =>
    scope ? (units.data?.find(u => u.id === scope.id)?.name ?? null) : null

  return (
    <Drawer open={!!approvalId} onClose={onClose} title={t('provenance.context.title')}>
      {loading && <p role="status">{t('common.loading')}</p>}
      {error && <p role="alert">{t('incentives.error')} <button className="btn" onClick={reload}>{t('incentives.retry')}</button></p>}
      {data && ctx && (
        <>
          {ctx.proposedReward !== null && (
            <div className="dsec" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Coin n={ctx.proposedReward} />
              <span className="dim" style={{ fontSize: 12.5 }}>
                {t('incentives.chain.proposedFor', { name: name(ctx.subjectId) })}</span>
            </div>
          )}
          <div className="dsec">
            <span className="eyebrow">{t('provenance.what')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }}>
              <EventPhrase type={ctx.eventType} />
              {ctx.occurredAt && <span className="dim"> · {ago(ctx.occurredAt)}</span>}
              {ctx.subjectId && <div className="dim" style={{ marginTop: 4 }}>{name(ctx.subjectId)}</div>}
            </div>
          </div>
          <div className="dsec">
            <span className="eyebrow">{t('provenance.whyNeeded')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }}>
              {t('provenance.whyNeeded.' + ctx.trigger)}
              <div className="dim" style={{ marginTop: 4 }}>
                {t('incentives.authority.' + ctx.requiredAuthority)} · {t('provenance.yourAuthority', { role: t(roleKey(ctx.myAuthority)) })}
              </div>
            </div>
          </div>
          <div className="dsec">
            <span className="eyebrow">{t('provenance.evidence')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }}>
              {ctx.ruleName && <b dir="auto">{ctx.ruleName}</b>}
              {ctx.ruleDescription && <div className="dim" dir="auto" style={{ marginTop: 2 }}>{ctx.ruleDescription}</div>}
              {ctx.policyExplanation && <div className="dim" dir="auto" style={{ marginTop: 4 }}>{ctx.policyExplanation}</div>}
              {ctx.safetyOutcome && <div style={{ marginTop: 4 }}>{t('provenance.safety.' + ctx.safetyOutcome)}</div>}
              {ctx.scope && unitName(ctx.scope) &&
                <div className="dim" style={{ marginTop: 4 }}>{t('organization.' + ctx.scope.kind)}: <span dir="auto">{unitName(ctx.scope)}</span></div>}
            </div>
          </div>
          <div className="dsec">
            <span className="eyebrow">{t('provenance.consequence')}</span>
            <div style={{ marginTop: 6, fontSize: 13 }} className="dim">
              {ctx.effects.length > 0
                ? t('provenance.consequence.executed')
                : <>
                    {/* Truthful copy: approval authorizes; issuance is a
                        separate admin step. Never claim approval pays. */}
                    <div>{t('provenance.consequence.approve')}</div>
                    <div>{t('provenance.consequence.reject')}</div>
                  </>}
            </div>
          </div>
        </>
      )}
    </Drawer>
  )
}
