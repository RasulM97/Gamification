# Options Matrix — All Six Decisions

Companion to DECISION_BRIEF.md (full option text lives there). Effort:
XS <1d · S 1–3d · M 3–7d · L 1–3w · XL >3w. Risks: Architecture / Product /
Regression / Adoption. Recommended options in **bold**.

## Decision 1 — Selective Push

| Option | Effort | Arch impact | Arch risk | Product risk | Regression risk | Adoption risk | WSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A — Dashboard-only | XS | NONE | LOW | HIGH (all stalls persist) | LOW | HIGH | no |
| **B — Selective push (abstract contract, email first)** | M | NEW ADAPTER/MODULE | LOW–MED | LOW | MED (notification paths touched) | LOW | no |
| C — Broad push | M–L | NEW ADAPTER/MODULE + preferences | MED | HIGH (fatigue recreates the problem in the inbox) | MED | HIGH | no |

## Decision 2 — People Workflows

| Option | Effort | Arch impact | Arch risk | Product risk | Regression risk | Adoption risk | WSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A — CVE-first | XS | NONE | LOW | HIGH (intake stays broken) | LOW | HIGH | no |
| **B — Hybrid (UI + explicit channel actions, one adapter)** | L | NEW ADAPTER/MODULE | MED (identity mapping, abuse surface) | MED | MED | LOW–MED | no (may benefit later) |
| C — Channel-first | L–XL | NEW ADAPTER/MODULE + UI demotion | MED | MED–HIGH (channel-less companies degraded) | MED | MED | may benefit later |

## Decision 3 — Incentive / Provenance Presentation

| Option | Effort | Arch impact | Arch risk | Product risk | Regression risk | Adoption risk | WSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A — Keep technical chain | XS | NONE | LOW | MED–HIGH (audit stays admin-only) | LOW | MED | no |
| **B — Business-language skin + drill-down** | S–M | UI ONLY | LOW | LOW | LOW–MED (skin truthfulness tests) | LOW | no |
| C — Role-specific provenance | M | UI ONLY | LOW | MED (over-hiding risk) | MED (3× surface) | LOW | no |

## Decision 4 — Admin IA

| Option | Effort | Arch impact | Arch risk | Product risk | Regression risk | Adoption risk | WSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **A — Responsibility-based groups** | S | UI ONLY | LOW | LOW | LOW–MED (nav/route tests) | LOW | no |
| B — Lifecycle-based (Setup/Operate/Audit) | S | UI ONLY | LOW | MED (blurry boundaries) | LOW–MED | LOW | no |

## Decision 5 — Overview / Company Flow

| Option | Effort | Arch impact | Arch risk | Product risk | Regression risk | Adoption risk | WSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A — Keep role widgets | XS | NONE | LOW | MED (stays unvisited) | LOW | MED | no |
| **B — Attention / company-flow recomposition (with anti-surveillance guardrails)** | M | UI ONLY | LOW | MED (surveillance drift — mitigated by guardrails as acceptance criteria) | MED (new selectors/modules) | LOW | no |
| C — Dual view (personal + company) | M–L | UI ONLY | LOW | MED | MED | LOW | no |

## Decision 6 — Task Lite Positioning

| Option | Effort | Arch impact | Arch risk | Product risk | Regression risk | Adoption risk | WSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A — Primary work surface | L ongoing | API/APP expansion | MED | HIGH (competes with Jira — violates strategy) | MED | HIGH | may benefit later |
| **B — Fallback task system + listener posture** | XS–S | NONE / UI ONLY | LOW | LOW | LOW | LOW | no |
| C — Personal/small-team only | S | UI ONLY | LOW | MED (wastes working engine) | LOW | MED | no |

## Totals if all recommendations accepted

- Core contract changes: **0**
- New adapters/modules: **2** (outbound delivery contract + email adapter;
  channel intake adapter + identity mapping)
- UI-only work: provenance skin, admin regroup, overview recomposition,
  task positioning
- Estimated total: **~4–7 engineering weeks** (M + L + S–M + S + M + XS–S,
  with D1-B and D2-B partially shared infrastructure)
- WSE-required decisions: **0** · AI-required decisions: **0**
- Highest-risk item: D2-B (identity mapping + abuse surface in external
  channels) — mitigated by explicit-actions-only and one-adapter pilot scope.
