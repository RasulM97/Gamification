# Repository intelligence (E0.1)

Graphify is optional development tooling. The product, API, schema and customer
deployments do not depend on it. Architecture decision:
[ADR-CORE-DEPLOYMENT-MODEL](adr/ADR-CORE-DEPLOYMENT-MODEL.md).

## Setup

Requires Git, Node (existing npm workflow), uv and Python 3.12. Tested on Windows
with Node 24.20.0 and Python 3.12.11. From the repository root:

```powershell
uv venv --python 3.12 .venv
uv pip sync --python .venv/Scripts/python.exe --require-hashes scripts/graphify-requirements.txt
npm run graph
npm run graph:status
npm run graph:query -- "economicPosition ledger"
```

On POSIX use `.venv/bin/python` in the sync command. Do not reuse `.venv` for the
backend; this environment is dedicated to Graphify. If `.venv` already belongs to
another project/tool, preserve it and use a separate checkout for this setup.
On Windows with disabled PowerShell script execution, use `npm.cmd` instead of
`npm`. If uv's default cache is inaccessible, set `UV_CACHE_DIR` to a writable
temporary directory. Installation downloads public packages; indexing does not
upload repository contents. No global skill/hook installation is needed.

The official [Graphify project](https://github.com/Graphify-Labs/graphify) publishes
the `graphifyy` package. Version 0.9.67 and transitive dependencies are hash-locked
in `scripts/graphify-requirements.txt`; the small `.in` file records the direct
dependency. To deliberately review/update the lock:

```sh
uv pip compile scripts/graphify-requirements.in --python-version 3.12 --universal --generate-hashes --output-file scripts/graphify-requirements.txt
```

No backend requirements or frontend dependencies were added. The pilot Docker
context excludes the tooling environment and graph artifacts.

## Index, freshness and privacy

`npm run graph` runs Graphify `extract . --code-only --force --max-workers 2`.
The launcher sets `PYTHONHASHSEED=0` before Python starts (avoids upstream Windows
`os.execvpe` access violations) and enables UTF-8. Python/TS/TSX and other supported
code/config are AST-parsed locally. Markdown/media semantic extraction, LLM
labeling, global graph merge, live database inspection and uploads are not used.
Do not replace this command with a generic assistant `/graphify` semantic pass.

`.graphifyignore` plus `.gitignore` exclude environment files, logs, founder local
reports, uploads, dependencies, tool environments and graph output. Do not place
secrets inside source code. Treat generated graphs and query logs as private
source-derived data. Graphify may write local query metadata to its user cache;
do not publish that cache either. No HTTP listener is started by these commands.

`npm run graph:status` prints **GRAPH CURRENT** (exit 0) or **GRAPH STALE** (exit 1).
The ignored `graphify-out/cve-status.json` records HEAD, a fingerprint of tracked
and nonignored files (excluding local environment/log data), generation time and
graph hash. Changes, additions, deletions, branch/commit changes, missing/corrupt
graphs and graph tampering invalidate the stamp. This intentionally errs toward
refreshing, including for documentation changes. Ignored inputs are outside the
freshness contract; do not force-add ignored sources to the index corpus.
Generation refuses a freshness stamp if files changed during indexing.
`graph:query` refuses stale output. Refresh after committing to stamp the new HEAD.
There is no watcher, daemon or git hook.

All `graphify-out/` artifacts and `.venv/` are ignored. Initial measured index:
232 code files, 1,626 nodes, 6,017 edges; `graph.json` 2,729,666 bytes and total
generated output about 4.3 MB before validation probes. These are disposable,
source-derived artifacts with local paths; committing them creates churn and
privacy risk. Track only configuration, dependency lock, launcher and docs.

## Agents and MCP

The canonical agent rules are in [AGENTS.md](../AGENTS.md). Query the graph,
identify candidate modules, inspect source directly, check current domain rules,
migrations and database contracts, implement, test, then refresh if architecture
or dependencies changed. **GRAPH != SOURCE OF TRUTH.** Code, migrations and
database contracts are authoritative. If graph and source conflict, source wins;
raise real specification disagreements instead of silently changing domain rules.

[graphify-mcp.example.json](graphify-mcp.example.json) is an optional stdio template.
Replace `<REPOSITORY>` locally with your checkout; on POSIX replace
`.venv/Scripts/python.exe` with `.venv/bin/python`. Merge the entry into your
client's local MCP configuration; do not overwrite other servers or commit local
paths. No credentials are required. Run `graph:status` before MCP queries and
refresh/restart the server after changes. The direct MCP endpoint does not enforce
the repository freshness stamp. Verified tools include `query_graph`, `get_node`,
`get_neighbors`, `shortest_path` and `graph_stats`. Prefer `get_node`/`get_neighbors`
for precise symbols and qualify ambiguous symbols with a file path.

MCP exposes private repository-derived content to its client. Connect only an
authorized client; whether that client sends tool results to a hosted model is a
separate, explicit client privacy decision. Local CLI indexing itself needs no
hosted service. Do not invoke GitHub PR tools as part of local-only analysis.

Remote MCP is not configured. If explicitly needed later, bind HTTP to
`127.0.0.1` or a private interface, set `GRAPHIFY_API_KEY` through secret management,
and use an authenticated encrypted tunnel/private TLS gateway with access
controls. Never expose an unauthenticated public endpoint or commit a key.

## Navigation validation and limitations

All four requested natural-language questions returned navigable source paths.
Broad queries can select irrelevant similarly named symbols and truncate output;
they are candidate discovery, not exhaustive dependency analysis. Follow with
`explain` or MCP `get_node`/`get_neighbors`, then read the files. For example:

```powershell
.venv/Scripts/python.exe -m graphify explain approve_work
.venv/Scripts/python.exe -m graphify explain economicPosition
.venv/Scripts/python.exe -m graphify explain backend/app/task_access.py::require_view
.venv/Scripts/python.exe -m graphify explain backend/app/service_common.py::act
```

| Question | Useful graph navigation, verified against source |
| --- | --- |
| Task approval | `backend/app/routes.py` → `services.py` / `task_services.py::approve_work`; graph edges identify `require_view`, `require_review`, `ledger`, submission and cycle updates. UI/demo: `src/domain/taskAccess.ts`, `reducer.ts`, `views/Reviews.tsx`. |
| Ledger/economic position dependencies | `backend/app/service_common.py::ledger`, `economy_position.py`, task/reward/cycle services and `models.py::LedgerTransaction`; `src/domain/economyPosition.ts` callers `balanceOf`, `coinDebtOf`, `TaskModals.tsx` and integrity tests. |
| Private Task visibility | `backend/app/task_access.py`, `serializers.py`, `routes.py`, `src/domain/taskAccess.ts`, store/reducer and integrity tests. The legacy `domain.py::can_see_task` alone is incomplete: current task access includes viewer/reviewer membership. |
| Future Canonical Event subsystem | Graph candidates: `service_common.py::act/note`, task/reward/cycle services, `models.py`, `routes.py`, `serializers.py`, `src/domain/events.ts`, `model.ts`, `reducer.ts` and `components/EventText.tsx`. Direct source review additionally requires `backend/alembic/versions/` and migration/parity tests. This is an inferred investigation list, not an implemented subsystem or definitive impact plan. |

No graph can discover a subsystem that does not exist. N3.2 event records are
existing activity/notification presentation contracts, not the future canonical
event core. AST edges miss dynamic dispatch and do not prove authorization,
transaction correctness or migration compatibility. Documentation and unsupported
formats are intentionally not semantically indexed.

## Validation and troubleshooting

Baseline: 126 frontend tests and TypeScript check passed. Database-free backend
smoke executes all six existing functions in `backend/tests/test_domain.py` using
`runpy`, without importing `conftest.py`. This checks pure rules only, not PostgreSQL
transactions. Never point the ordinary pytest fixture at founder/production data:
it truncates and reseeds tables. No database was accessed for E0.1.

Post-change: 142 frontend tests (`engine`, `integrity`, `runtime`), TypeScript and
server-mode Vite build passed; build retains its large-chunk warning. Backend
pure-rule smoke is repeated after tooling setup. MCP validation performs an actual
stdio initialize, tools/list and query_graph call returning `economyPosition.ts`.
Freshness validation covers missing stamp, changed/new/deleted source, changed HEAD,
graph tampering and recovery. See the final E0.1 report for commit verification.

If the graph is stale/missing, run `npm run graph`. If Python is missing, finish
setup; do not install Graphify into the backend environment. If upstream Windows
launch crashes, use the npm launcher with its preset hash seed. If a query is noisy,
use exact path-qualified symbols; ambiguity and truncation are not complete answers.
If indexing fails, its stamp is removed and stale queries are refused. Do not mark
a failed/partial graph current manually or replace Graphify without approval.
