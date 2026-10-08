# Operations and runtime

Canonical topic document at code baseline `f1600b580a540b55fbb8e62e1e7caa47962c313a`.
Authority: Source Code → DB/Migrations → Explicit Contracts → Graphify.
Phase-specific measurements below are historical evidence, not tests rerun by this sweep.

## Contents

- [WS1 delivery operations](#ws1-delivery-operations)

- [RUNTIME](#contract-runtime)
- [PILOT RUNBOOK](#contract-pilot-runbook)

<a id="contract-runtime"></a>
<a id="contract-runtime-runtime-integration-through-e11"></a>
## Runtime integration through E11

<a id="contract-runtime-demo-mode"></a>
### Demo mode

From the repository root, install dependencies using the repository package manifest and run `npm run dev`. Any
`VITE_CVE_DATA_MODE` value other than exactly `server` selects demo mode.
The demo uses its TypeScript reducer, seed, browser persistence and persona
switcher. It needs no backend and does not expose the entire E7–E11 API surface.

<a id="contract-runtime-server-mode"></a>
### Server mode

Follow [local PostgreSQL setup](EXTERNAL_POSTGRESQL_RUN.md), using a backend
virtual environment separate from the root Graphify `.venv`. Configure
`CVE_DATABASE_URL`, uploads, origins and authentication locally; never copy
actual credentials into tracked documentation. From `backend/`:

```sh
alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Current repository head: `ee02a1b3c402`. Reachability: `/api/health` and `/docs`.
This does not assert that a local process or temporary public tunnel is running.
Development mode may seed an empty database. For a real pilot, use
[Pilot Runbook](OPERATIONS.md#contract-pilot-runbook): non-development startup never seeds and
requires an explicit strong JWT secret. Do not run development seed/reset tools
against pilot data.

From the root, `npm run dev:server` loads the server-mode Vite configuration.
`/api` is proxied to the configured backend (`CVE_API_PROXY_TARGET`, default
`http://localhost:8000`). For a separate-origin build, configure
`VITE_API_BASE_URL` and backend CORS deliberately. No availability auto-detection
changes the chosen runtime mode.

Server mode uses real login and authoritative bootstrap/mutation responses.
The auth token storage key is `cve-token` (`src/api.ts`); browser preferences are
also local, but persisted demo domain state is not server authority. Uploads
send multipart bytes; authenticated downloads use `/api/files/{id}`.
The test-account switcher requires Vite development mode, server mode and
`VITE_CVE_DEV_TOOLS=true`; it is not a production identity mechanism.

Managed, self-hosted and headless access share the same server contracts.
See [architecture](ARCHITECTURE.md#contract-architecture) and [recorded validation](TESTING_ACCEPTANCE.md#contract-testing-readme).


<a id="contract-pilot-runbook"></a>
<a id="contract-pilot-runbook-pilot-operations--n7"></a>
## Pilot operations — N7

The pilot uses PostgreSQL, real email/password login, and an explicitly provisioned company. Startup does **not** require or create seed data. `deploy/compose.pilot.yml` is separate from the founder's local development compose file and volumes. The pilot image serves the compiled server frontend and API from one origin.

<a id="contract-pilot-runbook-first-startup-powershell-repository-root"></a>
### First startup (PowerShell, repository root)

Install Docker with Compose. Create secrets **once**, keep the file private, and retain it across updates. The file is ignored by Git. The random hex format is safe inside the database URL.

```powershell
function New-PilotSecret {
  $bytes = New-Object byte[] 32
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}
if (Test-Path -LiteralPath 'deploy/.env.pilot') { throw 'Keep the existing secrets file; do not overwrite it.' }
$pilotEnv = @("PILOT_DB_PASSWORD=$(New-PilotSecret)", "PILOT_JWT_SECRET=$(New-PilotSecret)", 'PILOT_PORT=8080')
[IO.File]::WriteAllLines((Join-Path (Get-Location) 'deploy/.env.pilot'), $pilotEnv, [Text.UTF8Encoding]::new($false))
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml up -d --build
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml logs --tail 30 app
Invoke-RestMethod http://localhost:8080/api/health
```

The app runs Alembic to revision `c71a1d902e64` before listening. On a fresh database, the company count is zero. No default login exists. `CVE_DEV_MODE=false` is explicit; a JWT secret shorter than 32 bytes or the known development secret stops startup. Port 8080 binds to localhost. For team access, put this origin behind an HTTPS reverse proxy and use its public origin when copying activation links. Do not expose a Vite development server as the pilot deployment.

<a id="contract-pilot-runbook-provision-the-company-and-initial-admin"></a>
### Provision the company and initial Admin

```powershell
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml exec app python -m app.provision_company --company 'Your Company' --admin-name 'Your Name' --admin-email 'admin@your-company.example'
```

The CLI prompts privately for a unique password and confirmation: minimum 8 characters (12 or more recommended), maximum 72 UTF-8 bytes. It prints only company ID, Admin ID, and whether it created them. Do not put passwords in shell arguments. For automation, `--password-stdin` accepts one line from a protected secret source; do not echo secrets into logs.

Provisioning creates only Company, CompanySettings, and one ADMIN User in a transaction. IDs are generated, not seed IDs. Repeating the same company name and Admin email returns the existing identity without resetting its password, onboarding state, or business data. Conflicting company/login combinations fail. Email logins are globally unique. A second company requires a different name and Admin email; run the same command with those values. Changing a company's display name later does not change its ID.

Open `http://localhost:8080` and sign in. The initial Admin lands in **Admin → Company setup**. Admins manage work and the economy but cannot own tasks or hold a participant wallet.

<a id="contract-pilot-runbook-team-setup-and-activation"></a>
### Team setup and activation

1. **Company:** verify the display name and Save.
2. **People:** add Managers or Employees with name, email, title, and capacity. Title is metadata, never a role. Additional Admin creation is not exposed by this UI.
3. **Capacity:** use the existing control; the default is 2, the range is 1–100. Admin capacity is not applicable. Lowering capacity does not unassign existing work.
4. **Reward operations:** optionally grant fulfillment capability. Admin fulfillment and the existing management fallback remain available. A starter reward is optional. To create the first reward, first add a category through **Rewards → Reward categories**, then use the normal reward form.
5. **Upload policy:** accept the defaults (10 MB/file, 25 MB total) or save the existing policy control. Readiness requires valid positive limits, no more than 100 MB/file or 500 MB total, with total at least the per-file limit.
6. **Review and ready:** inspect the counts, capacities, fulfillment holders, policy, tasks, and Coin circulation. Complete setup when blockers are clear.

Each new server account starts with login disabled. Creation displays a **single-use activation link** once; copy it and deliver it through a secure channel yourself. **No email is sent.** Links expire after 24 hours. The recipient opens the link, chooses and confirms their own password, and signs in. The link token is stored only as a SHA-256 hash on the server and is removed from the browser URL on entry. Successful activation consumes it; it cannot be used again. Passwords and activation tokens are not included in bootstrap state, business history, or UAT exports.

If a pending link expires or is lost, Admin → Company setup → People → **Issue new link** invalidates the old link and displays a new one. This is only for accounts that have never activated; N7 does not add password reset for active users or an email service. Initial Admin password recovery remains an operator responsibility; do not provision a duplicate Admin to bypass an existing account.

Non-Admins signing in before completion see a setup-in-progress message and can sign out; a reload/focus refresh after completion opens the normal workspace. This is guidance, not an additional role or business authorization model. Existing backend role and tenant checks remain authoritative.

Completion creates no tasks, rewards, coins, or notifications. No managers, employees, or rewards is a warning, not a blocker. Settings remain accessible in Admin after completion, and setup can be reopened without resetting it. Existing companies migrate to COMPLETED so they are not forced through onboarding.

<a id="contract-pilot-runbook-first-task-and-first-reward-smoke-checks"></a>
### First task and first reward smoke checks

On an isolated new company, activate at least one Employee. Complete setup with no rewards. Confirm dashboard totals are zero. As Admin, create an employee marketplace task worth 25 Coins. As Employee, claim it and submit evidence. As Admin, approve it. Confirm one 25-Coin credit, approved submission/cycle history, and no duplicate payout if approval is repeated.

As Admin, create a category and a 10-Coin reward with stock 2. As Employee, redeem it. As Admin, approve and fulfill it with a reference. Confirm FULFILLED, stock 1, and the employee's balance 15. Do not add a fake starting balance. Repeat with a second independently provisioned company and confirm neither company can see or operate on the other's IDs.

<a id="contract-pilot-runbook-backup-and-update-safety"></a>
### Backup and update safety

Back up the database and uploads together while app writes are stopped. Keep the secrets file separately in protected storage. These commands target the pilot compose project, not development. Do not use `down -v`, reseed, or clear-workspace during maintenance.

```powershell
$backupPath = Join-Path (Get-Location) ('deploy/backups/' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backupPath | Out-Null
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml stop app
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml exec -T db pg_dump -U cve -d cve_pilot -Fc -f /tmp/pilot.dump
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml cp db:/tmp/pilot.dump "$backupPath/pilot.dump"
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml run --rm --no-deps -v "${backupPath}:/backup" app tar -czf /backup/uploads.tar.gz -C /data/uploads .
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml start app
```

Check every command's exit status before proceeding. Keep backups outside the host as well. For an update, first make a verified backup, retain the previous image, and keep the existing `.env.pilot` and volumes:

```powershell
docker image tag cve-pilot-app cve-pilot-app:pre-update
git pull --ff-only
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml up -d --build app
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml logs --tail 50 app
Invoke-RestMethod http://localhost:8080/api/health
```

Repeat sign-in, dashboard, and task/reward smoke checks. The startup migration is additive and repeatable. Never downgrade schema against business data casually. To rehearse restoration, use a **separate** compose project with fresh volumes and a different `PILOT_PORT`, stop its app, copy the dump into its DB container, and run `pg_restore -U cve -d cve_pilot --clean --if-exists /tmp/pilot.dump`. Restore `uploads.tar.gz` into that project's uploads volume with the same image before starting its app. Validate IDs, balances, attachments, and logins. Only switch traffic after the restore is verified.

<a id="contract-pilot-runbook-development-remains-supported"></a>
### Development remains supported

The founder's existing local `docker-compose.yml` uses `CVE_DEV_MODE=true`; `docker compose up -d --build` starts the normal development servers. Development can seed an empty database. Never enable this mode for a pilot database. The legacy reset endpoint now works only when the sole company is the canonical development seed company; the persona list requires authentication and includes only seeded-password identities in that company. A new pilot tenant receives no demo personas, even if development mode is accidentally enabled.

The compiled pilot hides Test Lab, clear workspace, demo reset, and persona tools. Backend development endpoints are independently denied with dev mode off. Development's default known credentials are confined to seed infrastructure and are never used to provision pilot accounts.

<a id="contract-pilot-runbook-n71-account-maintenance"></a>
### N7.1 account maintenance

Admin > People > Edit changes profile, role, and active status. Capacity remains in the existing Capacity control. Deactivation preserves records and requires unfinished responsibilities to be resolved; the sole active Admin cannot be removed. Production passwords require 8 characters, with 12 or more recommended. Short development passwords require both development mode and explicit `CVE_ALLOW_WEAK_DEV_PASSWORDS=true`, plus weak-password confirmation. Never enable this exception for a pilot deployment. See [N7.1 history](HISTORY.md#early-phases) for task privacy, review delegation, debt, and the eight Founder checks.

## WS1 delivery operations

Use the backend environment (not the Graphify environment) for `python backend/scripts/deliver_notifications.py --limit 50` and `python backend/scripts/escalate_help.py --company <company-id>` from repo root. Operators schedule bounded passes; no scheduler is installed by this sweep. Delivery CLI exit 0 alone is not successful email delivery: inspect summary counts/unconfigured state and persisted rows. Empty SMTP host leaves PENDING rows; terminal FAILED remains inspectable.

Environment-backed settings: `CVE_SMTP_HOST`, `CVE_SMTP_PORT` (587 default), `CVE_SMTP_USERNAME`, `CVE_SMTP_PASSWORD`, `CVE_SMTP_FROM`, `CVE_SMTP_STARTTLS`, `CVE_PUBLIC_BASE_URL`, `CVE_HELP_ESCALATION_MINUTES` (240 default, bounded 15–10080). Keep secrets outside tracked files. Links require normal authentication and confer no approval authority.

Outbox staging is in the caller transaction alongside in-app notification state. Delivery is asynchronous and uses bounded retry/backoff (5 attempts). A crash after SMTP acceptance but before commit may resend with the same deterministic Message-ID: one logical outbox identity is not an exactly-once SMTP guarantee. The drain scans pending rows across companies and validates each recipient in its row's tenant; do not claim it has a company CLI filter. Escalation processes companies separately.

Current migration head is `ee02a1b3c402`; this describes repository migrations, not any live database. WS1 `ee01c9e2601` follows Organization and adds push/intake persistence; WS1.1 adds immutable retry receipts. Do not execute migrations or test fixtures on founder/pilot data for documentation work.

## Development reset and attachment boundaries (N6.1)

Retained operational guardrails. Later collaboration/economic history protections also apply; a development clear is never permission to erase E7 or organizational history.

## Two distinct Admin controls

**Reset demo data** retains its existing behavior: restore the original seeded
scenario. **Clear test workspace** keeps company and people but removes all
business test state. Its modal explains the deletion and requires the exact,
case-sensitive confirmation `CLEAR`. Cancel, Escape, or invalid confirmation
cannot clear data. The server independently validates the confirmation.

The clean demo helper preserves company, users, roles, positions, capacities,
fulfillment capabilities, upload settings, reward categories, notification mute
preferences and the ID sequence. It clears tasks (including nested submissions,
reviews, cycles, contributions and attachment metadata), rewards (including
executor assignments), redemptions, ledger, notifications and activity. Balances
are derived from the empty ledger, never assigned to synthetic wallet fields.

Reward categories are retained as configuration/taxonomy. Test Lab storage and
locale/direction preferences are separate and untouched. An active UAT session
records one `TEST_WORKSPACE_CLEARED` operation after the authoritative result;
existing events, issues and notes remain exportable. No business Activity event
is recreated by the clear operation. Repeated clear is safe.

## Server boundary and environment safety

`POST /api/admin/test-workspace/clear`, JSON body `{"confirmation":"CLEAR"}`.
The authenticated actor must be ADMIN. All deletion predicates use the actor's
company ID; callers cannot supply another tenant. `CVE_DEV_MODE=true` must be
explicitly configured. The historical implicit default of True is insufficient
for this destructive endpoint; false or omitted configuration refuses it.

Frontend controls are restricted to Admin in Vite development mode. Server
development additionally requires the existing `VITE_CVE_DEV_TOOLS=true` flag.
Demo development is the existing local test environment. Both production builds
hide the new control. No new overlapping environment flags were added.

The reset service uses one PostgreSQL transaction and explicit dependency-ordered,
tenant-scoped deletes. It removes Attachment, Contribution, TaskCycle, Submission,
RewardExecutor, Redemption, LedgerTransaction, Notification, Activity, Task and
Reward rows. It preserves Company, User, CompanySettings and RewardCategory.
Reviews are fields on submission records; transitions are activity/cycle records.
That list describes the legacy reset scope, not the current complete schema. Later E7, collaboration and organization history adds refusal boundaries; inspect the current reset guards before using this development operation.

Short-lived table locks prevent concurrent writes from crossing the clear boundary.
They can briefly delay another tenant's writes, but never delete its rows. Any SQL,
serialization or commit failure rolls back the entire clear. Constraints remain
enabled. No TRUNCATE, schema reset, migration execution or reset-tracking table is
used. A cleared company survives application restart without reseeding because
the existing seed guard checks company existence.

## Attachment handling

Real attachments are local files with DB metadata. Before deletion, all paths are
resolved and checked inside the authenticated tenant's directory. No bytes move
before the database commits: rollback or a process crash during the transaction
cannot leave live metadata referencing a removed file. After commit, unreferenced
files move on the same filesystem into a unique `.workspace-clear` quarantine and
are deleted. A cleanup failure is logged; remaining original or quarantined bytes
are unservable because their authenticated attachment metadata no longer exists.
Operators may remove these unreferenced leftovers after checking metadata. Missing
files are tolerated; paths outside the tenant are refused before any deletion.
There is no new durable background cleanup subsystem.

## Account synchronization and presentation integrity (N7.1)

Retained security requirements; current Task authority is documented in TASK_LITE rather than the older N7.1 role assumptions.

## Accounts and synchronization

Admin → People → Edit changes name, position, role, and active status. Capacity remains in the existing capacity control; fulfillment permission remains separate from the system role. Deactivation retains history and requires cleanup of owned work, pending direct assignments, executor seats, and pending/approved redemptions. The last active Admin cannot be removed. Inactive and activation-pending people cannot sign in, receive assignments, or appear in the dev switcher.

Development switching uses an authenticated, tenant-scoped token exchange and lists all eligible active accounts. It never distributes passwords. Each browser tab binds requests to its current authenticated session. Cross-tab token changes reset identity and state together; old queued requests and responses cannot apply to the new account. Refusals trigger an authoritative refresh and a localized error without changing Test Lab expectations.

Production passwords require at least 8 characters; 12 or more is recommended. The strength meter is guidance. Six- or seven-character passwords are accepted only when both development mode and `CVE_ALLOW_WEAK_DEV_PASSWORDS=true` are explicitly enabled, and weak development passwords require confirmation. Passwords never enter business history or UAT exports.

## Presentation

Task text preserves paragraphs, lists, indentation, and safe links. Task history and cycles sort newest first, with stable ID ordering for equal timestamps. Notifications sound only for new actionable or important notices after interaction; initial history stays silent, bursts are throttled, and each account can mute sound.

Errors use localized semantic messages, remain for ten seconds, pause while hovered or focused, and can be closed above an open drawer. Cancellation history preserves the cancelling actor's name, time, and reason even after profile edits. Dashboard actions have keyboard focus and hover feedback; static metrics remain static.

## Backend and migration

Migration `c71a1d902e64` follows `b72e4d1f8307`. It adds user active status, task viewer/reviewer grants, historical sensitivity, private worker role, and cancellation snapshots. It derives metadata from existing structured history without altering ledger entries, task cycles, authored content, or activity. Historical cancellation attribution is backfilled from the recorded event rather than a user's current name.

New endpoints are `PUT /api/tasks/{id}/access`, `PATCH /api/users/{id}`, `POST /api/dev/switch/{id}`, and `GET /api/auth/password-policy`. Existing routing endpoints accept sensitivity confirmation. New events are `TASK_ACCESS_UPDATED`, `TASK_AUDIENCE_CONFIRMED`, `USER_UPDATED`, `USER_DEACTIVATED`, and `USER_REACTIVATED`.

Backend services are split into task operations, task cycles, rewards, shared operations, access, audience guards, and account lifecycle modules. Authentication routes are separate. Frontend actions, reward transitions, integrity rules, request mapping, and task history are extracted from their larger parent files.
