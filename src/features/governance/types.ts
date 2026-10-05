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

export interface GithubSourceItem {
  id: string; provider: 'GITHUB'; name: string; repositoryId: string
  status: 'ACTIVE' | 'DISABLED'; webhookPath: string; createdAt: number; updatedAt: number
}

export interface GithubIdentityItem { externalUserId: string; userId: string }

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
}

export interface OrgUnit {
  id: string; kind: 'TEAM' | 'PROJECT'; name: string; status: 'ACTIVE' | 'CLOSED'
  memberships: { userId: string; manager: boolean; joinedAt: number; leftAt: number | null }[]
}

/* One paged list contract for the UI regardless of the wire shape (B2):
   server envelopes ({rules}, {approvals, offset, limit}, bare lists) are
   normalized by the source implementation, never by the views. */
export interface Page<T> { items: T[]; offset: number; limit: number }

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
}
