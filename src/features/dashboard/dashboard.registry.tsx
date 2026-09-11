import type { DashboardModuleDefinition } from './dashboard.types'
import { ActiveWorkModule, AvailableWorkModule } from './modules/WorkModules'
import { AttentionModule, ReviewQueueModule, RedemptionModule } from './modules/QueueModules'
import { CapacityModule } from './modules/CapacityModule'
import { EconomyModule, WalletModule } from './modules/EconomyModules'
import { RecentActivityModule, TaskStatusModule } from './modules/HistoryModules'

const management = ['ADMIN', 'MANAGER'] as const
const workers = ['MANAGER', 'EMPLOYEE'] as const
const everyone = ['ADMIN', 'MANAGER', 'EMPLOYEE'] as const

/** Static composition only. Selectors own derivation; modules own presentation. */
export const dashboardModules: readonly DashboardModuleDefinition[] = [
  { id: 'attention', roles: everyone, titleKey: 'overview.attentionTitle', order: 10,
    component: ({ model, onGo }) => <AttentionModule data={model.attention} onGo={onGo}/> },
  { id: 'reviews', roles: management, titleKey: 'overview.kpi.reviewsWaiting', order: 20,
    component: ({ model, onGo }) => <ReviewQueueModule tasks={model.reviews!} onGo={onGo}/> },
  { id: 'personal-work', roles: workers, titleKey: 'overview.myActiveWork', order: 30,
    component: ({ model, onGo }) => <ActiveWorkModule data={model.personal!} onGo={onGo} personal/> },
  { id: 'active-work', roles: management, titleKey: 'overview.kpi.activeTasks', order: 40,
    component: ({ model, onGo }) => <ActiveWorkModule data={model.activeWork!} onGo={onGo}/> },
  { id: 'capacity', roles: management, titleKey: 'capacity.label', order: 50,
    component: ({ model, onGo }) => <CapacityModule data={model.capacity!} onGo={onGo}/> },
  { id: 'redemptions', roles: everyone, titleKey: 'common.redemptions', order: 60,
    component: ({ model, onGo }) => <RedemptionModule data={model.redemptions} onGo={onGo}/> },
  { id: 'economy', roles: management, titleKey: 'overview.portfolio', order: 70,
    component: ({ model, onGo }) => <EconomyModule data={model.economy!} onGo={onGo}/> },
  { id: 'wallet', roles: workers, titleKey: 'common.wallet', order: 80,
    component: ({ model, onGo }) => <WalletModule data={model.wallet!} onGo={onGo}/> },
  { id: 'available-work', roles: workers, titleKey: 'nav.availableWork', order: 90,
    component: ({ model, onGo }) => <AvailableWorkModule data={model.available!} onGo={onGo}/> },
  { id: 'task-status', roles: management, titleKey: 'overview.chart.status', order: 100,
    component: ({ model, onGo }) => <TaskStatusModule rows={model.statusMix!} onGo={onGo}/> },
  { id: 'recent-activity', roles: management, titleKey: 'common.activity', order: 110,
    component: ({ model, onGo }) => <RecentActivityModule rows={model.activity!} onGo={onGo}/> },
]
