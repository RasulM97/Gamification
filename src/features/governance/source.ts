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
  AppreciationItem, ApprovalContext, ApprovalItem, CandidateItem, ChainDetail, ChannelIdentityItem,
  DecisionItem, EffectItem, EventItem, GithubAttributionItem, GithubIdentityItem, GithubSourceItem,
  GovernanceSource, HelpItem, IncentiveProvenanceItem, IncentiveStatus, OrgUnit, Page, PolicyItem, RuleItem,
  SafetyEvalItem, ShadowItem, SlackWorkspaceItem, WebhookSourceItem,
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
  createGithubSource: (name, repositoryId) =>
    api.post<GithubSourceItem & { secret?: string }>('/integrations/github', { name, repositoryId }),
  setGithubSourceStatus: (id, status) => api.patch<GithubSourceItem>(`/integrations/github/${id}`, { status }),
  rotateGithubSecret: id =>
    api.post<GithubSourceItem & { secret?: string }>(`/integrations/github/${id}/rotate-secret`, {}),
  async listGithubIdentities(sourceId) {
    return (await api.get<{ mappings: GithubIdentityItem[] }>(`/integrations/github/${sourceId}/identities`)).mappings
  },
  async mapGithubIdentity(sourceId, externalUserId, userId) {
    await api.put(`/integrations/github/${sourceId}/identities/${externalUserId}`, { userId })
  },
  async deleteGithubIdentity(sourceId, externalUserId) {
    await api.del(`/integrations/github/${sourceId}/identities/${externalUserId}`)
  },
  async listGithubAttributions(sourceId) {
    return (await api.get<{ attributions: GithubAttributionItem[] }>(
      `/integrations/github/${sourceId}/project-attributions`)).attributions
  },
  async assignGithubResource(sourceId, kind, resourceId, projectId) {
    await api.put(`/integrations/github/${sourceId}/resources/${kind}/${resourceId}/project`, { projectId })
  },
  async listSlackWorkspaces() {
    return (await api.get<{ workspaces: SlackWorkspaceItem[] }>('/integrations/slack')).workspaces
  },
  createSlackWorkspace: (name, externalTeamId) =>
    api.post<SlackWorkspaceItem & { secret?: string }>('/integrations/slack', { name, externalTeamId }),
  setSlackWorkspaceStatus: (id, status) => api.patch<SlackWorkspaceItem>(`/integrations/slack/${id}`, { status }),
  rotateSlackSecret: id =>
    api.post<SlackWorkspaceItem & { secret?: string }>(`/integrations/slack/${id}/rotate-secret`, {}),
  async listSlackIdentities(workspaceId) {
    return (await api.get<{ mappings: ChannelIdentityItem[] }>(`/integrations/slack/${workspaceId}/identities`)).mappings
  },
  async mapSlackIdentity(workspaceId, externalUserId, userId) {
    await api.put(`/integrations/slack/${workspaceId}/identities/${externalUserId}`, { userId })
  },
  async deleteSlackIdentity(workspaceId, externalUserId) {
    await api.del(`/integrations/slack/${workspaceId}/identities/${externalUserId}`)
  },
  async listWebhookSources() {
    return (await api.get<{ sources: WebhookSourceItem[] }>('/integrations/webhooks')).sources
  },
  createWebhookSource: name =>
    api.post<WebhookSourceItem & { secret?: string }>('/integrations/webhooks', { name }),
  setWebhookSourceActive: (id, active) => api.patch<WebhookSourceItem>(`/integrations/webhooks/${id}`, { active }),
  rotateWebhookSecret: id =>
    api.post<WebhookSourceItem & { secret?: string }>(`/integrations/webhooks/${id}/rotate-secret`, {}),
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
  /* WS2-A provenance reads — backend composes and authorizes per role.
     The demo-only actorId parameter is ignored: the session is authoritative. */
  async myIncentives(_actorId?: string, offset?: number) {
    const r = await api.get<{ items: IncentiveProvenanceItem[]; offset: number; limit: number; hasMore: boolean }>(
      `/provenance/me?offset=${offset ?? 0}`)
    return { ...page(r.items, r.offset, r.limit), hasMore: r.hasMore }
  },
  getApprovalContext: id => api.get<ApprovalContext>(`/provenance/approvals/${id}`),
  getChain: id => api.get<ChainDetail>(`/provenance/chain/${id}`),
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
  async createGithubSource(name, repositoryId) {
    const s = demo_state()
    const now = Date.now()
    const item: GithubSourceItem = {
      id: `gh-demo-${now}`, provider: 'GITHUB', name, repositoryId, status: 'ACTIVE',
      webhookPath: `/api/webhooks/github/demo-key-${s.githubSources.length + 1}`,
      createdAt: now, updatedAt: now,
    }
    s.githubSources.push(item)
    return { ...item, secret: 'demo-signing-secret-shown-once' }
  },
  async setGithubSourceStatus(id, status) {
    const source = demo_state().githubSources.find(s => s.id === id)
    if (source) { source.status = status; source.updatedAt = Date.now() }
    return source as GithubSourceItem
  },
  async rotateGithubSecret(id) {
    const source = demo_state().githubSources.find(s => s.id === id)
    if (source) source.updatedAt = Date.now()
    return { ...(source as GithubSourceItem), secret: 'demo-signing-secret-rotated' }
  },
  listGithubIdentities: async () => demo_state().githubIdentities,
  async mapGithubIdentity(_sourceId, externalUserId, userId) {
    const s = demo_state()
    const existing = s.githubIdentities.find(m => m.externalUserId === externalUserId)
    if (existing) existing.userId = userId
    else s.githubIdentities.push({ externalUserId, userId })
  },
  async deleteGithubIdentity(_sourceId, externalUserId) {
    const s = demo_state()
    s.githubIdentities = s.githubIdentities.filter(m => m.externalUserId !== externalUserId)
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
  listSlackWorkspaces: async () => demo_state().slackWorkspaces,
  async createSlackWorkspace(name, externalTeamId) {
    const s = demo_state()
    const now = Date.now()
    const item: SlackWorkspaceItem = {
      id: `cw-demo-${now}`, provider: 'SLACK', name, externalTeamId, status: 'ACTIVE',
      commandPath: `/api/channels/slack/demo-key-${s.slackWorkspaces.length + 1}`,
      createdAt: now, updatedAt: now,
    }
    s.slackWorkspaces.push(item)
    return { ...item, secret: 'demo-signing-secret-shown-once' }
  },
  async setSlackWorkspaceStatus(id, status) {
    const workspace = demo_state().slackWorkspaces.find(w => w.id === id)
    if (workspace) { workspace.status = status; workspace.updatedAt = Date.now() }
    return workspace as SlackWorkspaceItem
  },
  async rotateSlackSecret(id) {
    const workspace = demo_state().slackWorkspaces.find(w => w.id === id)
    if (workspace) workspace.updatedAt = Date.now()
    return { ...(workspace as SlackWorkspaceItem), secret: 'demo-signing-secret-rotated' }
  },
  listSlackIdentities: async workspaceId =>
    demo_state().slackIdentities.filter(m => m.workspaceId === workspaceId)
      .map(({ externalUserId, userId }) => ({ externalUserId, userId })),
  async mapSlackIdentity(workspaceId, externalUserId, userId) {
    const s = demo_state()
    const existing = s.slackIdentities.find(m => m.workspaceId === workspaceId && m.externalUserId === externalUserId)
    if (existing) existing.userId = userId
    else s.slackIdentities.push({ workspaceId, externalUserId, userId })
  },
  async deleteSlackIdentity(workspaceId, externalUserId) {
    const s = demo_state()
    s.slackIdentities = s.slackIdentities.filter(m => !(m.workspaceId === workspaceId && m.externalUserId === externalUserId))
  },
  /* WS5 demo: deterministic webhook sources; secrets are obvious fakes shown
     once, mirroring the one-time contract without real credential material. */
  listWebhookSources: async () => demo_state().webhookSources,
  async createWebhookSource(name) {
    const s = demo_state()
    const now = Date.now()
    const item: WebhookSourceItem = {
      id: `wh-demo-${now}`, name, sourceKey: `demo-webhook-key-${s.webhookSources.length + 1}`,
      active: true, configured: true, createdAt: now, updatedAt: now,
    }
    s.webhookSources.push(item)
    return { ...item, secret: 'demo-webhook-secret-shown-once' }
  },
  async setWebhookSourceActive(id, active) {
    const source = demo_state().webhookSources.find(x => x.id === id)
    if (source) { source.active = active; source.updatedAt = Date.now() }
    return source as WebhookSourceItem
  },
  async rotateWebhookSecret(id) {
    const source = demo_state().webhookSources.find(x => x.id === id)
    if (source) source.updatedAt = Date.now()
    return { ...(source as WebhookSourceItem), secret: 'demo-webhook-secret-rotated' }
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
  /* WS2-A demo provenance — the same projections, composed locally from the
     deterministic fixtures. Never calls the network. */
  myIncentives: async (actorId, offset = 0) => {
    const s = demo_state()
    /* Same minimized employee shape as the server projection: payout rows
       plus non-payout governance outcomes, no engine internals. */
    const policyReason = (d?: DecisionItem | null): 'MATCHED_POLICY' | 'DEFAULT_GOVERNANCE' | null =>
      !d ? null : d.matchedPolicies.length === 1 && d.matchedPolicies[0] === 'pol-default'
        ? 'DEFAULT_GOVERNANCE' : 'MATCHED_POLICY'
    const facts = (candidateId: string) => {
      const candidate = s.candidates.find(c => c.id === candidateId)
      const event = s.events.find(ev => ev.id === candidate?.canonicalEventId)
      return { candidate, event }
    }
    const payouts = s.effects.filter(e => e.beneficiaryUserId === actorId).map(e => {
      const { candidate, event } = facts(e.candidateId)
      const decision = s.decisions.find(d => d.candidateId === e.candidateId)
      const approval = s.approvals.find(a => a.finalDecision?.id === e.approvalDecisionId)?.finalDecision ?? null
      return {
        ledgerTransactionId: e.ledgerTransactionId, effectId: e.id, amount: e.amount,
        status: e.status as IncentiveStatus, createdAt: e.createdAt,
        eventType: event?.type ?? null, occurredAt: event?.occurredAt ?? null,
        ruleName: (candidate?.ruleSnapshot?.name as string) ?? null,
        policyReason: policyReason(decision),
        decidedBy: approval?.decidedBy ?? null, decidedAt: approval?.decidedAt ?? null,
        reversal: e.reversal && { reasonCode: e.reversal.reasonCode, createdAt: e.reversal.createdAt },
      }
    })
    const outcomes = s.candidates.flatMap(c => {
      const event = s.events.find(ev => ev.id === c.canonicalEventId)
      if (((event?.subjectId ?? event?.actorId) ?? null) !== actorId) return []
      if (s.effects.some(e => e.candidateId === c.id)) return []
      const decision = s.decisions.find(d => d.candidateId === c.id) ?? null
      /* Same derivation as the server projection — execution semantics are
         the authority; SHADOW_ONLY is always invisible. */
      if (!decision || decision.effectiveDecision === 'SHADOW_ONLY') return []
      const safety = s.safety.find(x => x.candidateId === c.id) ?? null
      const applicable = (safetyReview: boolean) =>
        s.approvals.find(a => a.candidateId === c.id
          && a.policyDecisionId === decision.decisionId
          && (safetyReview ? a.safetyEvaluationId === safety?.id : !a.safetyEvaluationId)) ?? null
      /* statusAt mirrors the server's derivation from the same fixture
         timestamps: when the CURRENT state took effect — current safety
         evaluation time, policy decision time, rejection/approval decision
         time, or the start of the applicable waiting state — never the
         candidate's creation time. Demo-only field; the server contract is
         unchanged. */
      const build = (status: IncentiveStatus, rejected: { decidedBy: string; decidedAt: number } | null,
                     statusAt: number) => [{
        ledgerTransactionId: null, effectId: null, amount: null, status,
        createdAt: c.createdAt,
        eventType: event?.type ?? null, occurredAt: event?.occurredAt ?? null,
        ruleName: (c.ruleSnapshot?.name as string) ?? null,
        policyReason: policyReason(decision),
        decidedBy: rejected?.decidedBy ?? null, decidedAt: rejected?.decidedAt ?? null,
        reversal: null,
        statusAt,
      }]
      if (safety?.outcome === 'SUPPRESS_INCENTIVE') return build('SAFEGUARDED', null, safety.createdAt)
      if (decision.effectiveDecision === 'BLOCK') return build('NOT_AUTHORIZED', null, decision.createdAt)
      if (decision.effectiveDecision === 'REQUIRE_APPROVAL') {
        const request = applicable(false)
        const fd = request?.finalDecision ?? null
        if (!fd) return build('PENDING_REVIEW', null, request?.requestedAt ?? decision.createdAt)
        return fd.decision === 'REJECTED'
          ? build('NOT_APPROVED', fd, fd.decidedAt) : build('AUTHORIZED_PENDING', null, fd.decidedAt)
      }
      if (safety?.outcome === 'REQUIRE_REVIEW') {
        const request = applicable(true)
        const fd = request?.finalDecision ?? null
        if (!fd) return build('PENDING_REVIEW', null, request?.requestedAt ?? decision.createdAt)
        return fd.decision === 'REJECTED'
          ? build('NOT_APPROVED', fd, fd.decidedAt) : build('AUTHORIZED_PENDING', null, fd.decidedAt)
      }
      return build('AUTHORIZED_PENDING', null, decision.createdAt)
    })
    const items = [...payouts, ...outcomes].sort((a, b) =>
      b.createdAt - a.createdAt || (b.ledgerTransactionId ?? '').localeCompare(a.ledgerTransactionId ?? ''))
    return { ...page(items.slice(offset, offset + 100), offset), hasMore: items.length > offset + 100 }
  },
  async getApprovalContext(requestId) {
    const s = demo_state()
    const approval = s.approvals.find(a => a.id === requestId)
    if (!approval) throw new Error('Approval request not found')
    const candidate = s.candidates.find(c => c.id === approval.candidateId)
    const event = s.events.find(ev => ev.id === candidate?.canonicalEventId)
    const decision = s.decisions.find(d => d.candidateId === approval.candidateId)
    const safety = s.safety.find(x => x.candidateId === approval.candidateId)
    const snapshot = candidate?.ruleSnapshot ?? {}
    return {
      approval,
      context: {
        eventType: event?.type ?? null, occurredAt: event?.occurredAt ?? null,
        subjectId: (event?.subjectId ?? event?.actorId) ?? null,
        ruleName: (snapshot.name as string) ?? null, ruleDescription: null,
        proposedReward: typeof candidate?.data?.proposedReward === 'number' ? candidate.data.proposedReward as number : null,
        scope: (snapshot as { scope?: { kind: 'TEAM' | 'PROJECT'; id: string } }).scope ?? null,
        policyDecision: decision?.effectiveDecision ?? null,
        policyExplanation: decision?.explanation ?? null,
        safetyOutcome: safety?.outcome ?? null,
        trigger: approval.trigger ?? 'POLICY', requiredAuthority: approval.requiredAuthority,
        myAuthority: 'MANAGER',
        effects: s.effects.filter(e => e.candidateId === approval.candidateId),
      },
    }
  },
  async getChain(candidateId) {
    const s = demo_state()
    const candidate = s.candidates.find(c => c.id === candidateId)
    if (!candidate) throw new Error('Candidate not found')
    const event = s.events.find(ev => ev.id === candidate.canonicalEventId) ?? null
    const decision = s.decisions.find(d => d.candidateId === candidateId) ?? null
    const safety = s.safety.find(x => x.candidateId === candidateId) ?? null
    const snapshot = candidate.ruleSnapshot ?? {}
    return {
      summary: {
        eventType: event?.type ?? null, occurredAt: event?.occurredAt ?? null,
        subjectId: (event?.subjectId ?? event?.actorId) ?? null,
        ruleName: (snapshot.name as string) ?? null, ruleDescription: null,
        proposedReward: typeof candidate.data?.proposedReward === 'number' ? candidate.data.proposedReward as number : null,
        scope: (snapshot as { scope?: { kind: 'TEAM' | 'PROJECT'; id: string } }).scope ?? null,
        policyDecision: decision?.effectiveDecision ?? null,
        policyExplanation: decision?.explanation ?? null,
        safetyOutcome: safety?.outcome ?? null,
      },
      event, candidate, decision, safety,
      approvals: s.approvals.filter(a => a.candidateId === candidateId),
      effects: s.effects.filter(e => e.candidateId === candidateId),
    }
  },
}

/* Static build-time mode: one branch is dead-code-eliminated per build. */
export const governance: GovernanceSource = IS_DEMO ? demoSource : server
