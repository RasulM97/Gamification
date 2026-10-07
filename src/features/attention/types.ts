/* WS3 attention contracts — the normalized read model shared by both
 * surfaces. The backend computes category/state/nextAction authoritatively;
 * the frontend only groups, sorts, presents, and navigates. `kind` is a
 * business key resolved through i18n; `nav.view` names an existing surface
 * that owns the real action. */
export type AttentionCategory = 'ACTION_REQUIRED' | 'WAITING' | 'RESOLVED_RECENTLY' | 'INFORMATION'

export interface AttentionItem {
  id: string
  category: AttentionCategory
  kind: string
  title: string | null
  state: string
  occurredAt: number
  nextAction: string | null
  nav: { view: string }
  scope?: { kind: 'TEAM' | 'PROJECT'; id: string }
}

export interface IncentiveFlow {
  /* CURRENT state — true right now, no time cutoff. */
  current: { pending: number; held: number; safeguarded: number }
  /* RECENT flow — what happened inside the fixed window. */
  recent: { issued: number; rejected: number; windowDays: number }
}

export interface AttentionFlow {
  waitingDecisions: AttentionItem[]
  unresolvedHelp: AttentionItem[]
  incentiveFlow: IncentiveFlow
  resolvedRecently: AttentionItem[]
}

export interface AttentionActor {
  id: string
  role: string
}

export interface AttentionSource {
  myAttention(me: AttentionActor): Promise<AttentionItem[]>
  teamFlow(me: AttentionActor): Promise<AttentionFlow>
}
