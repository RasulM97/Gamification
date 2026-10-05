/* Governance data source (Cohesion F1/F2/D1) — the single normalization
 * point between governance views and their data.
 *
 * SERVER MODE: thin wrappers over the real APIs; backend stays authoritative.
 * DEMO MODE: the deterministic Aster Dynamics fixture story (demoData.ts).
 * Demo mutations edit the local fixture copy only — they never touch a
 * Ledger, never call the network, and are reset with the demo workspace.
 *
 * Views consume Page<T> / item shapes only (B2 normalization lives here).
 */
import { api } from '../../api'
import { IS_DEMO } from '../../runtime'
import { demoGovernance, type DemoGovernance } from './demoData'
import type {
  AppreciationItem, ApprovalItem, CandidateItem, DecisionItem, EffectItem, EventItem,
  GithubAttributionItem, GithubIdentityItem, GithubSourceItem, GovernanceSource, HelpItem,
  OrgUnit, Page, PolicyItem, RuleItem, SafetyEvalItem, ShadowItem,
} from './types'

const page = <T>(items: T[], offset = 0, limit = 100): Page<T> => ({ items, offset, limit })

/* ── server implementation ─────────────────────────────────────────────── */

const server: GovernanceSource = {
  async listEvents(offset = 0) {
    const r = await api.get<{ events: EventItem[]; offset: number; limit: number }>(`/events?offset=${offset}`)
    return page(r.events, r.offset, r.limit)
  },
  getEvent: async id => { try { return await api.get<EventItem>(`/events/${id}`) } catch { return null } },
  async listRules(offset = 0) {
    const r = await api.get<{ rules: RuleItem[] }>(`/rules?offset=${offset}`)
    return page(r.rules, offset)
  },
  createRule: body => api.post<RuleItem>('/rules', body),
  setRuleActive: (id, active) => api.patch<RuleItem>(`/rules/${id}`, { active }),
  async listCandidates(eventId, offset = 0) {
    const q = `${eventId ? `eventId=${encodeURIComponent(eventId)}&` : ''}offset=${offset}`
    const r = await api.get<{ candidates: CandidateItem[]; offset: number; limit: number }>(`/rules/candidates?${q}`)
    return page(r.candidates, r.offset, r.limit)
  },
  getCandidate: async id => { try { return await api.get<CandidateItem>(`/rules/candidates/${id}`) } catch { return null } },
  async listPolicies(offset = 0) {
    const r = await api.get<{ policies: PolicyItem[] }>(`/policies?offset=${offset}`)
    return page(r.policies, offset)
  },
  async listDecisions(candidateId, offset = 0) {
    const q = `${candidateId ? `candidateId=${encodeURIComponent(candidateId)}&` : ''}offset=${offset}`
    const r = await api.get<{ decisions: DecisionItem[]; offset: number; limit: number }>(`/policies/decisions?${q}`)
    return page(r.decisions, r.offset, r.limit)
  },
  getDecision: async id => { try { return await api.get<DecisionItem>(`/policies/decisions/${id}`) } catch { return null } },
  async listApprovals(status = 'PENDING', offset = 0) {
    const r = await api.get<{ approvals: ApprovalItem[]; offset: number; limit: number }>(
      `/approvals?status=${encodeURIComponent(status)}&offset=${offset}`)
    return page(r.approvals, r.offset, r.limit)
  },
  decideApproval: (id, decision, reasonCode, note) =>
    api.post<ApprovalItem>(`/approvals/${id}/decision`, { decision, reasonCode, note: note ?? null }),
  async listSafetyEvaluations(offset = 0) {
    const r = await api.get<SafetyEvalItem[]>(`/incentive-safety/evaluations?offset=${offset}`)
    return page(r, offset)
  },
  getSafetyEvaluation: async id => {
    try { return await api.get<SafetyEvalItem>(`/incentive-safety/evaluations/${id}`) } catch { return null }
  },
  async listShadow(offset = 0) {
    const r = await api.get<{ evaluations: ShadowItem[] }>(`/shadow?offset=${offset}`)
    return page(r.evaluations, offset)
  },
  async listEffects(policyDecisionId, offset = 0) {
    const q = `${policyDecisionId ? `policyDecisionId=${encodeURIComponent(policyDecisionId)}&` : ''}offset=${offset}`
    const r = await api.get<{ effects: EffectItem[]; offset: number; limit: number }>(`/economic-effects?${q}`)
    return page(r.effects, r.offset, r.limit)
  },
  getEffect: async id => { try { return await api.get<EffectItem>(`/economic-effects/${id}`) } catch { return null } },
  async listGithubSources() {
    return (await api.get<{ sources: GithubSourceItem[] }>('/integrations/github')).sources
  },
  setGithubSourceStatus: (id, status) => api.patch<GithubSourceItem>(`/integrations/github/${id}`, { status }),
  async listGithubIdentities(sourceId) {
    return (await api.get<{ mappings: GithubIdentityItem[] }>(`/integrations/github/${sourceId}/identities`)).mappings
  },
  async mapGithubIdentity(sourceId, externalUserId, userId) {
    await api.put(`/integrations/github/${sourceId}/identities/${externalUserId}`, { userId })
  },
  async listGithubAttributions(sourceId) {
    return (await api.get<{ attributions: GithubAttributionItem[] }>(
      `/integrations/github/${sourceId}/project-attributions`)).attributions
  },
  async assignGithubResource(sourceId, kind, resourceId, projectId) {
    await api.put(`/integrations/github/${sourceId}/resources/${kind}/${resourceId}/project`, { projectId })
  },
  listAppreciation: kind => api.get<AppreciationItem[]>(`/collaboration/${kind}`),
  async giveThanks(recipientUserId, message) {
    await api.post('/collaboration/thanks', { recipientUserId, message, submissionId: crypto.randomUUID() })
  },
  async recognize(recipientUserId, message) {
    await api.post('/collaboration/recognition', { recipientUserId, message, submissionId: crypto.randomUUID() })
  },
  listHelp: () => api.get<HelpItem[]>('/collaboration/help'),
  async requestHelp(title, description) {
    await api.post('/collaboration/help', { title, description, submissionId: crypto.randomUUID() })
  },
  helpAction: (id, action) => api.post(`/collaboration/help/${id}/${action}`, {}),
  async listOrgUnits() {
    return (await api.get<{ units: OrgUnit[] }>('/organization')).units
  },
}

