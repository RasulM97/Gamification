# N6 — Test Lab & UAT operations

Version: `1.6.0-n6`. N5 baseline: `ae5a9f981b44006237c9767d4220bfa9f11dc48c`.

## Running a session

Open **Test Lab** as Admin and select **Start session**. Recording is explicit:
NOT_STARTED → ACTIVE → ENDED. Stop freezes the end time; operations finishing
after Stop are ignored. Repeated Start cannot erase an active session. A new
session replaces ended evidence only after the UI confirmation; export first.
Clear also requires confirmation and changes only Test Lab storage.

The existing Admin navigation restriction remains. In demo, switch personas to
exercise employee/manager flows, then return to Admin to review or stop. Server
development account switching performs real sign-ins. Each operation keeps the
actor ID, name and role at the attempt, independently of the initiating tester.

Choose **Expected block** before the next attempted operation when testing a
business refusal. The expectation resets after one attempt. Disabled controls
do not dispatch and therefore do not create fictitious operation records.

## Evidence and verdicts

The observer records action/operation type, target type/ID, session, timestamp,
actor, page, runtime, version, expected/actual outcome, verdict and result code.
Server events retain actual HTTP status, route/method and elapsed time. Queued
creations compare the state immediately before execution to the authoritative
response, so the resolved target belongs to that operation. Specific assignment
acceptance is distinct from marketplace claim. Refused redemption targets the
reward; successful redemption targets the created redemption.

Expected success + success = PASS. Expected block + actual business refusal =
PASS. A mismatched expectation = FAIL. Transport errors and HTTP 401/404/429/5xx
are always FAIL. HTTP 403/409/422 are business refusals and only pass when a block
was expected. Unchanged informational actions are WARN. Demo observes the
canonical reducer result (including cloned no-change results) and uses the
canonical capacity-refusal helper; no independent business rules are introduced.
The demo adapter applies that same reducer result exactly once, so generated
task/redemption IDs in evidence match the actual persisted objects.

Operation filters cover verdict, operation type and actor role. Issues require
severity P0–P3 and title, with optional description and related operation. They
retain automatic context and recent events; duplicate reports remain distinct.
Notes are separate authored records, never issues or operation verdicts.

Summary includes operation totals, PASS/FAIL/WARN, issue and note totals,
severity counts, start/end and duration. Export downloads both JSONL and TXT.
JSONL contains SESSION, SUMMARY, EVENT, ISSUE and NOTE records. TXT is a stable
English diagnostic format with technical outcome codes; the application UI is
localized and authored text is preserved.

## Storage, version and privacy

Browser-local key `cve-uat-v2` retains one session across reloads. Pre-N6 records
remain readable as ended history; no automatic recording resumes. A failed
localStorage write retains exportable evidence in memory and displays a warning.
That fallback lasts only for the current tab. Concurrent browser tabs are not a
shared UAT coordination service; use one recording tab per session.

`package.json` is the canonical version. Existing Vite injection supplies
`__APP_VERSION__`, re-exported by `src/version.ts`; no git command runs in the UI.
Runtime comes from the existing build-time data-mode source. The observer
whitelists metadata and compact deltas; it never automatically captures action
payloads, credentials, headers, raw exception prose or full state. Manually
authored issue/note content is retained verbatim.

No backend API, database schema, migration or domain rule changes. Demo remains
offline. Instrumentation, storage, exports, types, presentation and UI are split
under `src/features/test-lab`; `src/uat.ts` and the old view path remain compatible
facades. The central store is below 500 lines after extraction.

## Verification

- TypeScript project and Node configuration checks; demo and server builds.
- Full Vitest suite: 485 passed, including 29 new N6 tests and 12 legacy UAT tests.
- Backend pytest: 142 passed (205 existing dependency warnings).
- Full Playwright regression: 270 cases (175 demo, 95 server-dev), including
  24 new N6 browser cases and an exact applied task-ID assertion.
  The final broad run passed 269; the added creation test initially omitted its
  required description. After fixing that test setup, all 24 N6 cases passed on
  rerun, covering all 270 distinct cases successfully.
- Isolated real PostgreSQL/backend/browser check: approval HTTP 200 and competing
  claim HTTP 409 recorded once each, with Dana/Priya actor snapshots and PASS
  for the explicitly expected conflict. No development product data was reset.
