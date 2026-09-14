# N7 — Pilot onboarding and operations

Baseline: N6.1 `cbc367d114641a5a7ad63df1a38da9d37f1c6a6b`. Delivery version: `1.7.0-n7`.

N7 adds seed-free operational provisioning, a six-step Admin setup guide, and single-use account activation. It does not add Organization, Projects, AI, additional roles, or an email invitation service. See [PILOT_RUNBOOK.md](PILOT_RUNBOOK.md) for startup, account setup, smoke checks, backup, and updates.

## Design and boundaries

The provisioning CLI creates one Company, its CompanySettings, and its initial Admin atomically. It uses generated IDs and requires an explicit unique password. Repeated matching provisioning is idempotent and never changes existing credentials or business state. People creation is Admin-only and accepts only MANAGER or EMPLOYEE. Emails are normalized and globally unique; titles do not confer authority.

New users have no usable password until activation. A 256-bit random bearer token is returned once to the creating Admin; only its SHA-256 hash and 24-hour expiry are stored. Activation locks the matching row, validates the password, consumes the token, and stores bcrypt. A pending account can receive a replacement link, which immediately invalidates its previous token. No credential is placed in State, action payloads, business history, or UAT exports. There is no active-user password reset feature in this phase.

The setup state is `NOT_STARTED`, `IN_PROGRESS`, or `COMPLETED`, plus an optional completion timestamp. No per-step table or workflow engine exists. Existing companies migrate to COMPLETED with an unknown historical timestamp; newly provisioned companies start NOT_STARTED. Completion is idempotent and creates no business records. Later edits and reopening the guide preserve completion.

Admin → Company setup contains Company, People, Capacity, Reward operations, Upload policy, and Review/ready. The guide reuses capacity, fulfillment actions, the upload form, and normal reward creation. Completed companies can reopen it; normal Admin controls remain available. Non-Admins see a waiting message before completion. The real API continues to enforce the existing role/tenant model.

Readiness is deterministic in both adapters. It blocks a missing valid Admin, invalid company/user/role/membership, invalid participant capacity, or invalid upload limits. No managers, employees, rewards, tasks, or coins is not a blocker. Pending activation is a warning. The review displays actual counts and settings, including a valid zero-business state. Server completion rechecks readiness transactionally rather than trusting the browser.

## API and migration

| Method | Endpoint | Authority/result |
|---|---|---|
| GET | `/api/onboarding/readiness` | Admin; blocker/warning codes |
| POST | `/api/onboarding/begin` | Admin; updated State |
| PATCH | `/api/company` | Admin; current tenant display name only |
| POST | `/api/users` | Admin; State plus one-time activation token |
| POST | `/api/users/{id}/activation` | Admin, same tenant, pending account only; replacement token |
| POST | `/api/onboarding/complete` | Admin; authoritative readiness check and State |
| POST | `/api/auth/activate` | Public possession of valid single-use token; `{ok:true}` |
| GET | `/activate` | Production SPA activation entry, no-store/no-referrer headers |

Migration `b72e4d1f8307` follows `a41b7c9d2601`: Company onboarding status/timestamp; User activation hash/expiry and unique hash constraint. Existing rows are preserved. Bootstrap adds companyId, onboarding, company membership; email and activation-pending metadata are Admin-only. No password/hash/token enters serialization.

No new business event types. Structured backend operations are `onboarding_begin`, `company_update`, `person_create`, `activation_reissue`, and `onboarding_complete`; they contain identity/result metadata, not credentials. Existing task, capacity, policy, reward, and ledger events are unchanged.

## Runtime and regression corrections

Pilot mode defaults to dev disabled, checks the JWT secret, and never invokes seed startup. The dedicated Docker/Compose path serves the compiled frontend and API together. Test Lab, reset, clear, and personas are hidden in production; UAT instrumentation also declines new attempts in production. Authenticated demo personas are restricted to actual seeded-password users in the seed tenant, and global demo reseed refuses any multi-company or non-seed database.

Removed a duplicate unassigned attention-badge count, the demo company name from real login, and a seeded reward-category fallback. A company with no categories is directed to the existing category manager before first reward creation. No dashboard or economy rules were changed.

All 48 new `setup.*` keys have translations in en, zh-CN, ru, hi, fa, ar, he, tr, ko, and ja. `page.admin.subtitle` now describes real company controls. Existing Auto/LTR/RTL behavior is retained; authored names use automatic direction and emails/links use LTR. New layouts use logical margins and responsive widths.

## Verification

Verification uses dedicated PostgreSQL test databases and a separate production compose project/volumes. The founder's development database is not reset, and unrelated local Docker/config/log/UAT files are hash-checked and excluded from the commit.

- Backend: 176 tests passed, including 19 new N7 tests. Coverage includes fresh Alembic+CLI provisioning, legacy migration preservation, invalid setup, Admin authority, activation expiry/reissue/single use, secret non-export, first actual task/reward lifecycles, two-company isolation, and pilot startup/tool guards.
- Frontend: 506 Vitest tests passed (22 files); both TypeScript checks and both demo/server builds passed. Browser: 323 passed in the final complete demo/server run (201 demo, 122 server). The 23 N7 cases also passed in a targeted run. The first full run had one initial-page-load timeout in an existing Hebrew case; the clean final run passed without changing that test.
- Production image: built and started on entirely new volumes; confirmed zero companies before provisioning. Real browser onboarding, activation-route serving, empty completion, first payout/redemption/fulfillment, and production tool gating passed.
- Final production image update retained completed onboarding and the task/reward records. Development renders version 1.7.0-n7 on port 5173. A pre-migration development database backup was restored into a separate scratch database and all 15 tables compared: original data is unchanged, excluding only the additive N7 columns. All 14 preserved local files match their original hashes.

