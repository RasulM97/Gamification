import { currentLocale, intlLocaleOf, tActive } from '../../i18n'
export const operationKeys: Record<string, string> = {
  CREATE_TASK: 'task.action.create', CLAIM_TASK: 'task.action.claim', ACCEPT_ASSIGNMENT: 'task.action.acceptStart',
  DECLINE_ASSIGNMENT: 'task.action.decline', RETURN_CLAIM: 'task.action.returnMarketplace',
  EDIT_TASK: 'task.action.edit', REASSIGN: 'task.field.ownership', REPORT_PROGRESS: 'task.field.reportedProgress',
  SUBMIT_WORK: 'task.action.submit', RESUME_WORK: 'task.action.resumeRework', APPROVE: 'redemption.action.approve',
  REJECT: 'task.status.rejected', HANDOFF: 'task.action.handoff', REOPEN: 'task.action.reopen',
  CANCEL_TASK: 'task.action.cancel', REACTIVATE: 'task.action.reactivate', REDEEM: 'reward.action.redeem',
  APPROVE_REDEMPTION: 'redemption.action.approve', FULFILL_REDEMPTION: 'redemption.action.fulfill',
  CANCEL_REDEMPTION: 'redemption.action.cancelRefund', ADMIN_ADJUST: 'admin.adjustmentTitle',
  SAVE_REWARD: 'common.rewards', SAVE_REWARD_CATEGORY: 'reward.action.categories',
  UPDATE_CAPACITY: 'dashboard.manageCapacity', TOGGLE_FULFILL_PERMISSION: 'common.fulfillment',
  MARK_READ: 'common.notifications', MARK_ALL_READ: 'common.notifications', ARCHIVE_NOTICE: 'common.notifications',
  ARCHIVE_ALL_READ: 'common.notifications', TOGGLE_NOTIF_MUTE: 'common.notifications', UPDATE_SETTINGS: 'admin.uploadPolicy',
}
export const operationLabel = (code: string) => tActive(operationKeys[code] ?? 'testLab.operations')
export const timeLabel = (ts: number) => new Intl.DateTimeFormat(intlLocaleOf(currentLocale()), { dateStyle: 'short', timeStyle: 'short' }).format(ts)
