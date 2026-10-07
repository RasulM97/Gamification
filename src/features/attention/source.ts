/* WS3 attention data source — the single normalization point between the
 * attention views and their data, mirroring the governance feature pattern.
 *
 * SERVER MODE: thin wrappers over /api/attention/*; the backend stays
 * authoritative for category, state, and nextAction.
 * DEMO MODE: deterministic composition over the shared Aster Dynamics
 * fixtures (via the governance source's public reads, so demo mutations stay
 * consistent). Demo scope/audience resolution approximates the server's
 * organization authority — presentation fixtures only, never an engine.
 */
import { api } from '../../api'
import { IS_DEMO } from '../../runtime'
import { governance } from '../governance/source'
import type { HelpItem, OrgUnit } from '../governance/types'
import type { AttentionActor, AttentionFlow, AttentionItem, AttentionSource, IncentiveFlow } from './types'

const DAY = 86_400_000
const RESOLVED_WINDOW = 7 * DAY
const FLOW_WINDOW = 30 * DAY

/* ── server implementation ─────────────────────────────────────────────── */

const server: AttentionSource = {
  myAttention: async () => (await api.get<{ items: AttentionItem[] }>('/attention/me')).items,
  teamFlow: () => api.get<AttentionFlow>('/attention/flow'),
}

/* ── demo implementation: deterministic fixtures, local-only ────────────── */

const scopeOf = (row: HelpItem) => row.scope ?? { kind: 'COMPANY' as const }

/** Demo approximation of organization authority: admins see everything;
 *  managers see company scope plus units they manage. */
const manages = (units: OrgUnit[], me: AttentionActor, scope: { kind: string; id?: string }) =>
  me.role === 'ADMIN' || scope.kind === 'COMPANY' ||
  units.some(u => u.kind === scope.kind && u.id === scope.id &&
    u.memberships.some(m => m.userId === me.id && m.manager && !m.leftAt))

function helpItem(row: HelpItem, category: AttentionItem['category'], kind: string,
                  state: string, occurredAt: number, nextAction: string | null): AttentionItem {
  const scope = scopeOf(row)
  return {
    id: `${kind}.${row.id}`, category, kind, title: row.title, state, occurredAt,
    nextAction, nav: { view: 'people' },
    ...(scope.kind !== 'COMPANY' ? { scope: scope as AttentionItem['scope'] } : {}),
  }
}

