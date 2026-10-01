# Organization / Projects validation

**STATUS: PASS — evidence collection complete. Recommended decision: C.**
**Implementation is NOT approved and has NOT started.** Verified 2026-10-02 against
`bd2e76ca8ad8e2b1c24c253d36e440b1ba009912`.

The recommendation is conditional on the team-scoped and cross-functional
workflows explicitly required by the validation brief. This is reproducible
synthetic structural evidence, not interviews, production incidents or proof of
customer demand. Company A and Company E do not need Organization/Projects for
the tested workflows. Do not mandate these concepts for every company.

## Evidence and method

- [Frozen dataset / ground truth](../../backend/tests/organization_validation/dataset.json)
- [Production-service characterization](../../backend/tests/test_organization_validation.py)
- [Test-only model comparison](../../backend/tests/organization_validation/concepts.py)
- [Concept counterexamples](../../backend/tests/organization_validation/test_concepts.py)
- [Measured results, all scenarios and repeat hashes](EVIDENCE.json)
- [Every observed gap and workaround assessment](FAILURES.md)
- [Source/dependency map](DEPENDENCY_MAP.md)

Five disposable PostgreSQL companies contain exactly 285 users. No Team or Project
records, hidden User fields or new schema were inserted. Membership and project
lifecycle truth lives solely in the external test fixture. User IDs, role/team
assignment and project memberships are reproducible from the dataset seed/rules.

| Company | Users | Shape | Primary scenarios | Observed scenario gaps |
| --- | --- | --- | --- | --- |
| A | 20 | Flat; no teams/projects | 3 | 0 |
| B | 60 | Engineering, Sales, Operations; scoped managers | 10 | 3 |
| C | 80 | Cross-functional Alpha, Beta, Gamma with overlapping people | 11 | 8 |
| D | 100 | Functional membership plus overlapping temporary projects; transfers | 6 | 3 |
| E | 25 | Two GitHub repositories, minimal hierarchy | 6 | 0 |

Every company also executes Thanks, Recognition, Help, Task creation, Rule/Policy,
Shadow and a real economic issuance. Thirty-six primary scenarios cover same-team
and cross-team Recognition, cross-project Help, project-local versus company work,
manager overlap, project closure, team movement, project joins/leaves, disabled
capabilities, duplicate deliveries and economic retries. Each scenario declares
expected visibility, Rule scope, conditional approver, Safety context and reporting
group before comparing actual behavior. The primary result is one named facet;
these are not 180 independently executed assertions across every facet.

Two clean runs produced the same logical hash:
`66c5a55d1ae512821ccc0eda754624bc1a7b91e3300de0a52f829204989fe136`.
Each run persisted 55 canonical events, 9 economic effects, ledger total 90 and
8 Shadow observations. Test source registrations and HMAC deliveries were local,
synthetic and disposable; no live GitHub repository or connector was changed.
Generated signing secrets are neither exported nor included in the reports.

The engine clock is fixed. External logical ticks express desired membership and
lifecycle changes. Production has no scope mutation API, so no report pretends to
have executed one. The concurrency probe deliberately holds an approval worker
behind a barrier until the external scope manager transfer occurs; the unchanged
production service then accepts the old company Manager. The conceptual resolver
checks decision-time authority separately from occurrence-time membership.
This exposes an unrepresentable input, not a tested production membership-lock
implementation. A future implementation still needs genuine transaction races.

## Measured gaps

| Category | Scenario gaps |
| --- | --- |
| Manager / work visibility scope | 3 |
| Rule / Policy / project-command lifecycle scope | 4 |
| Approval authority scope | 4 |
| Safety context | 0 |
| Shadow / historical reporting | 2 |
| Connector work context | 1 |
| Cross-tenant access | 0 |

The visibility count includes the employee-peer counterexample to using PRIVATE
Tasks for a shared team work item. The Rule/Policy category includes rejection of
a project selector and acceptance of ordinary work after an external project
closure, not four defects in the predicate evaluator. Related scenarios share
underlying missing context; fourteen is not a count of fourteen independent
architectural defects. The company-scoped baseline still obeys its current
contracts; these are failures against the additional supplied scope requirements.

Three out-of-scope managers successfully approved requests and enabled 30 coins
of real test credit. Separately, Beta Help evaluated through an Alpha-labelled
fallback Rule/Policy produced 10 coins. Those 40 coins are incorrect under the
synthetic scope oracle, but valid under the existing company-only contract.
Exactly-once identity, normal role checks, tenant checks and Ledger consistency
were not bypassed. The failing boundary is missing scoped business authority.

## Alternatives that work today

PRIVATE Task + explicit manager reviewer/viewer IDs solves a single-worker private
work item. An Admin-only approval hint safely centralizes incentive approval.
Explicit actor-ID Rule predicates work for a stable team list. GitHub repositoryId
and Policy sourceId safely separate E's two repositories; reporting can derive
repository groups from existing event data. A separately tested, manually curated
Help-ID predicate correctly distinguishes two already known project events.