/* ── demo implementation: deterministic fixtures, local-only mutation ──── */

let demoData: DemoGovernance | null = null
const demo_state = (): DemoGovernance => (demoData ??= demoGovernance())

/** Test/demo reset hook — drops the local fixture copy (never any server). */
export function resetDemoGovernance(): void { demoData = null }

const demoSource: GovernanceSource = {
  listEvents: async offset => page(demo_state().events.slice(offset ?? 0, (offset ?? 0) + 100), offset),
  getEvent: async id => demo_state().events.find(e => e.id === id) ?? null,
  listRules: async offset => page(demo_state().rules.slice(offset ?? 0), offset),
  async createRule(body) {
    const s = demo_state()
    const item: RuleItem = {
      id: `rule-demo-${s.rules.length + 1}`, name: String(body.name ?? ''), description: String(body.description ?? ''),
      active: body.active ?? false, priority: body.priority ?? 0, eventType: String(body.eventType ?? ''),
      conditions: body.conditions ?? [], outcome: body.outcome ?? { kind: 'INCENTIVE', data: {} },
      version: 1, createdBy: 'u-dana', createdAt: Date.now(), updatedAt: Date.now(),
      ...(body.scope ? { scope: body.scope } : {}),
    }
    s.rules = [item, ...s.rules]
    return item
  },
  async setRuleActive(id, active) {
    const rule = demo_state().rules.find(r => r.id === id)
    if (rule) { rule.active = active; rule.updatedAt = Date.now(); rule.version += 1 }
    return rule as RuleItem
  },
  listCandidates: async (eventId, offset = 0) => {
    const rows = demo_state().candidates.filter(c => !eventId || c.canonicalEventId === eventId)
    return page(rows.slice(offset, offset + 100), offset)
  },
  getCandidate: async id => demo_state().candidates.find(c => c.id === id) ?? null,
  listPolicies: async offset => page(demo_state().policies.slice(offset ?? 0), offset),
  listDecisions: async (candidateId, offset = 0) => {
    const rows = demo_state().decisions.filter(d => !candidateId || d.candidateId === candidateId)
    return page(rows.slice(offset, offset + 100), offset)
  },
  getDecision: async id => demo_state().decisions.find(d => d.decisionId === id) ?? null,
  listApprovals: async (status = 'PENDING', offset = 0) => {
    const rows = demo_state().approvals.filter(a => a.status === status)
    return page(rows.slice(offset, offset + 100), offset)
  },
  async decideApproval(id, decision, reasonCode, note) {
    const approval = demo_state().approvals.find(a => a.id === id)
    if (!approval || approval.finalDecision) throw new Error('Approval already decided')
    approval.status = decision
    approval.finalDecision = { id: `ad-${id}`, decision, decidedBy: 'demo', decidedAt: Date.now(), reasonCode, note: note ?? null }
    return approval
  },
  listSafetyEvaluations: async offset => page(demo_state().safety.slice(offset ?? 0), offset),
  getSafetyEvaluation: async id => demo_state().safety.find(s => s.id === id) ?? null,
  listShadow: async offset => page(demo_state().shadow.slice(offset ?? 0), offset),
  listEffects: async (policyDecisionId, offset = 0) => {
    const rows = demo_state().effects.filter(e => !policyDecisionId || e.policyDecisionId === policyDecisionId)
    return page(rows.slice(offset, offset + 100), offset)
  },
  getEffect: async id => demo_state().effects.find(e => e.id === id) ?? null,
  listGithubSources: async () => demo_state().githubSources,
  async setGithubSourceStatus(id, status) {
    const source = demo_state().githubSources.find(s => s.id === id)
    if (source) { source.status = status; source.updatedAt = Date.now() }
    return source as GithubSourceItem
  },
  listGithubIdentities: async () => demo_state().githubIdentities,
  async mapGithubIdentity(_sourceId, externalUserId, userId) {
    const s = demo_state()
    const existing = s.githubIdentities.find(m => m.externalUserId === externalUserId)
    if (existing) existing.userId = userId
    else s.githubIdentities.push({ externalUserId, userId })
  },
  listGithubAttributions: async () => demo_state().githubAttributions,
  async assignGithubResource(_sourceId, kind, resourceId, projectId) {
    const s = demo_state()
    const now = Date.now()
    s.githubAttributions.forEach(a => {
      if (a.resourceKind === kind && a.resourceId === resourceId && a.effectiveUntil === null)
        a.effectiveUntil = now
    })
    if (projectId)
      s.githubAttributions.push({ id: `ga-${kind}-${resourceId}-${now}`, resourceKind: kind, resourceId,
        projectId, effectiveFrom: now, effectiveUntil: null })
  },
  listAppreciation: async (kind, actorId) =>
    demo_state()[kind].filter(a => !actorId || a.senderUserId === actorId || a.issuerUserId === actorId || a.recipientUserId === actorId),
  async giveThanks(recipientUserId, message, actorId) {
    demo_state().thanks.unshift({ id: `th-demo-${Date.now()}`, companyId: 'co-aster',
      senderUserId: actorId ?? 'demo', recipientUserId, message, createdAt: Date.now() })
  },
  async recognize(recipientUserId, message, actorId) {
    demo_state().recognition.unshift({ id: `rec-demo-${Date.now()}`, companyId: 'co-aster',
      issuerUserId: actorId ?? 'demo', recipientUserId, message, createdAt: Date.now() })
  },
  listHelp: async () => demo_state().help,
  async requestHelp(title, description, actorId) {
    demo_state().help.unshift({ id: `help-demo-${Date.now()}`, companyId: 'co-aster',
      requesterUserId: actorId ?? 'demo', title, description, status: 'OPEN', createdAt: Date.now(),
      acceptedByUserId: null, acceptedAt: null, finishedAt: null, confirmedAt: null })
  },
  async helpAction(id, action, actorId) {
    const item = demo_state().help.find(h => h.id === id)
    if (!item) return
    const now = Date.now()
    if (action === 'accept') { item.status = 'ACCEPTED'; item.acceptedByUserId = actorId ?? 'demo'; item.acceptedAt = now }
    if (action === 'finish') { item.status = 'FINISHED'; item.finishedAt = now }
    if (action === 'confirm') { item.status = 'CONFIRMED'; item.confirmedAt = now }
  },
  listOrgUnits: async () => demo_state().orgUnits,
}

/* Static build-time mode: one branch is dead-code-eliminated per build. */
export const governance: GovernanceSource = IS_DEMO ? demoSource : server
