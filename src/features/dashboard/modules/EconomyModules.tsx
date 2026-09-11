import { Coin, Empty, rowProps } from '../../../ui'
import { fmtInt, useI18n } from '../../../i18n'
import type { EconomySummary, WalletSummary, DashboardNavigate } from '../dashboard.types'

export function EconomyModule({ data, onGo }: { data: EconomySummary; onGo: DashboardNavigate }) {
  const { t } = useI18n()
  return <>
    <dl className="kv"><dt>{t('wallet.coinsIssued')}</dt><dd><Coin n={data.issued}/></dd><dt>{t('wallet.coinsCirculating')}</dt><dd><Coin n={data.circulating}/></dd></dl>
    <p className="faint">{t('dashboard.issuedHint')}</p>
    <button className="btn" onClick={() => onGo('wallet')}>{t('common.wallet')}</button>
  </>
}
export function WalletModule({ data, onGo }: { data: WalletSummary; onGo: DashboardNavigate }) {
  const { t } = useI18n()
  return <>
    <div className="kpi2"><div className="l">{t('wallet.balance')}</div><div className="v"><Coin n={data.balance}/></div></div>
    <p>{t('overview.kpi.rewardsAffordable', { count: fmtInt(data.affordable.length) })}</p>
    {data.affordable.length === 0 && <Empty title={t('overview.nothingAffordable')}/>}
    {data.affordable.slice(0, 3).map(r => <div className="att-row dashboard-row" key={r.id} {...rowProps(() => onGo('rewards'))}><span dir="auto">{r.name}</span><Coin n={r.cost}/></div>)}
    <div className="dashboard-actions"><button className="btn" onClick={() => onGo('wallet')}>{t('common.wallet')}</button><button className="btn" onClick={() => onGo('rewards')}>{t('common.rewards')}</button></div>
  </>
}