## Founder UAT (maximum six checks)

1. Start the clean pilot stack, provision a company/Admin, and confirm zero business data.
2. Add one Manager and two Employees; activate accounts and complete setup with no rewards.
3. Complete the first real task and verify its single Coin issuance and history.
4. Create the first category/reward and complete redemption/fulfillment.
5. Provision a second company and confirm tenant isolation.
6. Confirm the pilot build exposes no Test Lab, clear workspace, demo reset, or persona controls.

## Maintainability and file inventory

New modules keep provisioning, accounts, readiness, HTTP routes, and UI steps separate. UploadPolicyForm was extracted for reuse. The canonical reducer and backend services.py did not grow. Generated locale bundles remain flat data files. Final before/after line counts and complete file inventory follow below.

<!-- N7-INVENTORY -->

| File over 500 lines | Before | After | Action |
|---|---:|---:|---|
| backend/app/routes.py | 520 | 523 | Thin dev guards only; all N7 routes live in onboarding_routes.py. |
| src/i18n/locales/ar.json | 894 | 942 | Flat localization data; keep the established bundle structure. |
| src/i18n/locales/en.json | 894 | 942 | Flat localization data; keep the established bundle structure. |
| src/i18n/locales/fa.json | 894 | 942 | Flat localization data; keep the established bundle structure. |
| src/i18n/locales/he.json | 894 | 942 | Flat localization data; keep the established bundle structure. |
| src/i18n/locales/hi.json | 894 | 942 | Flat localization data; keep the established bundle structure. |
| src/i18n/locales/ja.json | 894 | 942 | Flat localization data; keep the established bundle structure. |
| src/i18n/locales/ko.json | 894 | 942 | Flat localization data; keep the established bundle structure. |
| src/i18n/locales/ru.json | 894 | 942 | Flat localization data; keep the established bundle structure. |
| src/i18n/locales/tr.json | 894 | 942 | Flat localization data; keep the established bundle structure. |
| src/i18n/locales/zh-CN.json | 894 | 942 | Flat localization data; keep the established bundle structure. |

### New files

- `backend/alembic/versions/b72e4d1f8307_pilot_onboarding.py`
- `backend/app/dev_guard.py`
- `backend/app/onboarding.py`
- `backend/app/onboarding_routes.py`
- `backend/app/pilot_accounts.py`
- `backend/app/provision_company.py`
- `backend/app/provisioning.py`
- `backend/tests/test_n7_migration.py`
- `backend/tests/test_n7_pilot.py`
- `deploy/Dockerfile.pilot`
- `deploy/Dockerfile.pilot.dockerignore`
- `deploy/compose.pilot.yml`
- `docs/N7-PILOT-ONBOARDING.md`
- `docs/PILOT_RUNBOOK.md`
- `e2e/n7-cases.ts`
- `e2e/n7-demo.spec.ts`
- `e2e/n7-server.spec.ts`
- `src/components/UploadPolicyForm.tsx`
- `src/features/onboarding/ActivationScreen.tsx`
- `src/features/onboarding/OnboardingView.tsx`
- `src/features/onboarding/PeopleSetup.tsx`
- `src/features/onboarding/operations.test.ts`
- `src/features/onboarding/operations.ts`

### Modified files

- `.gitignore`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/routes.py`
- `backend/app/security.py`
- `backend/app/seed.py`
- `backend/app/serializers.py`
- `backend/tests/conftest.py`
- `backend/tests/test_n23_migration.py`
- `backend/tests/test_n4_migration.py`
- `package.json`
- `src/App.tsx`
- `src/components/Login.tsx`
- `src/domain/model.ts`
- `src/features/test-lab/testlab.instrumentation.ts`
- `src/i18n/locales/ar.json`
- `src/i18n/locales/en.json`
- `src/i18n/locales/fa.json`
- `src/i18n/locales/he.json`
- `src/i18n/locales/hi.json`
- `src/i18n/locales/ja.json`
- `src/i18n/locales/ko.json`
- `src/i18n/locales/ru.json`
- `src/i18n/locales/tr.json`
- `src/i18n/locales/zh-CN.json`
- `src/store.tsx`
- `src/views/Admin.tsx`
- `src/views/Rewards.tsx`

### New localization keys

- `setup.title`
- `setup.open`
- `setup.completed`
- `setup.intro`
- `setup.companyName`
- `setup.save`
- `setup.step.company`
- `setup.step.people`
- `setup.step.capacity`
- `setup.step.rewardOps`
- `setup.step.uploads`
- `setup.step.review`
- `setup.capacityHint`
- `setup.rewardHint`
- `setup.optionalReward`
- `setup.zero`
- `setup.blockers`
- `setup.ready`
- `setup.warnings`
- `setup.finish`
- `setup.back`
- `setup.next`
- `setup.error`
- `setup.name`
- `setup.addPerson`
- `setup.peopleHint`
- `setup.demoPeople`
- `setup.saved`
- `setup.linkHint`
- `setup.activationLink`
- `setup.pending`
- `setup.reissue`
- `setup.activate`
- `setup.activated`
- `setup.passwordHint`
- `setup.confirmPassword`
- `setup.activationError`
- `setup.waiting`
- `setup.blocker.company`
- `setup.blocker.admin`
- `setup.blocker.people`
- `setup.blocker.capacity`
- `setup.blocker.uploads`
- `setup.warning.noEmployees`
- `setup.warning.noManagers`
- `setup.warning.pendingActivation`
- `setup.warning.noRewards`
- `setup.categoryFirst`
