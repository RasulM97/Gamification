import type { Attachment, AssignMode, Audience, NotifLevel, Priority, Reward, RewardCategory, Settings } from './model'

export type Action =
  | { type: 'SET_TASK_ACCESS'; by: string; taskId: string; viewerIds: string[]; reviewerIds: string[] }
  | { type: 'UPDATE_USER'; by: string; userId: string; name: string; position: string; role: import('./model').Role; active: boolean }
  | { type: 'CLEAR_TEST_WORKSPACE'; by: string }
  | { type: 'UPDATE_CAPACITY'; by: string; userId: string; maxActiveTasks: number }
  | { type: 'CREATE_TASK'; by: string; title: string; description: string; priority: Priority; deadline: string | null; reward: number; audience: Audience; assignMode: AssignMode; assigneeId: string | null; attachments?: Attachment[] }
  | { type: 'CLAIM_TASK'; taskId: string; userId: string }
  | { type: 'DECLINE_ASSIGNMENT'; taskId: string; userId: string; reason: string }
  | { type: 'RETURN_CLAIM'; taskId: string; userId: string; reason: string }
  | { type: 'EDIT_TASK'; taskId: string; by: string; title?: string; description?: string; priority?: Priority; deadline?: string | null; reward?: number }
  | { type: 'REASSIGN'; audience?: Audience; sensitivityConfirmed?: boolean; taskId: string; by: string; assigneeId: string | null }
  | { type: 'REPORT_PROGRESS'; taskId: string; userId: string; pct: number }
  | { type: 'SUBMIT_WORK'; taskId: string; userId: string; note: string; attachments: Attachment[]; pct?: number }
  | { type: 'RESUME_WORK'; taskId: string; userId: string }
  | { type: 'APPROVE'; taskId: string; managerId: string }
  | { type: 'REJECT'; taskId: string; managerId: string; reason: string }
  | { type: 'HANDOFF'; sensitivityConfirmed?: boolean; taskId: string; managerId: string; acceptedPct: number; reason: string; next: { kind: 'EMPLOYEE'; id: string } | { kind: 'AVAILABLE' }; audience?: Audience; priority?: Priority; deadline?: string | null; remainingReward?: number; overrideReason?: string; attachments?: Attachment[] }
  /* M1-D D7: reopen/reactivate start a NEW cycle with NEW routing — the
     previous cycle's worker type never constrains the new cycle. audience
     re-decides who the work is for; assigneeId routes one-to-one. */
  | { type: 'REOPEN'; sensitivityConfirmed?: boolean; taskId: string; by: string; description?: string; attachments?: Attachment[]; audience?: Audience; assigneeId?: string | null }
  | { type: 'CANCEL_TASK'; taskId: string; by: string; reason: string; acceptedPct?: number }
  | { type: 'REACTIVATE'; sensitivityConfirmed?: boolean; taskId: string; by: string; reason: string; description?: string; attachments?: Attachment[]; audience?: Audience; assigneeId?: string | null }
  | { type: 'REDEEM'; userId: string; rewardId: string }
  /* N2.2 §5: approval and fulfillment are separate transitions — approval
     follows the N2.1-R2 decision matrix; fulfillment is executor work on an
     already-APPROVED redemption and carries optional tracking details. */
  | { type: 'APPROVE_REDEMPTION'; id: string; by: string }
  | { type: 'FULFILL_REDEMPTION'; id: string; by: string; reference?: string; note?: string }
  | { type: 'CANCEL_REDEMPTION'; id: string; by: string; reason: string }
  | { type: 'SAVE_REWARD_CATEGORY'; by: string; category: RewardCategory }
  | { type: 'TOGGLE_FULFILL_PERMISSION'; by: string; userId: string }
  | { type: 'ADMIN_ADJUST'; by: string; userId: string; amount: number; reason: string }
  | { type: 'SAVE_REWARD'; by: string; reward: Reward }
  | { type: 'MARK_READ'; id: string }
  | { type: 'MARK_ALL_READ'; userId: string }
  | { type: 'ARCHIVE_NOTICE'; id: string }
  | { type: 'ARCHIVE_ALL_READ'; userId: string }
  | { type: 'TOGGLE_NOTIF_MUTE'; userId: string; level: NotifLevel }
  | { type: 'UPDATE_SETTINGS'; by: string; settings: Settings }
