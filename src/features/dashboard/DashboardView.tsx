import { useEffect, useMemo, useState } from 'react'
import { useMe, useStore } from '../../store'
import { useI18n } from '../../i18n'
import { Panel } from '../../ui'
import { WelcomeCard } from './WelcomeCard'
import { buildDashboardModel } from './dashboard.selectors'
import { dashboardModules } from './dashboard.registry'
import type { DashboardModuleDefinition, DashboardModuleProps, DashboardNavigate } from './dashboard.types'

export function DashboardLayout({ model, onGo, modules = dashboardModules }: DashboardModuleProps & {
  modules?: readonly DashboardModuleDefinition[]
}) {
  const { t } = useI18n()
  return <div className="dashboard-grid">
    {modules.filter(m => m.roles.includes(model.role) && (!m.visible || m.visible(model)))
      .sort((a, b) => a.order - b.order).map(({ id, titleKey, component: Component }) =>
        <section className="dashboard-module" data-dashboard-module={id} key={id}>
          <Panel title={t(titleKey)}><Component model={model} onGo={onGo}/></Panel>
        </section>)}
  </div>
}

export function DashboardView({ onGo }: { onGo: DashboardNavigate }) {
  const { state } = useStore(), me = useMe()
  const [now, setNow] = useState(Date.now)
  // Reward availability windows refresh even when the domain state is idle.
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 60_000); return () => clearInterval(timer) }, [])
  const model = useMemo(() => buildDashboardModel(state, me, now), [state, me, now])
  return <div className="wrap dashboard-wrap"><WelcomeCard key={me.id}/><DashboardLayout model={model} onGo={onGo}/></div>
}
