/* Governance presentation types (System Cohesion Sweep, F1/F2/D1).
 *
 * These mirror the backend API views 1:1 (camelCase wire shapes). Views never
 * invent business truth: server mode reads the real APIs, demo mode reads the
 * deterministic fixture module — identical structure, different data source.
 */

export interface RuleItem {
  id: string; name: string; description: string; active: boolean; priority: number
  eventType: string; conditions: unknown[]; outcome: { kind: string; data: Record<string, unknown> }
  scope?: { kind: 'TEAM' | 'PROJECT'; id: string }
  version: number; createdBy: string; createdAt: number; updatedAt: number
}

export interface CandidateItem {
  id: string; canonicalEventId: string; ruleId: string; ruleVersion: number
  kind: string; data: Record<string, unknown>; status: string
  ruleSnapshot: Record<string, unknown>; createdAt: number
}

export interface PolicyItem {
  id: string; name: string; description: string; active: boolean
  candidateKind: string | null; eventType: string | null; decision: string
  priority: number; conditions: unknown[]
  scope?: { kind: 'TEAM' | 'PROJECT'; id: string }
  version: number; createdBy: string; createdAt: number; updatedAt: number
}

export interface DecisionItem {
  decisionId: string; candidateId: string; policySetFingerprint: string
  effectiveDecision: string; matchedPolicies: unknown[]; evaluatedPolicies: unknown[]
  explanation: string; createdAt: number
}

export interface ApprovalItem {
  id: string; type: string; policyDecisionId: string; candidateId: string
  requiredAuthority: string; requestedBy: string; requestedAt: number; status: string
  trigger?: 'POLICY' | 'INCENTIVE_SAFETY'; safetyEvaluationId?: string
  finalDecision: null | {
    id: string; decision: string; decidedBy: string; decidedAt: number
    reasonCode: string; note: string | null
  }
}

export interface SafetyEvalItem {
  id: string; candidateId: string; outcome: string
  findings: { id: string; findingType: string; [k: string]: unknown }[]
  evidence: Record<string, unknown>; createdAt: number
}

export interface ShadowItem {
  id: string; canonicalEventId: string; candidateId: string; ruleId: string
  ruleVersion: number; policyDecisionId: string; policyDecision: string
  recipientUserId: string | null; proposedAmount: string | null
  authorizedHypotheticalAmount: string | null; governanceState: string
  outcome: string; reasonCode: string; provenance: Record<string, unknown>
  version: number; createdAt: number; realExecution: boolean
}

export interface EffectItem {
  id: string; candidateId: string; policyDecisionId: string
  approvalDecisionId: string | null; effectType: string; amount: string
  beneficiaryUserId: string; status: 'ISSUED' | 'REVERSED'
  ledgerTransactionId: string; createdAt: number
  reversal: null | { id: string; amount: string; reasonCode: string; initiatedBy: string; createdAt: number }
}

export interface EventItem {
  id: string; type: string; schemaVersion: number; sourceKind: string
  sourceId: string | null; sourceEventId: string | null
  actorId: string | null; subjectId: string | null
  occurredAt: number; receivedAt: number; createdAt: number
  payload: Record<string, unknown>; correlationId: string | null; causationId: string | null
}

/* ── WS2-A: role-specific provenance projections ───────────────────────────
 * Business-language views of the governance chain, composed server-side.
 * No internal nouns for employees; managers get decision context; admins get
 * the summary plus complete drill-down. */

export interface ProvenanceSummary {
  eventType: string | null; occurredAt: number | null; subjectId: string | null
  ruleName: string | null; ruleDescription: string | null
  proposedReward: number | null; scope: { kind: 'TEAM' | 'PROJECT'; id: string } | null
  policyDecision: string | null; policyExplanation: string | null
  safetyOutcome: string | null
}

/* Employee projection (WS2 review): deliberately minimal — no engine nouns,
 * no candidate/policy/safety identifiers, no approver free-text. effectId and
 * ledgerTransactionId exist only to correlate wallet rows; non-payout outcomes
 * carry nulls for payout-only fields. */
export type IncentiveStatus = 'ISSUED' | 'REVERSED'
  | 'AUTHORIZED_PENDING' | 'PENDING_REVIEW' | 'NOT_APPROVED' | 'NOT_AUTHORIZED' | 'SAFEGUARDED'

export interface IncentiveProvenanceItem {
  ledgerTransactionId: string | null; effectId: string | null
  amount: string | null; status: IncentiveStatus; createdAt: number
  eventType: string | null; occurredAt: number | null
  ruleName: string | null; policyReason: 'MATCHED_POLICY' | 'DEFAULT_GOVERNANCE' | null
  decidedBy: string | null; decidedAt: number | null
  reversal: null | { reasonCode: string; createdAt: number }
}

export interface ApprovalContext {
  approval: ApprovalItem
  context: ProvenanceSummary & {
    trigger: string; requiredAuthority: string; myAuthority: string
    effects: EffectItem[]
  }
}

export interface ChainDetail {
  summary: ProvenanceSummary
  event: EventItem | null; candidate: CandidateItem; decision: DecisionItem | null
  safety: SafetyEvalItem | null; approvals: ApprovalItem[]; effects: EffectItem[]
}

export interface GithubSourceItem {
  id: string; provider: 'GITHUB'; name: string; repositoryId: string
  status: 'ACTIVE' | 'DISABLED'; webhookPath: string; createdAt: number; updatedAt: number
}

export interface GithubIdentityItem { externalUserId: string; userId: string }

/* WS1 Slack intake (Decision B): workspace binding + explicit identity mapping. */
export interface SlackWorkspaceItem {
  id: string; provider: 'SLACK'; name: string; externalTeamId: string
  status: 'ACTIVE' | 'DISABLED'; commandPath: string; createdAt: number; updatedAt: number
}

