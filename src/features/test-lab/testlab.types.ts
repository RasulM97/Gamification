export type UatResult = 'PASS' | 'FAIL' | 'WARN'
export type IssueSeverity = 'P0' | 'P1' | 'P2' | 'P3'
export type IssueCategory = 'UX' | 'PERMISSION' | 'DOMAIN' | 'DATA' | 'API' | 'VISUAL' | 'PERFORMANCE' | 'OTHER'

/* Compact before/after summary — never a full state dump. */
export interface StateDelta {
  entity: string            // e.g. 'task', 'wallet'
  fields: string[]          // e.g. ['status OPEN → IN_PROGRESS', 'owner null → u-priya']
}

export interface UatEvent {
  ts: number
  sessionId: string
  seq: number
  mode: 'demo' | 'server'
  appVersion: string
  actorId: string
  actorName: string
  actorRole: string
  page: string
  action: string
  entityType: string | null
  entityId: string | null
  result: UatResult
  expected: string | null
  actual: string
  expectedOutcome?: ExpectedOutcome
  actualOutcome?: ActualOutcome
  resultCode?: string
  operationType?: string
  /* Technical context when available. */
  adapter: 'demo' | 'api'
  endpoint?: string
  method?: string
  httpStatus?: number
  durationMs?: number
  errorCode?: string
  error: string | null
  /* Compact state context. */
  before?: StateDelta[]
  after?: StateDelta[]
}

export interface UatIssue {
  id: string
  ts: number
  sessionId: string | null
  severity: IssueSeverity
  category: IssueCategory
  title: string
  description: string
  expected: string
  actual: string
  page: string
  actorId: string
  actorName: string
  actorRole: string
  entityId: string | null
  mode: 'demo' | 'server'
  appVersion: string
  relatedOperation?: number | null
  recentEvents: UatEvent[]   // last N events at capture time
}

export interface UatSession {
  sessionId: string
  startedAt: number
  tester: Actor
  endedAt: number | null
  mode: 'demo' | 'server'
  appVersion: string
}

export interface UatBlob { session: UatSession | null; events: UatEvent[]; issues: UatIssue[]; notes: UatNote[]; nextExpected: ExpectedOutcome }


export interface Actor { id: string; name: string; role: string }
export type ExpectedOutcome = 'SUCCESS' | 'BLOCKED'
export type ActualOutcome = 'SUCCESS' | 'BLOCKED' | 'ERROR' | 'NO_CHANGE'
export interface UatNote { id: string; ts: number; sessionId: string; text: string; actor: Actor; page: string }
export interface OperationCapture { sessionId: string; expected: ExpectedOutcome; actor: Actor; page: string }
