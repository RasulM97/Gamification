# CVE / Gamification

CVE is a corporate virtual economy with a React/TypeScript demo and an
authoritative FastAPI/PostgreSQL backend. The implemented baseline now includes
**Module Flags / Capability Controls — CLOSED / PASS** on top of E11. See the
[acceptance report](docs/capabilities/ACCEPTANCE.md) for executed verification.

## Start here

- [Documentation index](docs/README.md)
- [Current status and completed phases](docs/STATUS.md)
- [Current architecture and invariants](docs/ARCHITECTURE.md)
- [Roadmap and WSE deferral gate](docs/ROADMAP.md)
- [Verified testing results and commands](docs/testing/README.md)
- [Runtime modes](docs/RUNTIME.md), [local backend setup](docs/EXTERNAL_POSTGRESQL_RUN.md),
  and [pilot operations](docs/PILOT_RUNBOOK.md)
- [Repository intelligence / Graphify](docs/REPOSITORY_INTELLIGENCE.md)

For the standalone demo, run `npm ci`, then `npm run dev` from the repository
root. For the server, follow the linked backend setup, then run `npm run dev:server`.
The backend working directory is `backend/`; its entrypoint is `app.main:app`.
Demo mode does not implement the full E7–E11 API capabilities in browser state.

The incentive path is Event → Rule → Candidate → Policy → Safety → Approval
where required → Economic Effect → Ledger. Stages are explicitly invoked;
webhook receipt does not automatically issue a reward. Shadow creates no real
economics. Wallet values are derived from the append-only signed ledger.

**Next boundary:** Organization / Projects only if validated, then System
Integration / Maturity Gate. No later phase is authorized by this completion. WSE and AI maturity
remain deferred. See the roadmap before starting work.
