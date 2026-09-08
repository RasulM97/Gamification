# Placeholder Runtime Audit — v1.1

All interpolation identifiers in `en.json` were audited against the current `main` branch. The localization files use placeholders only where the existing UI already interpolates a dynamic runtime value. Placeholder names remain unchanged in every locale.

| Placeholder | Current repository evidence | Runtime value represented |
|---|---|---|
| `{{assignee}}` | `src/components/CreateTask.tsx; src/components/TaskDrawer.tsx` | assigneeUser?.name / assigned user name |
| `{{coins}}` | `src/views/Reviews.tsx; src/views/Rewards.tsx` | computed payout / shortage amount |
| `{{count}}` | `src/ui.tsx; src/App.tsx; src/views/Notifications.tsx; src/views/Reviews.tsx; src/views/Rewards.tsx` | relative-time units, unread/waiting counts, stock count |
| `{{fileName}}` | `src/ui.tsx; src/domain/model.ts` | f.name / attachment file name in open + validation messages |
| `{{maxActive}}` | `src/components/TaskDrawer.tsx; src/views/Tasks.tsx` | MAX_ACTIVE |
| `{{maxFileSizeMb}}` | `src/components/CreateTask.tsx; src/components/TaskModals.tsx; src/domain/model.ts` | state.settings.maxFileSizeMb |
| `{{maxSubmissionTotalMb}}` | `src/components/TaskModals.tsx; src/domain/model.ts` | state.settings.maxSubmissionTotalMb |
| `{{name}}` | `src/components/HandoffWizard.tsx; src/views/Notifications.tsx` | owner?.name / ownerName |
| `{{pool}}` | `src/components/HandoffWizard.tsx` | poolLabel derived from audience |
| `{{query}}` | `src/components/HandoffWizard.tsx` | pick search text used in “Nobody matches …” |

**Result:** PASS

No pseudo-placeholders were found. Static statuses, roles, actions, priorities, audiences, and other system terms remain ordinary localization keys and are not represented as fake interpolation variables.
