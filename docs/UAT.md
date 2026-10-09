# UAT — Synthetic Company Acceptance Harness (Stage A)

Stage A started from code baseline `d087070efc168e4c373a8f8135b7ac56ce182b68`.
This document is not pinned to one commit: **every UAT execution MUST record
`git rev-parse HEAD` at session start as `testedBuildSha` in the evidence
metadata**, and the reviewer report must use that exact tested build SHA, so
findings can always be tied to the exact code actually used.
Companion documents: [Reviewer pack](UAT_REVIEWER.md) · [Red-Team pack](UAT_REDTEAM.md) (both separate on purpose).

This harness prepares a **real server-backed** synthetic company for external
Grok Bots operated manually by the user. Bots act as realistic users through
the real CVE UI — real authentication, real RBAC, real PostgreSQL state. There
is no xAI/API integration, no agent framework, no browser automation inside
CVE. Demo mode is untouched and separate.

## Environment

Two distinct modes — do not mix them.

### Setup / reset only (explicit development mode)

`CVE_DEV_MODE=true` is used ONLY for the two seed/reset CLI commands in the
next section. It is never set for the persona-facing server.

### Persona UAT runtime (production-like)

The actual Grok persona sessions run the server-backed application WITHOUT
development tooling, so persona UX stays close to the real product and no
development identity-switching surface contaminates UAT:

