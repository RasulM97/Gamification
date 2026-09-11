import { useState } from 'react'
import { CapacityControl } from '../../../components/CapacityControl'
import { fmtInt, useI18n } from '../../../i18n'
import { Empty, roleKey } from '../../../ui'
import type { CapacitySummary, DashboardNavigate } from '../dashboard.types'

export function CapacityModule({ data, onGo }: { data: CapacitySummary; onGo: DashboardNavigate }) {
  const { t } = useI18n()
  const [manage, setManage] = useState(false)
  return <>
    <dl className="kv"><dt>{t('capacity.full')}</dt><dd>{fmtInt(data.at)}</dd><dt>{t('dashboard.nearCapacity')}</dt><dd>{fmtInt(data.near)}</dd></dl>
    <p className="faint">{t('dashboard.nearHint')}</p>
    {data.at === 0 && <Empty title={t('dashboard.noCapacity')} />}
    {(manage ? data.people : data.people.slice(0, 5)).map(p => <div className="dashboard-person" key={p.user.id}>
      <div><b dir="auto">{p.user.name}</b><small>{t(roleKey(p.user.role))}</small></div>
      {manage ? <CapacityControl user={p.user} /> : <span className={p.at ? 'warn' : ''}><bdi dir="ltr">{fmtInt(p.active)} / {fmtInt(p.limit)}</bdi></span>}
    </div>)}
    <button className="btn" aria-expanded={data.admin ? undefined : manage}
      onClick={() => data.admin ? onGo('admin') : setManage(!manage)}>{t('dashboard.manageCapacity')}</button>
  </>
}