export interface ChannelIdentityItem { externalUserId: string; userId: string }

export interface GithubAttributionItem {
  id: string; resourceKind: 'issue' | 'pull_request'; resourceId: string
  projectId: string | null; effectiveFrom: number; effectiveUntil: number | null
}

export interface AppreciationItem {
  id: string; companyId: string; scope?: { kind: 'TEAM' | 'PROJECT'; id: string }
  recipientUserId: string; message: string; createdAt: number
  senderUserId?: string; issuerUserId?: string
}

export interface HelpItem {
  id: string; companyId: string; scope?: { kind: 'TEAM' | 'PROJECT'; id: string }
  requesterUserId: string; title: string; description: string; status: string
  createdAt: number; acceptedByUserId: string | null; acceptedAt: number | null
  finishedAt: number | null; confirmedAt: number | null
  /* WS1 routing state (Decision A): ROUTED | UNRESOLVED | ESCALATED. */
  routingStatus?: string; routedAt?: number | null; escalatedAt?: number | null
}

export interface OrgUnit {
  id: string; kind: 'TEAM' | 'PROJECT'; name: string; status: 'ACTIVE' | 'CLOSED'
  memberships: { userId: string; manager: boolean; joinedAt: number; leftAt: number | null }[]
}

/* One paged list contract for the UI regardless of the wire shape (B2):
   server envelopes ({rules}, {approvals, offset, limit}, bare lists) are
   normalized by the source implementation, never by the views. hasMore is
   present only where the backend computes it from the visible stream. */
export interface Page<T> { items: T[]; offset: number; limit: number; hasMore?: boolean }

export interface GovernanceSource {
  listEvents(offset?: number): Promise<Page<EventItem>>
  getEvent(id: string): Promise<EventItem | null>
  listRules(offset?: number): Promise<Page<RuleItem>>
  createRule(body: Partial<RuleItem>): Promise<RuleItem>
  setRuleActive(id: string, active: boolean): Promise<RuleItem>
  listCandidates(eventId?: string, offset?: number): Promise<Page<CandidateItem>>
  getCandidate(id: string): Promise<CandidateItem | null>
  listPolicies(offset?: number): Promise<Page<PolicyItem>>
  listDecisions(candidateId?: string, offset?: number): Promise<Page<DecisionItem>>
  getDecision(id: string): Promise<DecisionItem | null>
  listApprovals(status?: string, offset?: number): Promise<Page<ApprovalItem>>
  decideApproval(id: string, decision: 'APPROVED' | 'REJECTED', reasonCode: string, note?: string): Promise<ApprovalItem>
  listSafetyEvaluations(offset?: number): Promise<Page<SafetyEvalItem>>
  getSafetyEvaluation(id: string): Promise<SafetyEvalItem | null>
  listShadow(offset?: number): Promise<Page<ShadowItem>>
  listEffects(policyDecisionId?: string, offset?: number): Promise<Page<EffectItem>>
  getEffect(id: string): Promise<EffectItem | null>
  /* Integrations (F2) */
  listGithubSources(): Promise<GithubSourceItem[]>
  setGithubSourceStatus(id: string, status: 'ACTIVE' | 'DISABLED'): Promise<GithubSourceItem>
  listGithubIdentities(sourceId: string): Promise<GithubIdentityItem[]>
  mapGithubIdentity(sourceId: string, externalUserId: string, userId: string): Promise<void>
  listGithubAttributions(sourceId: string): Promise<GithubAttributionItem[]>
  assignGithubResource(sourceId: string, kind: 'issue' | 'pull_request', resourceId: string, projectId: string | null): Promise<void>
  /* Slack intake (WS1). secret is returned exactly once at create/rotate. */
  listSlackWorkspaces(): Promise<SlackWorkspaceItem[]>
  createSlackWorkspace(name: string, externalTeamId: string): Promise<SlackWorkspaceItem & { secret?: string }>
  setSlackWorkspaceStatus(id: string, status: 'ACTIVE' | 'DISABLED'): Promise<SlackWorkspaceItem>
  rotateSlackSecret(id: string): Promise<SlackWorkspaceItem & { secret?: string }>
  listSlackIdentities(workspaceId: string): Promise<ChannelIdentityItem[]>
  mapSlackIdentity(workspaceId: string, externalUserId: string, userId: string): Promise<void>
  /* People (E8). actorId is demo-only: the server scopes results to the
     authenticated actor; the demo source applies the same filter locally. */
  listAppreciation(kind: 'thanks' | 'recognition', actorId?: string): Promise<AppreciationItem[]>
  /* actorId is demo-only presentation attribution; the server derives the
     actor from the authenticated session and ignores it. */
  giveThanks(recipientUserId: string, message: string, actorId?: string): Promise<void>
  recognize(recipientUserId: string, message: string, actorId?: string): Promise<void>
  listHelp(): Promise<HelpItem[]>
  requestHelp(title: string, description: string, actorId?: string): Promise<void>
  helpAction(id: string, action: 'accept' | 'finish' | 'confirm', actorId?: string): Promise<void>
  /* Organization (D1/F3) */
  listOrgUnits(): Promise<OrgUnit[]>
  /* WS2-A provenance reads (role-scoped, read-only). actorId is demo-only: the
     server derives the caller from the session. Offset pages the
     employee-visible outcome stream. */
  myIncentives(actorId?: string, offset?: number): Promise<Page<IncentiveProvenanceItem>>
  getApprovalContext(requestId: string): Promise<ApprovalContext>
  getChain(candidateId: string): Promise<ChainDetail>
}
