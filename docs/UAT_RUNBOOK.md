# Synthetic Company UAT — Operator Runbook

> Execution runbook for the manually-operated Grok Bot UAT campaign.
> Contracts: [UAT.md](UAT.md) (personas, evidence schema) ·
> [UAT_REVIEWER.md](UAT_REVIEWER.md) · [UAT_REDTEAM.md](UAT_REDTEAM.md)
> (Red-Team is a separate later stage — do NOT run it now).
> Source remains authoritative if any document disagrees.
> Prepared and smoke-checked against testedBuildSha
> `1d2c1026e60f8a1f031644b31bf6be25e7b59e95`.

Everything runs locally. Four terminals, all in Git Bash from the repository
root unless noted. No secrets or passwords ever appear in docs, chat, or
reports — they live only in the git-ignored `uat-out/` artifacts.

---

## 1. UAT database (clean preparation)

The UAT database is a **dedicated, disposable PostgreSQL cluster** using the
repository's existing tooling (`pgserver`, the same user-space PostgreSQL
`backend/scripts/run_dev.py` uses):

- cluster data dir: `%TEMP%\cve-uat-pg` (Windows temp — local, disposable)
- database: **`cve_uat`** — created empty, used for nothing else
- it is NOT the dev default (`cve`), NOT the test DB (`cve_test`), NOT the
  demo dataset, and NEVER production

`pgserver` stops when its owning process stops, so one terminal must hold the
database open for the whole session. A small git-ignored keeper artifact was
prepared during environment prep: `uat-out/uat_db_keeper.py`. It starts the
cluster, creates `cve_uat` if missing, refreshes `uat-out/uat-env.local` with
the current connection URL (existing secrets are preserved), then holds.

**Terminal 1 — database keeper (leave running all session):**

```bash
./.venv/Scripts/python.exe uat-out/uat_db_keeper.py
```

The canonical placeholder `<uat-postgres-url>` below means: the
`CVE_DATABASE_URL` line that the keeper wrote into `uat-out/uat-env.local`.
The port changes each time the keeper restarts — always re-source the env
file in a fresh terminal after a keeper restart. Data persists across keeper
restarts; to discard everything, stop the keeper and delete `%TEMP%\cve-uat-pg`.

## 2. Local UAT secrets

Generated during prep into `uat-out/uat-env.local` (git-ignored). To regenerate
manually — two DIFFERENT formats:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"   # CVE_JWT_SECRET
python -c "import secrets; print(secrets.token_hex(32))"       # CVE_WEBHOOK_MASTER_KEY — MUST be exactly 64 hex chars
```

Never commit these values; never paste them into reports or chat.

## 3. Seed / reset

Order matters: the backend's first launch migrates the schema to head, so
start the backend (section 5) once BEFORE the first seed.

**Terminal 3 — seed/reset (the only place `CVE_DEV_MODE=true` is used):**

```bash
cd backend
set -a; . ../uat-out/uat-env.local; set +a          # = CVE_DATABASE_URL=<uat-postgres-url> + secrets
CVE_DEV_MODE=true ../.venv/Scripts/python.exe -m app.uat_seed seed     # first time: create if absent (idempotent)
CVE_DEV_MODE=true ../.venv/Scripts/python.exe -m app.uat_seed reset    # fresh campaign: wipe ONLY the UAT tenants, reseed
```

Truthful distinction: `seed` creates missing tenants and is a no-op otherwise
(passwords unchanged); `reset` wipes the two UAT tenants (including immutable
history) and reseeds with NEW passwords. `reset` also works from empty.
Never aim either at any other database URL — the guards (explicit dev mode,
hardcoded `co-uat-aster`/`co-uat-orbit`, name check, superuser-only session
flag) are defense-in-depth, not permission.

Do NOT reset between personas or virtual days — the shared evolving company
state is the point. Reset only before a fresh campaign or when instructed.

After seeding, confirm the credential artifact:

- `uat-out/credentials.txt` exists (repo root)
- `git check-ignore uat-out/credentials.txt` confirms it is git-ignored
- it lists 10 Aster Dynamics UAT + 2 Orbit Labs UAT accounts
- do NOT print or share its contents

## 4. Tested build identity

Immediately before persona execution:

```bash
git rev-parse HEAD
```

Expected: `1d2c1026e60f8a1f031644b31bf6be25e7b59e95` — record it as
`testedBuildSha` in EVERY evidence record. If HEAD changes at any point:
STOP the UAT; never mix evidence from different builds.

## 5. Backend launch (persona runtime — production-like)

**Terminal 2 (leave running):**

```bash
cd backend
set -a; . ../uat-out/uat-env.local; set +a
CVE_DEV_MODE=false \
CVE_PORT=8011 \
CVE_UPLOAD_DIR="$TEMP/cve-uat-uploads" \
../.venv/Scripts/python.exe scripts/run_dev.py
```

`run_dev.py` migrates the schema to head, then serves uvicorn on
`http://127.0.0.1:8011`. With `CVE_DEV_MODE=false` the server refuses to start
without a strong `CVE_JWT_SECRET` (lifespan check) and never seeds demo data.
Verify once: `curl http://127.0.0.1:8011/api/health` → HTTP 200.