- Migration current/head: `a41b7c9d2601`.
- N6 browser cases cover lifecycle, filters, operations, issues, notes, exports,
  actual status handling, zero demo API calls, and en/fa/ar/he at 768/1440 widths.
- All ten locale dictionaries receive the same 38 new Test Lab keys; the full
  localization parity suite checks the complete dictionaries.

Run `npx vitest run`, `npx tsc -b`, `npm run build`, and Playwright against demo
and server-dev Vite hosts. The verification environment used installed Chrome
and placed browser artifacts outside the Vite-watched repository.

## Founder UAT

1. Start as Admin, exercise a task cycle across accounts, then review actor/target records.
2. Select Expected block and attempt a permitted-to-click business refusal; check PASS and its result code.
3. Add a P1 issue related to an operation and a separate note; check counts.
4. Stop and download JSONL + TXT; verify records, timestamps and version.
5. Repeat in Persian with Direction Auto and in server mode; verify RTL and real HTTP outcomes.

## File audit

Fourteen unrelated local files were checked against their baseline SHA-256 hashes
and excluded from delivery. Existing locale dictionaries remain large data files;
only the 38 N6 entries were appended. No dictionary restructuring was required.
The original 552-line store was reduced below 500 lines by extracting UAT code.

| Path | Lines | Action |
| --- | ---: | --- |
| `e2e/m1c.spec.ts` | 206 | modified |
| `package.json` | 30 | modified |
| `src/api.ts` | 114 | modified |
| `src/i18n/locales/ar.json` | 887 | modified |
| `src/i18n/locales/en.json` | 887 | modified |
| `src/i18n/locales/fa.json` | 887 | modified |
| `src/i18n/locales/he.json` | 887 | modified |
| `src/i18n/locales/hi.json` | 887 | modified |
| `src/i18n/locales/ja.json` | 887 | modified |
| `src/i18n/locales/ko.json` | 887 | modified |
| `src/i18n/locales/ru.json` | 887 | modified |
| `src/i18n/locales/tr.json` | 887 | modified |
| `src/i18n/locales/zh-CN.json` | 887 | modified |
| `src/store.tsx` | 402 | modified |
| `src/styles/hardening.css` | 122 | modified |
| `src/uat.test.ts` | 152 | modified |
| `src/uat.ts` | 4 | modified |
| `src/views/TestLab.tsx` | 1 | modified |
| `e2e/n6-cases.ts` | 163 | new |
| `e2e/n6-server.spec.ts` | 2 | new |
| `e2e/n6.spec.ts` | 2 | new |
| `src/features/test-lab/IssueForm.tsx` | 18 | new |
| `src/features/test-lab/OperationsPanel.tsx` | 28 | new |
| `src/features/test-lab/TestLabView.tsx` | 73 | new |
| `src/features/test-lab/testlab.export.ts` | 94 | new |
| `src/features/test-lab/testlab.instrumentation.ts` | 176 | new |
| `src/features/test-lab/testlab.presentation.ts` | 17 | new |
| `src/features/test-lab/testlab.store.ts` | 111 | new |
| `src/features/test-lab/testlab.test.ts` | 154 | new |
| `src/features/test-lab/testlab.types.ts` | 81 | new |
| `src/version.ts` | 2 | new |

## New localization keys

- `testLab.localHint`
- `testLab.replaceConfirm`
- `testLab.clearConfirm`
- `testLab.exportFormats`
- `testLab.runtime`
- `testLab.version`
- `testLab.duration`
- `testLab.seconds`
- `testLab.nextExpected`
- `testLab.expectedHint`
- `testLab.status.NOT_STARTED`
- `testLab.status.ACTIVE`
- `testLab.status.ENDED`
- `testLab.outcome.SUCCESS`
- `testLab.outcome.BLOCKED`
- `testLab.outcome.ERROR`
- `testLab.outcome.NO_CHANGE`
- `testLab.outcome.UNKNOWN`
- `testLab.operations`
- `testLab.issues`
- `testLab.notes`
- `testLab.verdict`
- `testLab.actor`
- `testLab.showing`
- `testLab.noOperations`
- `testLab.expected`
- `testLab.actual`
- `testLab.severity`
- `testLab.related`
- `testLab.noIssues`
- `testLab.noNotes`
- `testLab.copied`
- `testLab.copyReport`
- `testLab.severity.P0`
- `testLab.severity.P1`
- `testLab.severity.P2`
- `testLab.severity.P3`
- `testLab.storageWarning`