async function demoMyAttention(me: AttentionActor): Promise<AttentionItem[]> {
  const now = Date.now()
  const [help, thanks, recognition, units, outcomes] = await Promise.all([
    governance.listHelp(), governance.listAppreciation('thanks'), governance.listAppreciation('recognition'),
    governance.listOrgUnits(), governance.myIncentives(me.id),
  ])
  const items: AttentionItem[] = []
  for (const row of help) {
    const mine = row.requesterUserId === me.id
    const helping = row.acceptedByUserId === me.id
    /* Demo routing approximation, mirroring WS1 audiences: company scope
       reaches admins; team/project scope reaches members; escalations reach
       the scope's managers (admins at company level). The requester is never
       a recipient. Presentation fixtures only — the server stays
       authoritative in server mode. */
    const scope = row.scope
    const unit = scope ? units.find(u => u.kind === scope.kind && u.id === scope.id) : undefined
    const membership = unit?.memberships.find(m => m.userId === me.id && !m.leftAt)
    const escalated = row.routingStatus === 'ESCALATED'
    const routed = !mine && row.status === 'OPEN' && (scope
      ? (escalated ? (me.role === 'ADMIN' || !!membership?.manager) : !!membership)
      : me.role === 'ADMIN')
    if (mine && row.status === 'FINISHED')
      items.push(helpItem(row, 'ACTION_REQUIRED', 'help.confirm', 'FINISHED', row.finishedAt ?? now, 'confirm'))
    else if (mine && (row.status === 'OPEN' || row.status === 'ACCEPTED'))
      items.push(helpItem(row, 'WAITING', 'help.waiting', row.status === 'OPEN' ? row.routingStatus ?? 'ROUTED' : 'ACCEPTED',
        row.escalatedAt ?? row.acceptedAt ?? row.createdAt, null))
    else if (mine && row.status === 'CONFIRMED' && (row.confirmedAt ?? 0) >= now - RESOLVED_WINDOW)
      items.push(helpItem(row, 'RESOLVED_RECENTLY', 'help.resolved', 'CONFIRMED', row.confirmedAt ?? now, null))
    else if (helping && row.status === 'ACCEPTED')
      items.push(helpItem(row, 'ACTION_REQUIRED', 'help.finish', 'ACCEPTED', row.acceptedAt ?? now, 'finish'))
    else if (helping && row.status === 'FINISHED')
      items.push(helpItem(row, 'WAITING', 'help.awaitingConfirm', 'FINISHED', row.finishedAt ?? now, null))
    else if (helping && row.status === 'CONFIRMED' && (row.confirmedAt ?? 0) >= now - RESOLVED_WINDOW)
      items.push(helpItem(row, 'RESOLVED_RECENTLY', 'help.resolved', 'CONFIRMED', row.confirmedAt ?? now, null))
    else if (routed)
      items.push(helpItem(row, 'ACTION_REQUIRED', 'help.accept', row.routingStatus ?? 'ROUTED',
        row.escalatedAt ?? row.routedAt ?? row.createdAt, 'accept'))
  }
  const appreciation = [
    ...thanks.map(row => ({ row, kind: 'appreciation.thanks' })),
    ...recognition.map(row => ({ row, kind: 'appreciation.recognition' })),
  ]
  for (const { row, kind } of appreciation) {
    if (row.recipientUserId === me.id && row.createdAt >= now - RESOLVED_WINDOW)
      items.push({
        id: `${kind}.${row.id}`, category: 'INFORMATION', kind, title: row.message, state: 'RECEIVED',
        occurredAt: row.createdAt, nextAction: null, nav: { view: 'people' },
        ...(row.scope ? { scope: row.scope } : {}),
      })
  }
  let sequence = 0
  for (const row of outcomes.items) {
    if (row.ledgerTransactionId !== null) continue  // payout history stays in the Wallet
    sequence += 1
    const id = `incentive.${row.status}.${row.createdAt}.${sequence}`
    if (row.status === 'PENDING_REVIEW' || row.status === 'AUTHORIZED_PENDING')
      items.push({ id, category: 'WAITING', kind: 'incentive.waiting', title: row.ruleName, state: row.status,
        occurredAt: row.createdAt, nextAction: null, nav: { view: 'wallet' } })
    else if ((row.status === 'NOT_APPROVED' || row.status === 'NOT_AUTHORIZED' || row.status === 'SAFEGUARDED')
             && row.createdAt >= now - FLOW_WINDOW)
      items.push({ id, category: 'RESOLVED_RECENTLY', kind: 'incentive.outcome', title: row.ruleName,
        state: row.status, occurredAt: row.createdAt, nextAction: null, nav: { view: 'wallet' } })
  }
  if (me.role === 'MANAGER' || me.role === 'ADMIN')
    items.push(...(await demoPendingDecisions(me)).items)
  return items
}

async function demoPendingDecisions(me: AttentionActor) {
  const pending = (await governance.listApprovals('PENDING')).items
    .filter(a => me.role === 'ADMIN' || a.requiredAuthority === 'MANAGER_OR_ADMIN')
  return {
    items: pending.map(a => ({
      id: `approval.decide.${a.id}`, category: 'ACTION_REQUIRED' as const, kind: 'approval.decide',
      title: null, state: a.requiredAuthority, occurredAt: a.requestedAt, nextAction: 'decide',
      nav: { view: 'incentives' },
    })),
    pending,
  }
}