## 6. Frontend launch

**Terminal 4 (leave running):**

```bash
VITE_CVE_DATA_MODE=server \
CVE_API_PROXY_TARGET=http://127.0.0.1:8011 \
npm run dev -- --port 8173 --strictPort --host 127.0.0.1
```

Notes verified on this machine:

- do NOT use `npm run dev:server` — it loads `.env.server`, which sets
  `VITE_CVE_DEV_TOOLS=true` and would surface the dev account switcher.
  Setting `VITE_CVE_DATA_MODE=server` explicitly with plain `npm run dev`
  keeps dev tools off (`VITE_CVE_DEV_TOOLS` stays unset).
- `--host 127.0.0.1` and an explicit free port are needed on Windows:
  vite's default bind (`::1`) and several common ports (5173, 7100) were
  blocked/unreachable here; `8173` worked. If `8173` is busy, pick another
  and use it consistently everywhere (including the tunnel, section 7).
- `CVE_API_PROXY_TARGET` must be `http://127.0.0.1:8011` (IPv4 literal),
  not `localhost`.

The app is at `http://127.0.0.1:8173/`. All `/api` calls are proxied
same-origin to the backend.

## 7. Grok access (only if needed)

If the Grok Bots operate on THIS machine (you drive the browser and relay the
bot's actions), no tunnel is needed — use `http://127.0.0.1:8173/` directly
and skip this section.

If the bots are cloud-based and must browse the app themselves, localhost is
unreachable to them. The smallest compatible method (the project has used
Cloudflare Tunnel for webhook testing before):

```bash
cloudflared tunnel --url http://127.0.0.1:8173
```

- exposes ONLY the vite frontend port; `/api` rides the same origin through
  vite's proxy, so the backend and PostgreSQL stay unexposed
- `cloudflared` is not currently installed on this machine
  (`winget install cloudflare.cloudflared` if you choose this route)
- the random `*.trycloudflare.com` URL is session-local: share it only with
  the bots, never commit it, and stop the tunnel (Ctrl+C) when the session ends
- no developer consoles, no secrets, no production infrastructure

## 8. Environment smoke check (before ANY Grok persona)

Already executed against the prepared environment — ALL PASS:

| Check | Result |
|---|---|
| `cve_uat` on dedicated disposable cluster | PASS |
| migrations reach head | PASS |
| `uat_seed` CLI seeds; credentials artifact has 10 Aster + 2 Orbit accounts | PASS |
| backend `/api/health` with `CVE_DEV_MODE=false` (strong-JWT lifespan gate active) | PASS |
| frontend serves in server mode without dev tools | PASS |
| Dana (Admin) login; identity ADMIN @ `co-uat-aster` | PASS |
| Dana's bootstrap shows Aster Dynamics UAT only | PASS |
| Priya (Employee) login | PASS |
| Orbit account sees only Orbit Labs UAT (users: Rhea, Theo) | PASS |
| wrong password → uniform 401 | PASS |
| no demo company (`co-aster`) in the UAT DB | PASS |
| frontend reaches real backend through the `/api` proxy | PASS |

Remaining manual confirmations in the browser (30 seconds, environment check
only — not UAT): the login page appears; no demo banner; no dev account
switcher; logout returns to the login screen. If any of these fail → STOP
conditions apply. Do not explore features or fix anything.

## 9. Persona session order — Day 1

ONE persona at a time; never parallel Grok sessions in the same browser
environment; full logout protocol (section 11) between personas.

| Order | Persona | Role | Scenario ID | Dependency |
|---|---|---|---|---|
| 1 | Dana | ADMIN | D1-Dana-setup | none — goes first |
| 2 | Marcus | MANAGER | D1-Marcus-create-work | after Dana |
| 3 | Elena | MANAGER | D1-Elena-create-work | after Dana |
| 4 | Priya | EMPLOYEE | D1-Priya-normal-work | after Marcus (Northstar work exists) |
| 5 | Jonas | EMPLOYEE | D1-Jonas-normal-work | after Marcus |
| 6 | Aisha | EMPLOYEE | D1-Aisha-normal-work | after Marcus (Northstar) |
| 7 | Leo | EMPLOYEE | D1-Leo-normal-work | after Elena (Operations) |
| 8 | Sara | EMPLOYEE | D1-Sara-normal-work | after Elena (Customer Migration) |
| 9 | Noah | EMPLOYEE | D1-Noah-normal-work | after Elena |
| 10 | Mina | EMPLOYEE | D1-Mina-normal-work | after Elena |

Later days (preserve dependencies from `docs/UAT.md`):

- Day 2: Aisha BEFORE Jonas (his goal is to find her help request).
- Day 3: Marcus executes LAST (delayed response is by design).
- Day 5: operator coordinates — Dana disables the module first, employees try
  while it is off, Dana re-enables. Integration configuration uses dummy
  values only and needs the valid local `CVE_WEBHOOK_MASTER_KEY` (already set).

## 10. Grok persona prompt format — Day 1

Give each Bot ONLY its block below. Never add routes, button names, feature
checklists, expected results, source code, endpoints, or architecture.
The Bot is a user, not a tester of the implementation.

Shared rules appended to every prompt:

```text
Rules:
- Act as yourself through the CVE web app UI, like a real first-time user.
- Do not inspect browser devtools, network traffic, or page source.
- If you cannot find something, say so — that is a valid result. Try what a
  real person would try, then stop or move on as you would.
- Use only fictional content; never real personal data.
- When finished, report as JSON with exactly these fields: actions (ordered
  list), pagesVisited, outcome (SUCCESS | PARTIAL | FAILED | GAVE_UP),
  navigationTransitions (count of major page changes), confusingMoments,
  retries, errors, unexpectedBehavior, dashboardVisitNecessary (true/false),
  anotherPersonHadToIntervene (true/false), finalBusinessOutcome,
  personaComments (in character).
```

### 1 — Dana (Admin)

```text
You are Dana, Operations Director at Aster Dynamics, a small company that runs
its work on an app called "CVE". You are the company administrator. You are
pragmatic and allergic to consulting manuals or technical people to run your
own company's workspace. You know the company runs on this app and roughly
what GitHub/Slack/webhooks are at a business level. You do NOT know where any
setting lives or what a "capability" toggle does exactly. You explore settings
pages top to bottom, you read warnings, and you are cautious with irreversible
actions but will confirm them when they seem intended.

Your goal today: make sure the company is set up correctly — people,
teams/projects, and product capabilities. Note anything you could not find or
understand.
```

### 2 — Marcus (Manager)

```text
You are Marcus, Commercial Team Lead at Aster Dynamics. You manage Priya,
Jonas, Sara and Noah, and the "Northstar Launch" project. You are busy and do
not want another dashboard; you respond only when something clearly needs
managerial action. You do not know admin/configuration areas.

Your goal today: create one concrete piece of work for your team with a fair
reward, then check whether anything needs your decision.
```

### 3 — Elena (Manager)

```text
You are Elena, Operations Team Lead at Aster Dynamics. You manage Aisha, Leo
and Mina, and the "Customer Migration" project. You are structured, you check
outstanding decisions, and you dislike operational overhead and duplicate work.
You do not know admin areas or features you have never opened.

Your goal today: create one concrete piece of work for your team with a fair
reward, then check whether anything needs your decision.
```

### 4 — Priya (Employee)

```text
You are Priya, Account Executive at Aster Dynamics (Commercial team, Northstar
Launch project). You are a competent power user: fast, with low patience for
repetitive UI. You know the app tracks tasks, rewards and thanks. You do not
know keyboard shortcuts, filters, or any advanced surface. If you are unsure
something saved, you retry quickly.

Your goal today: find what work is available or assigned to you. Pick
something you can own and make progress on it. Record how you decided.
```

### 5 — Jonas (Employee)

```text
You are Jonas, Field Coordinator at Aster Dynamics (Commercial team, Northstar
Launch project). You are careful: you read labels before acting and avoid
risky actions. You hover over hints, back out of modals you are unsure about,
and double-check after submitting.

Your goal today: find what work is available or assigned to you. Pick
something you can own and make progress on it. Record how you decided.
```

### 6 — Aisha (Employee)

```text
You are Aisha, Business Analyst at Aster Dynamics (Operations team, Northstar
Launch project). You are collaborative, you need help fairly often, and you
expect asking for help to feel natural. You prefer asking over exploring, and
you follow up when no one responds.

Your goal today: find what work is available or assigned to you. Pick
something you can own and make progress on it. Record how you decided.
```

### 7 — Leo (Employee)

```text
You are Leo, Support Specialist at Aster Dynamics (Operations team). You are
not technical and do not explore hidden settings. You use only the most
obvious buttons, and you give up early if you get lost — if that happens, say
so honestly.

Your goal today: see what you must do today, do it, and stop.
```

### 8 — Sara (Employee)

```text
You are Sara, Sales Associate at Aster Dynamics (Commercial team, Customer
Migration project). You are busy and impatient. You skim, you dismiss badges,
and you ignore low-value notifications on purpose.

Your goal today: find what work is available or assigned to you. Pick
something you can own and make progress on it. Record how you decided.
```

### 9 — Noah (Employee)

```text
You are Noah, Implementation Associate at Aster Dynamics (Commercial team,
Customer Migration project). You are forgetful: you leave tasks half-finished
and come back later. You abandon forms mid-way and expect the app to help you
resume.

Your goal today: find what work is available or assigned to you. Pick
something you can own and make progress on it. Record how you decided.
```

### 10 — Mina (Employee)

```text
You are Mina, Operations Analyst at Aster Dynamics (Operations team, Customer
Migration project). You are curious: you click around, try the browser
back/refresh buttons, and open pages out of order to find your own way. You
never try to break security or access other people's accounts.

Your goal today: find what work is available or assigned to you. Pick
something you can own and make progress on it. Record how you decided.
```

## 11. Session isolation protocol (between EVERY persona)

1. Persona finishes the scenario.
2. Save the evidence record (section 12).
3. Click Logout in the app.
4. Verify the login screen appears.
5. Reload the page; verify you are STILL logged out.
6. Only then enter the next persona's credentials.

Never use the dev persona switcher (it is off — if you see it, STOP).
Never give one Grok Bot another persona's password.

## 12. Evidence collection

One JSON file per executed scenario:
`uat-out/evidence/<persona>__<scenarioId>__<YYYY-MM-DD>.json`
(create the directory once: `mkdir -p uat-out/evidence`).

Procedure per scenario:

1. Operator records `git rev-parse HEAD` once per day → `testedBuildSha`.
2. The Bot returns its structured report (fields per section 10).
3. The operator wraps it into the canonical schema from `docs/UAT.md`
   §Evidence capture: adds `session` (date, day, operator, testedBuildSha),
   `persona` (name, role), `scenarioId`, `businessGoal`, `startState`.
4. **`hardAssertions` are filled/verified by the OPERATOR from observable
   facts only** (what the server actually did) — never from the Bot's claims
   or guesses. If a class of assertion was not exercised by the scenario, the
   counters stay 0 and the missing coverage is noted for the reviewer (do not
   fake evidence).
5. No validator tooling exists; validate by hand against the schema (any JSON
   validator is fine). `uat-out/` is git-ignored — evidence never enters git.

## 13. STOP conditions

STOP persona execution immediately if any of these happen:

- wrong company/tenant appears;
- a previous persona remains logged in;
- demo data appears;
- the dev account switcher appears;
- unexpected 5xx blocks normal use;
- the UAT DB connection changes (keeper restarted → re-source env);
- `git rev-parse HEAD` changes;
- the credential file is missing/inconsistent;
- the product needs a code modification to continue;
- any security/economic hard assertion becomes non-zero.

Do NOT patch anything while UAT is running. Record the evidence and return
for triage.

## 14. What this campaign is NOT

- Not Red-Team (`docs/UAT_REDTEAM.md` is a separate, later, signed-off stage).
- Not a bug-fixing phase — no UAT-driven product changes.
- Not automated: no browser automation, no xAI/API integration, no agent
  orchestration inside CVE.
