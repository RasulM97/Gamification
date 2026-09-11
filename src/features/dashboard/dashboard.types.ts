import type { ComponentType } from 'react'
import type { Act, Role, Task, TaskStatus, User, Reward } from '../../domain/engine'

export type DashboardNavigate = (view: string, taskId?: string) => void
export interface WorkSummary { active: number; inReview: number; tasks: Task[] }
export interface PersonalWork extends WorkSummary { limit: number; manager: boolean }
export interface AttentionSummary { rework: Task[]; assignments: Task[]; total: number; personal: boolean }
export interface CapacityPerson { user: User; active: number; limit: number; at: boolean; near: boolean }
export interface CapacitySummary { people: CapacityPerson[]; at: number; near: number; admin: boolean }
export interface RedemptionSummary { pending: number; ready: number; ownPending: number; ownReady: number; management: boolean }
export interface EconomySummary { issued: number; circulating: number }
export interface WalletSummary { balance: number; affordable: Reward[] }
export interface AvailableSummary { visible: number; claimable: number; active: number; limit: number }
export interface ActivityRow { event: Act; actor: string }
export interface DashboardModel {
  role: Role
  personal?: PersonalWork
  attention: AttentionSummary
  reviews?: Task[]
  activeWork?: WorkSummary
  capacity?: CapacitySummary
  redemptions: RedemptionSummary
  economy?: EconomySummary
  wallet?: WalletSummary
  available?: AvailableSummary
  activity?: ActivityRow[]
  statusMix?: { status: TaskStatus; count: number }[]
}
export interface DashboardModuleProps { model: DashboardModel; onGo: DashboardNavigate }
export interface DashboardModuleDefinition {
  id: string
  roles: readonly Role[]
  titleKey: string
  order: number
  visible?: (model: DashboardModel) => boolean
  component: ComponentType<DashboardModuleProps>
}
