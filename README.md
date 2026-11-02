# Corporate Virtual Economy

CVE is a background incentive operating layer around existing company work, with an authenticated FastAPI/PostgreSQL backend and React web/demo surfaces.

**Preservation state, 2026-11-02.** Development is paused. The latest implementation is `stabilization-day2-batch2` at `32ade0768d57ae5a225659e164d1198de3d477dc`. GitHub `main` remains `394d1c6e6d8c9cfcb5317aac0a05aa4b31eb6444` and is 15 commits behind that branch. This pause is recorded on `archive/cve-pause-2026-11-02` and tag `cve-pause-2026-11-02`.

Start here:

- [Documentation index](docs/README.md)
- [Project freeze](docs/PROJECT_FREEZE_2026-11-02.md)
- [Resume development](docs/RESUME_DEVELOPMENT.md)
- [Backup manifest](docs/BACKUP_MANIFEST.md)

Historical contracts remain in [product/status](docs/PRODUCT.md), [architecture](docs/ARCHITECTURE.md), [operations](docs/OPERATIONS.md), [testing](docs/TESTING_ACCEPTANCE.md) and [history](docs/HISTORY.md). Those pages still describe the 2026-10-08 WS4 baseline. Where they disagree with this pause, the pause documents and the Batch 2 source win.

Source Code → DB/Migrations → Explicit Contracts → Graphify. Use [AGENTS.md](AGENTS.md) and [repository intelligence](docs/REPOSITORY_INTELLIGENCE.md) for navigation. Managed, self-hosted and headless deployment share [one Core](docs/adr/ADR-CORE-DEPLOYMENT-MODEL.md).

Run `npm run dev` for the browser demo, or follow [PostgreSQL setup](docs/EXTERNAL_POSTGRESQL_RUN.md) and `npm run dev:server` for authenticated server mode. There is no committed npm lockfile. Do not point migrations or tests at a database you did not create for that purpose. Local secrets, SQL dumps and the unrecovered `cve_e9_live` database are not in this repository.