function demoFlowCounts(me: AttentionActor, units: OrgUnit[],
                        pending: { safetyEvaluationId?: string | null }[],
                        effects: { status: string; createdAt: number; candidateId: string }[],
                        candidates: { id: string; ruleId: string }[],
                        rules: { id: string; scope?: { kind: 'TEAM' | 'PROJECT'; id: string } }[],
                        safety: { outcome: string; createdAt: number; candidateId: string }[],
                        rejectedCount: number): IncentiveFlow {
  const now = Date.now()
  /* Demo scope approximation: an incentive's scope is its rule's scope;
     managers see company scope plus units they manage. */
  const candidateScope = (candidateId: string) => {
    const candidate = candidates.find(c => c.id === candidateId)
    return rules.find(r => r.id === candidate?.ruleId)?.scope ?? { kind: 'COMPANY' as const }
  }
  const visible = (candidateId: string) => manages(units, me, candidateScope(candidateId))
  const issued = effects.filter(e =>
    e.status === 'ISSUED' && e.createdAt >= now - FLOW_WINDOW && visible(e.candidateId)).length
  /* CURRENT safeguarded mirrors the server's SafetyHead read: only the
     latest evaluation per candidate decides; superseded rows never count. */
  const headByCandidate = new Map<string, { outcome: string; createdAt: number }>()
  for (const row of safety) {
    const prior = headByCandidate.get(row.candidateId)
    if (!prior || row.createdAt >= prior.createdAt) headByCandidate.set(row.candidateId, row)
  }
  const safeguarded = [...headByCandidate.entries()]
    .filter(([candidateId, row]) => row.outcome === 'SUPPRESS_INCENTIVE' && visible(candidateId)).length
  return {
    current: { pending: pending.length, held: pending.filter(a => a.safetyEvaluationId).length, safeguarded },
    recent: { issued, rejected: rejectedCount, windowDays: 30 },
  }
}

async function demoTeamFlow(me: AttentionActor): Promise<AttentionFlow> {
  /* Same role boundary as the server: Team Flow is manager/admin only. */
  if (me.role !== 'MANAGER' && me.role !== 'ADMIN') throw new Error('Approval management authority required')
  const now = Date.now()
  const [help, rejected, units, effectsPage, safetyPage, rulesPage, candidatesPage] = await Promise.all([
    governance.listHelp(), governance.listApprovals('REJECTED'), governance.listOrgUnits(),
    governance.listEffects(), governance.listSafetyEvaluations(), governance.listRules(),
    governance.listCandidates(),
  ])
  const { items: waitingDecisions, pending } = await demoPendingDecisions(me)
  const unresolvedHelp: AttentionItem[] = []
  const resolvedRecently: AttentionItem[] = []
  for (const row of help) {
    const scope = scopeOf(row)
    if (!manages(units, me, scope)) continue
    if (row.status === 'OPEN') {
      const intervenable = row.routingStatus === 'UNRESOLVED' || row.routingStatus === 'ESCALATED'
      unresolvedHelp.push(helpItem(row, intervenable ? 'ACTION_REQUIRED' : 'WAITING',
        `help.${(row.routingStatus ?? 'ROUTED').toLowerCase()}`, row.routingStatus ?? 'ROUTED',
        row.escalatedAt ?? row.createdAt, intervenable ? 'review' : null))
    } else if (row.status === 'ACCEPTED') {
      unresolvedHelp.push(helpItem(row, 'WAITING', 'help.inProgress', 'ACCEPTED', row.acceptedAt ?? now, null))
    } else if (row.status === 'CONFIRMED' && (row.confirmedAt ?? 0) >= now - RESOLVED_WINDOW) {
      resolvedRecently.push(helpItem(row, 'RESOLVED_RECENTLY', 'help.resolved', 'CONFIRMED', row.confirmedAt ?? now, null))
    }
  }
  const rejectedCount = rejected.items.filter(a =>
    (a.finalDecision?.decidedAt ?? 0) >= now - FLOW_WINDOW &&
    (me.role === 'ADMIN' || a.requiredAuthority === 'MANAGER_OR_ADMIN')).length
  const incentiveFlow = demoFlowCounts(me, units, pending, effectsPage.items, candidatesPage.items,
    rulesPage.items, safetyPage.items, rejectedCount)
  return { waitingDecisions, unresolvedHelp, incentiveFlow, resolvedRecently }
}

const demo: AttentionSource = {
  myAttention: demoMyAttention,
  teamFlow: demoTeamFlow,
}

/* Static build-time mode: one branch is dead-code-eliminated per build. */
export const attention: AttentionSource = IS_DEMO ? demo : server