These alternatives must not be dismissed as impossible. They do not meet the
whole ongoing workflow when a single task must be shared by multiple selected
employees, a manager must retain authority in one scope but lose it in another,
or work context must survive membership changes without an external manual map.
Demoting a manager globally or routing every decision to Admin removes the required
valid scoped authority. Duplicating private tasks changes work/claim identity.

Manual project event-ID lists are a valid bounded workaround for frozen data.
They require an authoritative outside assignment for every new work item, a
separate policy/approval/reporting convention and separate lifecycle validation.
The current predicate limit is 50 IN values with no generic membership join;
larger histories require further rule configuration. Updating Rule definitions
also changes their versioned inputs. Recreating membership and historical context
through resource lists across domains is high-maintenance duplication, not a
single safely enforced context boundary. The recommendation does not depend on
claiming that a static predicate cannot select a known event.

## Model comparison

| Model | Comparison result | Interpretation |
| --- | --- | --- |
| A — current company-only | 22/36 primary scenarios meet the oracle; 14 gaps | Flat and repository-separated workflows pass. Scoped manager authority and durable cross-functional work context remain absent. |
| B — minimal Team scope | Conceptually resolves 4 gaps; 10 remain | Team visibility/authority and historic functional attribution address B plus D's team history. Team membership cannot distinguish overlapping projects. |
| C — Team + Project context | Conceptually resolves all 14 measured gaps | Requires trusted scope capture, scoped admission/approval and temporal provenance. Bare entity tables would not produce this result. |

B/C are small test-only resolvers over the external fixture, not alternate CVE
engines. They reuse current measured results for unaffected controls. Independent
concept tests demonstrate same-team/different-project membership, authority versus
occurrence time, closed-project history, tenant rejection and independence from
expected-answer fields. Their 0 remaining cases do not certify production security,
concurrency, migrations, performance or all possible organizational requirements.

## Safety and history

No incorrect Safety outcome was proven. Twenty same-actor events across two
project-labelled groups still produce the expected company-wide ACTOR_VELOCITY
OBSERVE finding. Splitting the count into ten per project could hide that signal;
it is not evidence of a false positive. Keep mandatory global protection unless
separate abuse-ground-truth validation justifies a different detector contract.

Current immutable events, Shadow records and effects remain unchanged when the
external membership timeline advances. That does not make historical grouping
recoverable: joining an old event to a current team can silently label yesterday's
Engineering work as Sales. Store/refer to immutable occurrence context if scope
is approved; current approver authority is a separate decision-time fact. Project
closure must preserve prior events, approvals and economics. Replays of old facts
must be distinguished from new activity after closure.

## Recommended decision C — pending explicit approval

For the supplied B–D requirements, both functional Team authority and independent
Project work context are needed. A Team cannot represent Alpha/Beta overlap:
the concept counterexample places two Engineering employees in different project
memberships. A repository cannot identify a project when a shared repository and
overlapping participants produce equivalent minimized facts.

The smallest candidate design to review later is Company → Team (members and
scoped managers) plus Company → Project (members, status, optional owner and
created/closed times). Historical membership/context provenance and current
approval authority are necessary correctness semantics, not an org hierarchy.
Do not add Departments, divisions, cost centers, portfolios, sprints, budgets,
resource planning, reporting trees or a generic scope engine. Do not add a new
connector or weaken company isolation, mandatory Safety, economic identity,
append-only Ledger or derived wallet behavior.

Approval of the recommendation must confirm that these synthetic B–D constraints
are required product workflows. If the intended deployment only needs A/E and
static curated rules, defer implementation and proceed to the separately scoped
System Integration / Maturity Gate instead. No such next phase was started here.

## Checks and reproduction

204 unique checks passed: 2 clean validation runs, 5 conceptual checks, 149
unchanged Golden checks and 48 capability regressions. After adding the final
ledger reconciliation assertion/export, all 7 validation/concept checks passed
again. The full product suite was not rerun for this test/documentation-only
phase; the prior product acceptance remains historical evidence.

Repository sanity checks passed: 93 relative documentation links resolve, JSON
and Python syntax checks pass, frozen dataset/report hashes agree, and the scoped
credential-pattern scan found no matches. The diff contains no production,
migration, dependency or existing Golden changes. Graphify was refreshed and
reports CURRENT (2,978 nodes / 12,958 edges). PowerShell classified a Graphify
stderr progress message as a native-command error; the graph was written and the
separate status check confirmed freshness.

From `backend/`, with `CVE_TEST_DATABASE_URL` pointing to a dedicated disposable
PostgreSQL database, a synthetic `CVE_WEBHOOK_MASTER_KEY` and an existing writable
`CVE_ORGANIZATION_REPORT_DIR`:

```sh
python -m pytest tests/test_organization_validation.py tests/organization_validation -q
python -m pytest tests/golden tests/policy_golden tests/approval_golden tests/economic_golden tests/safety_golden tests/test_capabilities.py -q
```

The fixture truncates/reseeds its database. Never use a live or founder database.
No production source, migrations, dependencies or existing Golden datasets changed.
No commit or push was performed for this evidence-only phase.

**STOP: do not implement Organization / Projects until the decision is explicitly approved.**
