# Development agents

Before broad repository exploration, query the repository knowledge graph when available.
Run `npm run graph:status`; refresh with `npm run graph` when stale.
Use `npm run graph:query -- "question or symbol"` and narrow noisy results to symbols.
Before modifying any file or domain rule, verify the relevant source directly.
If graph and source conflict, source wins.

The graph is navigation, not a specification. Inspect domain rules, migrations,
database contracts and applicable tests before implementation. Run relevant tests;
refresh the graph when architecture/dependencies change. Preserve founder UAT
files, local logs, uploads, environment files and database data.

Setup, privacy, MCP and limitations: [repository intelligence](docs/REPOSITORY_INTELLIGENCE.md).
Deployment constraint: [one core, three deployment modes](docs/adr/ADR-CORE-DEPLOYMENT-MODEL.md).
