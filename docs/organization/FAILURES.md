# Reproducible scope gaps

These are mismatches against the supplied synthetic workflow contracts, not regressions against the current company-only product contract. Counts are scenario-level: related symptoms may share one missing context. Models B/C are test-only conceptual resolvers.

## team-task

SCENARIO: Sales manager must not see Engineering-shared work (Company B)

EXPECTED: `false`

ACTUAL: `true`. EMPLOYEES audience also permits every active same-company Manager.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: YES

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: scope members and company Admin; no unrelated manager

EXPECTED RULE SCOPE: Engineering

EXPECTED APPROVER: current Engineering manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Engineering

## private-team-peer

SCENARIO: PRIVATE workaround cannot share one task with a second Engineering employee (Company B)

EXPECTED: `true`

ACTUAL: `false`. A second employee cannot be granted peer visibility through manager-only viewer/reviewer lists.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: YES

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: scope members and company Admin; no unrelated manager

EXPECTED RULE SCOPE: Engineering

EXPECTED APPROVER: current Engineering manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Engineering

## project-task

SCENARIO: Same-team manager outside Beta must not see Beta work (Company C)

EXPECTED: `false`

ACTUAL: `true`. Project Beta membership is not an input to Task visibility.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: NO

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: scope members and company Admin; no unrelated manager

EXPECTED RULE SCOPE: Beta

EXPECTED APPROVER: current Beta manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Beta

## team-approval

SCENARIO: Sales manager cannot approve Engineering incentive (Company B)

EXPECTED: `false`

ACTUAL: `true`. Current MANAGER_OR_ADMIN accepted this manager and authorized 10 coins; synthetic scope oracle excludes them.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: YES

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: existing read authorization unless this scenario explicitly tests scope

EXPECTED RULE SCOPE: Engineering

EXPECTED APPROVER: current Engineering manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Engineering

## project-approval

SCENARIO: Alpha manager cannot approve Beta incentive (Company C)

EXPECTED: `false`

ACTUAL: `true`. Current MANAGER_OR_ADMIN accepted this manager and authorized 10 coins; synthetic scope oracle excludes them.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: NO

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: existing read authorization unless this scenario explicitly tests scope

EXPECTED RULE SCOPE: Beta

EXPECTED APPROVER: current Beta manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Beta

## changed-manager

SCENARIO: Old Alpha owner cannot approve after authority transfer (Company D)

EXPECTED: `false`

ACTUAL: `true`. Current MANAGER_OR_ADMIN accepted this manager and authorized 10 coins; synthetic scope oracle excludes them.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: NO

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: existing read authorization unless this scenario explicitly tests scope

EXPECTED RULE SCOPE: Alpha

EXPECTED APPROVER: current Alpha manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Alpha

## project-rule

SCENARIO: Alpha reward must not match Beta Help by overlapping participants (Company C)

EXPECTED: `false`

ACTUAL: `true`. Both project activities have identical participants and payload schema; resource IDs do not carry project membership.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow. YES for a frozen, trusted event-ID list; that partial alternative was independently tested.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: NO

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: scope members and company Admin; no unrelated manager

EXPECTED RULE SCOPE: Alpha

EXPECTED APPROVER: current Alpha manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Alpha

## project-policy

SCENARIO: Beta work must not receive Alpha ALLOW decision (Company C)

EXPECTED: `false`

ACTUAL: `true`. Without an authoritative project fact, Alpha-targeted fallback ALLOW also permits Beta and credits 10 coins.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow. YES for a frozen, trusted event-ID list; that partial alternative was independently tested.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: NO

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: scope members and company Admin; no unrelated manager

EXPECTED RULE SCOPE: Alpha

EXPECTED APPROVER: current Alpha manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Alpha

## project-shadow-group

SCENARIO: Project label must be recoverable from stored Shadow provenance (Company C)

EXPECTED: `"Alpha"`

ACTUAL: `"UNRECOVERABLE"`. Shadow links its immutable event, but neither event nor Help row records a project.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: NO

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: scope members and company Admin; no unrelated manager

EXPECTED RULE SCOPE: Alpha

EXPECTED APPROVER: current Alpha manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Alpha

## historical-team-group

SCENARIO: Old event remains Engineering after participant moves to Sales (Company D)

EXPECTED: `"Engineering"`

ACTUAL: `"UNRECOVERABLE"`. A current participant join would say Sales after tick 2000; original Engineering membership is not stored.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: YES

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: scope members and company Admin; no unrelated manager

EXPECTED RULE SCOPE: Engineering

EXPECTED APPROVER: current Engineering manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Engineering

## missing-project-command

SCENARIO: Project-local Help must carry authoritative context without prose inference (Company C)

EXPECTED: `true`

ACTUAL: `false`. Existing strict Help command rejects a project selector: VALIDATION

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: NO

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: scope members and company Admin; no unrelated manager

EXPECTED RULE SCOPE: Alpha

EXPECTED APPROVER: current Alpha manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Alpha

## shared-repo-project

SCENARIO: Same repository and overlapping people cannot identify Alpha versus Beta (Company C)

EXPECTED: `"Alpha"`

ACTUAL: `"UNRECOVERABLE"`. One shared repository plus overlapping members cannot select Alpha vs Beta; no project field survives normalization.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: NO

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: scope members and company Admin; no unrelated manager

EXPECTED RULE SCOPE: Alpha

EXPECTED APPROVER: current Alpha manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Alpha

## membership-race

SCENARIO: Revoked project manager cannot authorize a request admitted after transfer (Company D)

EXPECTED: `false`

ACTUAL: `true`. A controlled barrier advances external project authority before actual approval; production has no membership/version input to reject stale project authority.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: NO

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: existing read authorization unless this scenario explicitly tests scope

EXPECTED RULE SCOPE: Alpha

EXPECTED APPROVER: current Alpha manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Alpha

## closed-project

SCENARIO: New project-scoped activity cannot be accepted after project closes (Company C)

EXPECTED: `false`

ACTUAL: `true`. A new ordinary Help action still succeeds after oracle closes Gamma; no project lifecycle is expressible in the command.

CAN EXISTING ARCHITECTURE SOLVE IT SAFELY: NO for the complete ongoing scoped workflow.

WORKAROUND COMPLEXITY: HIGH

WOULD TEAM MODEL SOLVE: NO

WOULD PROJECT MODEL SOLVE: YES (with trusted scope capture and enforcement, not an entity table alone)

EXPECTED VISIBILITY: scope members and company Admin; no unrelated manager

EXPECTED RULE SCOPE: Gamma

EXPECTED APPROVER: current Gamma manager or Admin (when approval is required)

EXPECTED SAFETY CONTEXT: company + event type + actor/recipient + bounded occurrence-time history; no project exemption

EXPECTED REPORTING GROUP: Gamma
