/* WS3 Team/Company Flow — manager/admin only. Emphasis: interventions,
 * blockers, waiting decisions, unresolved coordination. This is NOT an
 * employee-monitoring screen: incentive flow is aggregate business state
 * counts only (issued/pending/held/rejected/safeguarded over a fixed
 * window), never per-person breakdowns. The backend enforces scope
 * authority; this view only presents and navigates. */
import { useMe } from '../../store'
import { Empty, Panel } from '../../ui'
import { useI18n, fmtInt } from '../../i18n'
import { useGovData } from '../governance/hooks'
import { governance } from '../governance/source'
import { attention } from './source'
import { ItemRow } from './MyAttentionView'
import type { AttentionItem } from './types'

function ItemList({ items, scopeName, onNavigate, emptyKey }: {
  items: AttentionItem[]
  scopeName: (item: AttentionItem) => string | null
  onNavigate: (view: string) => void
  emptyKey: string
}) {
  const { t } = useI18n()
  if (items.length === 0) return <Empty title={t(emptyKey)} />
  return <>{items.map(item => <div key={item.id} style={{ display: 'flex', alignItems: 'center' }}>
    <div style={{ flex: 1, minWidth: 0 }}>
      <ItemRow item={item} onOpen={() => onNavigate(item.nav.view)} />
    </div>
    {scopeName(item) && <span className="badge" style={{ marginRight: 12 }} dir="auto">{scopeName(item)}</span>}
  </div>)}</>
}

export function FlowView({ onNavigate }: { onNavigate: (view: string) => void }) {
  const me = useMe(), { t } = useI18n()
  const { data, loading, error, reload } = useGovData(
    () => attention.teamFlow({ id: me.id, role: me.role }), [me.id, me.role])
  const units = useGovData(() => governance.listOrgUnits(), [])
  const scopeName = (item: AttentionItem) => item.scope
    ? units.data?.find(u => u.kind === item.scope?.kind && u.id === item.scope?.id)?.name ?? null
    : null
  const stats = data?.incentiveFlow
  return <div className="wrap" data-testid="team-flow">
    {loading && <p role="status" style={{ padding: 16 }}>{t('common.loading')}</p>}
    {error && <p role="alert" style={{ padding: 16 }}>{t('incentives.error')}{' '}
      <button className="btn" onClick={reload}>{t('incentives.retry')}</button></p>}
    {data && <>
      <Panel pad={false} title={t('flow.waitingDecisions')}
             right={<span data-testid="flow-decisions-count">{fmtInt(data.waitingDecisions.length)}</span>}>
        <ItemList items={data.waitingDecisions} scopeName={scopeName} onNavigate={onNavigate}
                  emptyKey="flow.noDecisions" />
      </Panel>
      <Panel pad={false} title={t('flow.unresolvedHelp')}
             right={<span data-testid="flow-help-count">{fmtInt(data.unresolvedHelp.length)}</span>}>
        <ItemList items={data.unresolvedHelp} scopeName={scopeName} onNavigate={onNavigate}
                  emptyKey="flow.noHelp" />
      </Panel>
      {stats && <Panel title={t('flow.incentiveFlow')}>
        <p className="dim" style={{ marginTop: 0 }}>{t('flow.windowDays', { days: stats.windowDays })}</p>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }} data-testid="flow-incentive-stats">
          {(['issued', 'pending', 'held', 'rejected', 'safeguarded'] as const).map(key =>
            <span key={key} className="badge" data-testid={`flow-stat-${key}`}>
              {t('flow.stat.' + key)} · {fmtInt(stats[key])}</span>)}
        </div>
      </Panel>}
      <Panel pad={false} title={t('flow.resolvedRecently')}>
        <ItemList items={data.resolvedRecently} scopeName={scopeName} onNavigate={onNavigate}
                  emptyKey="flow.noResolved" />
      </Panel>
    </>}
  </div>
}
