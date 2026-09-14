# Pilot operations — N7

The pilot uses PostgreSQL, real email/password login, and an explicitly provisioned company. Startup does **not** require or create seed data. `deploy/compose.pilot.yml` is separate from the founder's local development compose file and volumes. The pilot image serves the compiled server frontend and API from one origin.

## First startup (PowerShell, repository root)

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

The app runs Alembic to revision `b72e4d1f8307` before listening. On a fresh database, the company count is zero. No default login exists. `CVE_DEV_MODE=false` is explicit; a JWT secret shorter than 32 bytes or the known development secret stops startup. Port 8080 binds to localhost. For team access, put this origin behind an HTTPS reverse proxy and use its public origin when copying activation links. Do not expose a Vite development server as the pilot deployment.

## Provision the company and initial Admin

```powershell
docker compose --env-file deploy/.env.pilot -f deploy/compose.pilot.yml exec app python -m app.provision_company --company 'Your Company' --admin-name 'Your Name' --admin-email 'admin@your-company.example'
```

The CLI prompts privately for a unique password and confirmation: minimum 12 characters, maximum 72 UTF-8 bytes. It prints only company ID, Admin ID, and whether it created them. Do not put passwords in shell arguments. For automation, `--password-stdin` accepts one line from a protected secret source; do not echo secrets into logs.

Provisioning creates only Company, CompanySettings, and one ADMIN User in a transaction. IDs are generated, not seed IDs. Repeating the same company name and Admin email returns the existing identity without resetting its password, onboarding state, or business data. Conflicting company/login combinations fail. Email logins are globally unique. A second company requires a different name and Admin email; run the same command with those values. Changing a company's display name later does not change its ID.

Open `http://localhost:8080` and sign in. The initial Admin lands in **Admin → Company setup**. Admins manage work and the economy but cannot own tasks or hold a participant wallet.

## Team setup and activation

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

## First task and first reward smoke checks

On an isolated new company, activate at least one Employee. Complete setup with no rewards. Confirm dashboard totals are zero. As Admin, create an employee marketplace task worth 25 Coins. As Employee, claim it and submit evidence. As Admin, approve it. Confirm one 25-Coin credit, approved submission/cycle history, and no duplicate payout if approval is repeated.

As Admin, create a category and a 10-Coin reward with stock 2. As Employee, redeem it. As Admin, approve and fulfill it with a reference. Confirm FULFILLED, stock 1, and the employee's balance 15. Do not add a fake starting balance. Repeat with a second independently provisioned company and confirm neither company can see or operate on the other's IDs.

## Backup and update safety

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

## Development remains supported

The founder's existing local `docker-compose.yml` uses `CVE_DEV_MODE=true`; `docker compose up -d --build` starts the normal development servers. Development can seed an empty database. Never enable this mode for a pilot database. The legacy reset endpoint now works only when the sole company is the canonical development seed company; the persona list requires authentication and includes only seeded-password identities in that company. A new pilot tenant receives no demo personas, even if development mode is accidentally enabled.

The compiled pilot hides Test Lab, clear workspace, demo reset, and persona tools. Backend development endpoints are independently denied with dev mode off. Development's default known credentials are confined to seed infrastructure and are never used to provision pilot accounts.