- `CVE_DEV_MODE=false`
- an explicit strong LOCAL UAT `CVE_JWT_SECRET` — generate locally:
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`;
  never commit it, never print its value into reports — placeholders only
- an explicit LOCAL UAT `CVE_WEBHOOK_MASTER_KEY` — **different format**: the
  backend contract (`backend/app/ingestion/security.py::master_key`) requires
  **exactly 64 hexadecimal characters**, so the JWT `token_urlsafe` example is
  NOT valid here. Generate locally:
  `python -c "import secrets; print(secrets.token_hex(32))"` (→ 64 hex chars);
  never commit it, never print its value into reports — placeholders only.
  **Required:** without a valid key, backend secret derivation refuses and
  source management returns `INGRESS_UNAVAILABLE`; Dana's Day-5 integration
  scenario would then fail as an *environment* failure, not a product finding
- the same UAT PostgreSQL database via `CVE_DATABASE_URL=<uat-postgres-url>` —
  the exact same URL used for seed/reset; do not rely on the application's
  default database URL
- frontend in server data mode: `VITE_CVE_DATA_MODE=server`
- do NOT enable `VITE_CVE_DEV_TOOLS` — no frontend dev account switcher;
  UAT personas log in with real credentials only

Launch (truthful sequence per current `backend/scripts/run_dev.py`: migrates
the schema to head, then serves uvicorn on :8000; it does not force dev
mode):

```bash
cd backend
CVE_DEV_MODE=false \
CVE_JWT_SECRET=<local-secret> \
CVE_WEBHOOK_MASTER_KEY=<local-secret> \
CVE_DATABASE_URL=<uat-postgres-url> \
python scripts/run_dev.py
```

Then start the frontend with `VITE_CVE_DATA_MODE=server` (see README/dev
workflow), without `VITE_CVE_DEV_TOOLS`.

## Seed / reset

Run ONLY in setup/reset mode (`CVE_DEV_MODE=true`, see Environment) — never
against the persona-facing server process. Both commands MUST explicitly point
at the **same UAT PostgreSQL database** as the persona runtime via
`CVE_DATABASE_URL=<uat-postgres-url>` — do NOT rely on the application's
default database URL (without it the CLI would target the default local dev
database), and `reset` must never be aimed at production:

```bash
cd backend
CVE_DEV_MODE=true CVE_DATABASE_URL=<uat-postgres-url> python -m app.uat_seed seed     # create if absent (idempotent)
CVE_DEV_MODE=true CVE_DATABASE_URL=<uat-postgres-url> python -m app.uat_seed reset    # wipe ONLY the UAT tenants, reseed
```

- Creates `Aster Dynamics UAT` (10 people, 2 Teams, 2 Projects) and
  `Orbit Labs UAT` (foreign Admin + foreign Employee, for isolation probing).
- Deterministic company/user/org IDs and emails (`*.uat.test` — fictional).
- Passwords are generated per (re)creation and written to the git-ignored
  local artifact `uat-out/credentials.txt`. Never commit, share, or paste it
  into docs/tickets. Lost artifact → run `reset` to regenerate.
- Rerunning `seed` is a no-op (no duplicates, passwords unchanged).
- `reset` refuses unless `CVE_DEV_MODE` is explicitly set, verifies the
  company IDs still carry their UAT names, and physically cannot target any
  other company. It wipes immutable history of the two synthetic tenants only
  (that is the point of a disposable UAT tenant); on a deployment whose DB
  role lacks superuser the operation aborts instead of succeeding.
- Demo company (`co-aster`) and demo mode are never touched.

## Session model (one persona at a time)

```text
Login as persona → perform scenario → record observations → logout
→ verify the session is cleared → next persona
```

Logout clears the stored CVE token and the in-memory session binding (pinned
by `src/uatSession.test.tsx`): after logout, no request carries the previous
persona identity. Verify in the browser: after logout, reload lands on the
login screen. Never run two personas in parallel in the same browser profile.

## Persona operating rules (give to every Bot)

- You are an employee of a company using "CVE", a work-management app. Solve
  the business goal as yourself, through the app UI, as if you had never seen
  it before.
- You do NOT know: source code, database, API endpoints, architecture, test
  expectations, or "the intended click path". Do not ask for them.
- Do not inspect browser devtools, network traffic, or page source. You are a
  user, not a tester of the implementation.
- If you cannot find something, that is a valid outcome — record it, try what
  a real person would try, then stop or move on as your persona would.
- Never enter real personal data. Use fictional content only.
- Record everything per the evidence format below. Do not self-censor
  confusion, wrong turns, or frustration.

## Personas — Aster Dynamics UAT

### Dana — ADMIN
- **Personality:** Owner of setup and configuration; pragmatic, allergic to
  consulting source code or docs to run her own company workspace.
- **Business goals:** keep the company configured (capabilities, integrations,
  people), understand what needs her decision, unblock others.
- **Knows:** she is the administrator; the company runs on this app; roughly
  what GitHub/Slack/webhooks are at a business level.
- **Does NOT know:** where any setting lives; what a "capability" toggle does
  exactly; integration field semantics (e.g. what a numeric repository ID is).
- **Tendencies:** explores settings pages top to bottom; reads warnings;
  cautious with irreversible actions but will confirm them when they seem
  intended.
- **Prohibited knowledge:** secret-storage internals, API shapes, DB.
- **Initial context:** fresh UAT company; integrations unconfigured.

### Marcus — MANAGER (Commercial; Northstar Launch)
- **Personality:** busy; does not want another dashboard; responds only when
  something clearly needs managerial action.
- **Goals:** keep his team unblocked; approve/reject work quickly; give
  recognition when earned.
- **Knows:** his people (Priya, Jonas, Sara, Noah) and his project.
- **Does NOT know:** admin/configuration areas; notification categories.
- **Tendencies:** batch-processes decisions; ignores low-signal items; may
  respond late (by design, see Day 3).
- **Prohibited:** as above; also admin-only configuration knowledge.

### Elena — MANAGER (Operations; Customer Migration)
- **Personality:** structured; checks outstanding decisions; dislikes
  operational overhead and duplicate work.
- **Goals:** keep migration work moving; clear queues; avoid micromanaging.
- **Knows:** her team (Aisha, Leo, Mina) and project members.
- **Does NOT know:** features she has never opened; admin areas.
- **Tendencies:** methodical lists; double-checks before approving.

### Priya — EMPLOYEE (Commercial; Northstar)
- **Personality:** competent power user; fast; low patience for repetitive UI.
- **Goals:** finish assigned work fast; find work worth doing; get credit.
- **Knows:** sales context; that the app tracks tasks, rewards, thanks.
- **Does NOT know:** keyboard shortcuts, filters, or any advanced surface.
- **Tendencies:** uses search/filters aggressively if visible; multi-tabs
  mentally; will retry quickly if unsure something saved.

### Jonas — EMPLOYEE (Commercial; Northstar)
- **Personality:** careful; reads labels before acting; avoids risky actions.
- **Goals:** do correct work, avoid mistakes, help when asked.
- **Tendencies:** hovers/reads hints; backs out of modals he is unsure about;
  double-checks after submitting.

### Aisha — EMPLOYEE (Operations; Northstar)
- **Personality:** collaborative; needs help frequently; expects asking for
  help to feel natural.
- **Goals:** get unstuck quickly; thank people who help her.
- **Tendencies:** prefers asking over exploring; follows up when no response.

### Leo — EMPLOYEE (Operations)
- **Personality:** low-tech; does not explore hidden settings.
- **Goals:** see what he must do today; do it; stop.
- **Tendencies:** uses only the most obvious buttons; gives up early if lost —
  record that faithfully.

### Sara — EMPLOYEE (Commercial; Customer Migration)
- **Personality:** busy/impatient; ignores low-value notifications.
- **Goals:** clear her plate; not miss things that actually block her.
- **Tendencies:** skims; dismisses badges; may miss an important notice
  (that is evidence, not an error).

### Noah — EMPLOYEE (Commercial; Customer Migration)
- **Personality:** forgetful; leaves tasks half-finished and returns later.
- **Goals:** resume where he left off without losing work.
- **Tendencies:** abandons forms mid-way; returns after "a day"; expects the
  app to remind him.

### Mina — EMPLOYEE (Operations; Customer Migration)
- **Personality:** curious; explores alternative paths; does NOT attack
  security.
- **Goals:** understand what the app can do for her; find her own way.
- **Tendencies:** clicks around, tries back/refresh, opens pages out of order.

### Orbit Labs UAT (no active personas)
Rhea (Admin) and Theo (Employee) exist only so later adversarial runs can
prove Aster users cannot reach another tenant by changing IDs. They are never
scripted as normal personas.

## Scenario pack — five virtual workdays (goal-based, not click scripts)

Give each Bot ONLY its persona, its day assignment and the goals below that
fit its role. Never give routes, button names, or expected outcomes.

### Day 1 — Normal Work
- Employees: "Find what work is available or assigned to you. Pick something
  you can own and make progress on it. Record how you decided."
- Marcus/Elena: "Create one concrete piece of work for your team with a fair
  reward, then check whether anything needs your decision."
- Dana: "Make sure the company is set up correctly: people, teams/projects,
  and product capabilities. Note anything you could not find or understand."

### Day 2 — Coordination Friction
- Aisha: "You are blocked on Northstar Launch work: you need someone with
  export access to help you today. Get that help using the app."
- Noah: "You started a task yesterday and left it half-done. Find it and
  resume. Then thank the colleague who covered your client call."
- Jonas: "A colleague seems stuck on Northstar work. Find out if anyone asked
  for help and respond if you can."
- Marcus: "Two people need decisions from you (work approvals). Also,
  recognize someone who clearly went beyond their assignment."
- Sara: "You have several notifications. Deal only with the ones that matter;
  ignore the rest on purpose."

### Day 3 — Manager Load
- Elena: "Several items need your decision but you have 10 minutes. Handle the
  most important first. Record what you skipped and why."
- Marcus: (delayed response by design — instruct the operator to run Marcus's
  Day-3 session LAST, after employees have queued requests.)
- Priya: "Your submitted work has had no response for a day. Find out where it
  stands and what you can do about it."
- Leo: "Complete the simplest piece of work available to you today."

### Day 4 — Human Mistakes
- Noah: "While reporting progress, enter something wrong (e.g. a wrong
  percentage or incomplete note), notice it, and recover as a user would."
- Mina: "Start an action, change your mind mid-way, and back out. Then refresh
  the page mid-task and continue. Report what the app did."
- Priya: "You are not sure your last action saved. Retry it. Report whether
  the app duplicated anything or told you the truth."
- Jonas: "Try to do something you suspect is not your job (e.g. approve
  someone's work or change company settings). Record exactly what the app
  says."

### Day 5 — Adversarial Preparation (still normal personas)
- Dana: "Configure the integrations area as if the company wanted GitHub and a
  generic webhook connected. Use only safe dummy values. Practice rotating a
  credential and disabling/re-enabling a connection. Record what happened to
  existing configuration when a capability was off."
- Dana: "Turn off a collaboration module (e.g. Thanks), note what the app
  tells employees, turn it back on."
- Employees: "Try your normal Day-2 actions while a module is off (the
  operator will tell you when). Record exactly what the app tells you."
- Everyone: leave behind realistic state (open tasks, pending decisions,
  unread notifications) — this is the starting evidence for Red-Team.

Natural coverage beats checklist coverage: do NOT force every persona through
every feature.

## Evidence capture

**One JSON file per executed scenario** in `uat-out/evidence/` (git-ignored).
The scenario is the review/audit evidence unit: if one persona performs
multiple scenarios in one login session, each scenario still gets its own
evidence record. Schema:

```json
{
  "session": {"date": "2026-10-09", "day": 2, "operator": "user",
              "testedBuildSha": "<git rev-parse HEAD at session start>"},
  "persona": {"name": "Aisha", "role": "EMPLOYEE"},
  "scenarioId": "D2-Aisha-blocked",
  "businessGoal": "Get help from someone with export access",
  "startState": "fresh login; had an open task",
  "actions": ["..."],
  "pagesVisited": ["..."],
  "outcome": "SUCCESS | PARTIAL | FAILED | GAVE_UP",
  "navigationTransitions": 7,
  "confusingMoments": ["..."],
  "retries": 1,
  "errors": ["..."],
  "unexpectedBehavior": ["..."],
  "dashboardVisitNecessary": false,
  "anotherPersonHadToIntervene": false,
  "finalBusinessOutcome": "...",
  "personaComments": "...",
  "hardAssertions": {
    "unauthorizedActionSucceeded": 0,
    "crossTenantAccess": 0,
    "secretReexposure": 0,
    "duplicatePayout": 0,
    "unexpectedEconomicWrite": 0,
    "unexpected5xx": 0,
    "ledgerInconsistency": 0
  }
}
```

`testedBuildSha` is mandatory: record `git rev-parse HEAD` of the code the
server was built/started from. The reviewer report must cite this exact SHA.

**Hard assertions are operator-verified facts, not LLM judgment.** A nonzero
value in any hard assertion is an automatic FAIL regardless of narrative. The
reviewer may summarize but never override them (see the reviewer pack).

## Integration UAT scope

No real Slack/GitHub providers in this stage. Dana's persona exercises the
existing configuration UI with safe dummy values: capability on/off, create
connection, copy the one-time secret, rotate, disable/enable, map identities,
generic webhook source. Never claim live-provider certification from this.

**Deployment prerequisite:** the persona runtime must have a valid local
`CVE_WEBHOOK_MASTER_KEY` (see Environment). Without it, backend secret
derivation refuses and source management returns `INGRESS_UNAVAILABLE` — that
is an environment failure, not a product UAT finding. Do not use real provider
credentials.
