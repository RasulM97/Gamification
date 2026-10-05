/* Deterministic demo governance dataset (Cohesion D1) — ONE coherent story
 * for the Aster Dynamics pilot company, aligned with the demo seed users:
 *   u-dana (Admin) · u-marcus (Manager, Sales) · u-priya · u-jonas · u-aisha
 *
 * These are PRESENTATION FIXTURES, not a business engine: no evaluation,
 * safety or economic logic runs here. Demo mutations (approval decisions,
 * attribution changes) edit this local copy only — never a Ledger, never a
 * server. Times anchor to load like the existing demo seed.
 */
import type {
  AppreciationItem, ApprovalItem, CandidateItem, DecisionItem, EffectItem, EventItem,
  GithubAttributionItem, GithubIdentityItem, GithubSourceItem, HelpItem, OrgUnit,
  PolicyItem, RuleItem, SafetyEvalItem, ShadowItem,
} from './types'

const H = 3600e3, D = 24 * H

export function demoGovernance(now = Date.now()) {
  const orgUnits: OrgUnit[] = [
    { id: 'team-sales', kind: 'TEAM', name: 'Sales', status: 'ACTIVE', memberships: [
      { userId: 'u-marcus', manager: true, joinedAt: now - 90 * D, leftAt: null },
      { userId: 'u-priya', manager: false, joinedAt: now - 90 * D, leftAt: null },
      { userId: 'u-jonas', manager: false, joinedAt: now - 60 * D, leftAt: null }] },
    { id: 'team-ops', kind: 'TEAM', name: 'Operations', status: 'ACTIVE', memberships: [
      { userId: 'u-dana', manager: true, joinedAt: now - 120 * D, leftAt: null },
      { userId: 'u-aisha', manager: false, joinedAt: now - 45 * D, leftAt: null }] },
    { id: 'proj-northstar', kind: 'PROJECT', name: 'Northstar Onboarding', status: 'ACTIVE', memberships: [
      { userId: 'u-marcus', manager: true, joinedAt: now - 21 * D, leftAt: null },
      { userId: 'u-priya', manager: false, joinedAt: now - 21 * D, leftAt: null },
      { userId: 'u-jonas', manager: false, joinedAt: now - 14 * D, leftAt: null }] },
    { id: 'proj-q4', kind: 'PROJECT', name: 'Q4 Revenue Push', status: 'ACTIVE', memberships: [
      { userId: 'u-aisha', manager: false, joinedAt: now - 30 * D, leftAt: null },
      { userId: 'u-priya', manager: false, joinedAt: now - 30 * D, leftAt: null }] },
  ]

  const rules: RuleItem[] = [
    { id: 'rule-pr-merged', name: 'Merged pull request', description: 'A merged PR in an attributed repository earns a fixed incentive.',
      active: true, priority: 10, eventType: 'github.pull_request.merged', conditions: [],
      outcome: { kind: 'INCENTIVE', data: { proposedReward: 5 } }, scope: { kind: 'PROJECT', id: 'proj-northstar' },
      version: 2, createdBy: 'u-dana', createdAt: now - 20 * D, updatedAt: now - 12 * D },
    { id: 'rule-help-confirmed', name: 'Confirmed help', description: 'Finished and confirmed help earns the helper a small incentive.',
      active: true, priority: 5, eventType: 'internal.help.confirmed', conditions: [],
      outcome: { kind: 'INCENTIVE', data: { proposedReward: 3 } },
      version: 1, createdBy: 'u-dana', createdAt: now - 18 * D, updatedAt: now - 18 * D },
    { id: 'rule-thanks-burst', name: 'Thanks burst (observation)', description: 'Shadow-only: observes thanks bursts before anyone enables a payout.',
      active: true, priority: 0, eventType: 'internal.peer.thanks', conditions: [],
      outcome: { kind: 'INCENTIVE', data: { proposedReward: 8 } },
      version: 1, createdBy: 'u-dana', createdAt: now - 6 * D, updatedAt: now - 6 * D },
  ]

  const policies: PolicyItem[] = [
    { id: 'pol-approval', name: 'Incentives of 5+ Coins need approval', description: 'Manager-or-admin approval gate for larger incentives.',
      active: true, candidateKind: 'INCENTIVE', eventType: null, decision: 'REQUIRE_APPROVAL', priority: 10,
      conditions: [{ field: 'data.proposedReward', op: 'GTE', value: 5 }],
      version: 1, createdBy: 'u-dana', createdAt: now - 19 * D, updatedAt: now - 19 * D },
    { id: 'pol-shadow', name: 'Observe thanks bursts', description: 'Keeps the thanks-burst rule in shadow mode while it is tuned.',
      active: true, candidateKind: 'INCENTIVE', eventType: 'internal.peer.thanks', decision: 'SHADOW_ONLY', priority: 20,
      conditions: [], version: 1, createdBy: 'u-dana', createdAt: now - 6 * D, updatedAt: now - 6 * D },
    { id: 'pol-default', name: 'Default allow', description: 'Baseline: small incentives pass without approval.',
      active: true, candidateKind: 'INCENTIVE', eventType: null, decision: 'ALLOW', priority: 0,
      conditions: [], version: 3, createdBy: 'u-dana', createdAt: now - 19 * D, updatedAt: now - 9 * D },
  ]

  const events: EventItem[] = [
    { id: 'ce-pr-412', type: 'github.pull_request.merged', schemaVersion: 1, sourceKind: 'TRUSTED_CONNECTOR',
      sourceId: 'gh-1', sourceEventId: 'evt-412', actorId: 'u-priya', subjectId: 'u-priya',
      occurredAt: now - 2 * D, receivedAt: now - 2 * D, createdAt: now - 2 * D,
      payload: { repositoryId: '770041', number: 412, title: 'Northstar provisioning webhook handler' },
      correlationId: null, causationId: null },
    { id: 'ce-pr-87', type: 'github.pull_request.merged', schemaVersion: 1, sourceKind: 'TRUSTED_CONNECTOR',
      sourceId: 'gh-1', sourceEventId: 'evt-87', actorId: 'u-jonas', subjectId: 'u-jonas',
      occurredAt: now - 26 * H, receivedAt: now - 26 * H, createdAt: now - 26 * H,
      payload: { repositoryId: '770041', number: 87, title: 'Field sync retry logic' },
      correlationId: null, causationId: null },
    { id: 'ce-thanks-1', type: 'internal.peer.thanks', schemaVersion: 1, sourceKind: 'INTERNAL',
      sourceId: null, sourceEventId: null, actorId: 'u-priya', subjectId: 'u-jonas',
      occurredAt: now - 30 * H, receivedAt: now - 30 * H, createdAt: now - 30 * H,
      payload: { message: 'Covered my client call while I was stuck in the audit — thank you!' },
      correlationId: null, causationId: null },
    { id: 'ce-help-1', type: 'internal.help.confirmed', schemaVersion: 1, sourceKind: 'INTERNAL',
      sourceId: null, sourceEventId: null, actorId: 'u-priya', subjectId: 'u-jonas',
      occurredAt: now - 4 * D, receivedAt: now - 4 * D, createdAt: now - 4 * D,
      payload: { helpRequestId: 'help-2' }, correlationId: null, causationId: null },
    { id: 'ce-thanks-old', type: 'internal.peer.thanks', schemaVersion: 1, sourceKind: 'INTERNAL',
      sourceId: null, sourceEventId: null, actorId: 'u-marcus', subjectId: 'u-aisha',
      occurredAt: now - 16 * D, receivedAt: now - 16 * D, createdAt: now - 16 * D,
      payload: { message: 'Duplicate delivery — superseded by evt replay guard' },
      correlationId: null, causationId: null },
  ]

  const candidates: CandidateItem[] = [
    { id: 'rc-pr-412', canonicalEventId: 'ce-pr-412', ruleId: 'rule-pr-merged', ruleVersion: 2,
      kind: 'INCENTIVE', data: { proposedReward: 5, recognition: false, approvalHint: 'MANAGER' },
      status: 'PROPOSED', ruleSnapshot: { name: 'Merged pull request', priority: 10 }, createdAt: now - 2 * D },
    { id: 'rc-pr-87', canonicalEventId: 'ce-pr-87', ruleId: 'rule-pr-merged', ruleVersion: 2,
      kind: 'INCENTIVE', data: { proposedReward: 5, recognition: false, approvalHint: 'MANAGER' },
      status: 'PROPOSED', ruleSnapshot: { name: 'Merged pull request', priority: 10 }, createdAt: now - 26 * H },
    { id: 'rc-help-1', canonicalEventId: 'ce-help-1', ruleId: 'rule-help-confirmed', ruleVersion: 1,
      kind: 'INCENTIVE', data: { proposedReward: 3, recognition: true },
      status: 'PROPOSED', ruleSnapshot: { name: 'Confirmed help', priority: 5 }, createdAt: now - 4 * D },
    { id: 'rc-thanks-1', canonicalEventId: 'ce-thanks-1', ruleId: 'rule-thanks-burst', ruleVersion: 1,
      kind: 'INCENTIVE', data: { proposedReward: 8, recognition: true },
      status: 'PROPOSED', ruleSnapshot: { name: 'Thanks burst (observation)', priority: 0 }, createdAt: now - 30 * H },
    { id: 'rc-thanks-old', canonicalEventId: 'ce-thanks-old', ruleId: 'rule-thanks-burst', ruleVersion: 1,
      kind: 'INCENTIVE', data: { proposedReward: 8, recognition: true },
      status: 'PROPOSED', ruleSnapshot: { name: 'Thanks burst (observation)', priority: 0 }, createdAt: now - 16 * D },
  ]

  const decisions: DecisionItem[] = [
    { decisionId: 'pd-pr-412', candidateId: 'rc-pr-412', policySetFingerprint: 'fp-2026-09-a',
      effectiveDecision: 'REQUIRE_APPROVAL', matchedPolicies: ['pol-approval'], evaluatedPolicies: ['pol-shadow', 'pol-approval', 'pol-default'],
      explanation: 'Proposed incentive of 5 Coins meets the approval threshold.', createdAt: now - 2 * D },
    { decisionId: 'pd-pr-87', candidateId: 'rc-pr-87', policySetFingerprint: 'fp-2026-10-a',
      effectiveDecision: 'REQUIRE_APPROVAL', matchedPolicies: ['pol-approval'], evaluatedPolicies: ['pol-shadow', 'pol-approval', 'pol-default'],
      explanation: 'Proposed incentive of 5 Coins meets the approval threshold.', createdAt: now - 26 * H },
    { decisionId: 'pd-help-1', candidateId: 'rc-help-1', policySetFingerprint: 'fp-2026-09-a',
      effectiveDecision: 'ALLOW', matchedPolicies: ['pol-default'], evaluatedPolicies: ['pol-shadow', 'pol-approval', 'pol-default'],
      explanation: 'Below the approval threshold; default allow applies.', createdAt: now - 4 * D },
    { decisionId: 'pd-thanks-1', candidateId: 'rc-thanks-1', policySetFingerprint: 'fp-2026-10-a',
      effectiveDecision: 'SHADOW_ONLY', matchedPolicies: ['pol-shadow'], evaluatedPolicies: ['pol-shadow', 'pol-approval', 'pol-default'],
      explanation: 'Observation only — no payout while the rule is in shadow mode.', createdAt: now - 30 * H },
    { decisionId: 'pd-thanks-old', candidateId: 'rc-thanks-old', policySetFingerprint: 'fp-2026-09-a',
      effectiveDecision: 'SHADOW_ONLY', matchedPolicies: ['pol-shadow'], evaluatedPolicies: ['pol-shadow', 'pol-default'],
      explanation: 'Observation only — no payout while the rule is in shadow mode.', createdAt: now - 16 * D },
  ]

  const safety: SafetyEvalItem[] = [
    { id: 'saf-pr-412', candidateId: 'rc-pr-412', outcome: 'CLEAR', findings: [],
      evidence: { historySemantics: 'ARRIVED_INCENTIVE_EVENTS_AT_OR_BEFORE_OCCURRENCE' }, createdAt: now - 2 * D },
    { id: 'saf-pr-87', candidateId: 'rc-pr-87', outcome: 'CLEAR', findings: [],
      evidence: { historySemantics: 'ARRIVED_INCENTIVE_EVENTS_AT_OR_BEFORE_OCCURRENCE' }, createdAt: now - 26 * H },
    { id: 'saf-help-1', candidateId: 'rc-help-1', outcome: 'CLEAR', findings: [],
      evidence: { historySemantics: 'ARRIVED_INCENTIVE_EVENTS_AT_OR_BEFORE_OCCURRENCE' }, createdAt: now - 4 * D },
    { id: 'saf-thanks-old', candidateId: 'rc-thanks-old', outcome: 'REQUIRE_REVIEW', createdAt: now - 16 * D,
      findings: [{ id: 'f-dup', findingType: 'REPEAT_PAIR_CONCENTRATION', windowMs: 604800000, threshold: 4 }],
      evidence: { historySemantics: 'ARRIVED_INCENTIVE_EVENTS_AT_OR_BEFORE_OCCURRENCE' } },
  ]

  const approvals: ApprovalItem[] = [
    { id: 'ap-pr-87', type: 'GOVERNANCE', policyDecisionId: 'pd-pr-87', candidateId: 'rc-pr-87',
      requiredAuthority: 'MANAGER_OR_ADMIN', requestedBy: 'u-dana', requestedAt: now - 25 * H,
      status: 'PENDING', trigger: 'POLICY', finalDecision: null },
    { id: 'ap-thanks-old', type: 'GOVERNANCE', policyDecisionId: 'pd-thanks-old', candidateId: 'rc-thanks-old',
      requiredAuthority: 'ADMIN', requestedBy: 'u-dana', requestedAt: now - 15 * D,
      status: 'APPROVED', trigger: 'INCENTIVE_SAFETY', safetyEvaluationId: 'saf-thanks-old',
      finalDecision: { id: 'ad-thanks-old', decision: 'APPROVED', decidedBy: 'u-dana', decidedAt: now - 15 * D,
        reasonCode: 'REVIEWED', note: 'Duplicate delivery confirmed; payout voided via reversal instead.' } },
    { id: 'ap-pr-412', type: 'GOVERNANCE', policyDecisionId: 'pd-pr-412', candidateId: 'rc-pr-412',
      requiredAuthority: 'MANAGER_OR_ADMIN', requestedBy: 'u-dana', requestedAt: now - 2 * D,
      status: 'APPROVED', trigger: 'POLICY',
      finalDecision: { id: 'ad-pr-412', decision: 'APPROVED', decidedBy: 'u-marcus', decidedAt: now - 47 * H,
        reasonCode: 'MERIT', note: null } },
  ]

  const effects: EffectItem[] = [
    { id: 'ee-pr-412', candidateId: 'rc-pr-412', policyDecisionId: 'pd-pr-412', approvalDecisionId: 'ad-pr-412',
      effectType: 'INCENTIVE_CREDIT', amount: '5', beneficiaryUserId: 'u-priya', status: 'ISSUED',
      ledgerTransactionId: 'lt-ee-pr-412', createdAt: now - 46 * H, reversal: null },
    { id: 'ee-help-1', candidateId: 'rc-help-1', policyDecisionId: 'pd-help-1', approvalDecisionId: null,
      effectType: 'INCENTIVE_CREDIT', amount: '3', beneficiaryUserId: 'u-jonas', status: 'ISSUED',
      ledgerTransactionId: 'lt-ee-help-1', createdAt: now - 4 * D, reversal: null },
    { id: 'ee-thanks-old', candidateId: 'rc-thanks-old', policyDecisionId: 'pd-thanks-old', approvalDecisionId: 'ad-thanks-old',
      effectType: 'INCENTIVE_CREDIT', amount: '8', beneficiaryUserId: 'u-aisha', status: 'REVERSED',
      ledgerTransactionId: 'lt-ee-thanks-old', createdAt: now - 15 * D,
      reversal: { id: 'er-thanks-old', amount: '-8', reasonCode: 'INVALIDATED', initiatedBy: 'u-dana', createdAt: now - 14 * D } },
  ]

  const shadow: ShadowItem[] = [
    { id: 'sh-thanks-1', canonicalEventId: 'ce-thanks-1', candidateId: 'rc-thanks-1', ruleId: 'rule-thanks-burst',
      ruleVersion: 1, policyDecisionId: 'pd-thanks-1', policyDecision: 'SHADOW_ONLY',
      recipientUserId: 'u-jonas', proposedAmount: '8', authorizedHypotheticalAmount: null,
      governanceState: 'REQUIRE_APPROVAL', outcome: 'PENDING_APPROVAL', reasonCode: 'SHADOW_OBSERVATION',
      provenance: { evaluation: 'shadow' }, version: 'e10-v1', createdAt: now - 30 * H, realExecution: false },
    { id: 'sh-thanks-old', canonicalEventId: 'ce-thanks-old', candidateId: 'rc-thanks-old', ruleId: 'rule-thanks-burst',
      ruleVersion: 1, policyDecisionId: 'pd-thanks-old', policyDecision: 'SHADOW_ONLY',
      recipientUserId: 'u-aisha', proposedAmount: '8', authorizedHypotheticalAmount: null,
      governanceState: 'REQUIRE_APPROVAL', outcome: 'PENDING_APPROVAL', reasonCode: 'SHADOW_OBSERVATION',
      provenance: { evaluation: 'shadow' }, version: 'e10-v1', createdAt: now - 16 * D, realExecution: false },
  ]

  const githubSources: GithubSourceItem[] = [
    { id: 'gh-1', provider: 'GITHUB', name: 'aster-dynamics/core-app', repositoryId: '770041',
      status: 'ACTIVE', webhookPath: '/api/webhooks/github/demo-source-key', createdAt: now - 21 * D, updatedAt: now - 21 * D },
  ]
  const githubIdentities: GithubIdentityItem[] = [
    { externalUserId: '881001', userId: 'u-priya' },
    { externalUserId: '881002', userId: 'u-jonas' },
    { externalUserId: '881003', userId: 'u-marcus' },
  ]
  const githubAttributions: GithubAttributionItem[] = [
    { id: 'ga-412', resourceKind: 'issue', resourceId: '412', projectId: 'proj-northstar',
      effectiveFrom: now - 12 * D, effectiveUntil: null },
    { id: 'ga-87', resourceKind: 'pull_request', resourceId: '87', projectId: 'proj-northstar',
      effectiveFrom: now - 8 * D, effectiveUntil: null },
    { id: 'ga-388', resourceKind: 'issue', resourceId: '388', projectId: 'proj-q4',
      effectiveFrom: now - 30 * D, effectiveUntil: now - 10 * D },
  ]

  const thanks: AppreciationItem[] = [
    { id: 'th-1', companyId: 'co-aster', senderUserId: 'u-priya', recipientUserId: 'u-jonas',
      message: 'Covered my client call while I was stuck in the audit — thank you!', createdAt: now - 30 * H,
      scope: { kind: 'PROJECT', id: 'proj-northstar' } },
    { id: 'th-2', companyId: 'co-aster', senderUserId: 'u-aisha', recipientUserId: 'u-priya',
      message: 'The discrepancy sheet saved me hours.', createdAt: now - 3 * D },
  ]
  const recognition: AppreciationItem[] = [
    { id: 'rec-1', companyId: 'co-aster', issuerUserId: 'u-marcus', recipientUserId: 'u-priya',
      message: 'Outstanding work on the Northstar onboarding pack.', createdAt: now - 5 * H,
      scope: { kind: 'PROJECT', id: 'proj-northstar' } },
  ]
  const help: HelpItem[] = [
    { id: 'help-1', companyId: 'co-aster', requesterUserId: 'u-aisha', title: 'ERP export access',
      description: 'Need the Q3 commission extract permissions for the reconciliation task.',
      status: 'OPEN', createdAt: now - 6 * H, acceptedByUserId: null, acceptedAt: null,
      finishedAt: null, confirmedAt: null },
    { id: 'help-2', companyId: 'co-aster', requesterUserId: 'u-priya', title: 'Variance report review',
      description: 'Second pair of eyes on the warehouse A variance report.',
      status: 'CONFIRMED', createdAt: now - 5 * D, acceptedByUserId: 'u-jonas', acceptedAt: now - 5 * D,
      finishedAt: now - 4 * D - 2 * H, confirmedAt: now - 4 * D },
  ]

  return { orgUnits, rules, policies, events, candidates, decisions, safety, approvals,
           effects, shadow, githubSources, githubIdentities, githubAttributions,
           thanks, recognition, help }
}

export type DemoGovernance = ReturnType<typeof demoGovernance>
