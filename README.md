# Corporate Virtual Economy

CVE is a background incentive operating layer around existing company work, with an authenticated FastAPI/PostgreSQL backend and React web/demo surfaces. WS1–WS4 are FINAL CLOSED at `f1600b580a540b55fbb8e62e1e7caa47962c313a`; WS5 is not implemented by this documentation sweep.

Start with the [documentation index](docs/README.md), [product/status](docs/PRODUCT.md), [architecture](docs/ARCHITECTURE.md), [operations](docs/OPERATIONS.md) and [testing](docs/TESTING_ACCEPTANCE.md). Historical evidence, superseded decisions and original report recovery are indexed in [history](docs/HISTORY.md). The [review and Kimi handoff](docs/HANDOFF_WS5.md) records this sweep.

Source Code → DB/Migrations → Explicit Contracts → Graphify. Use [AGENTS.md](AGENTS.md) and [repository intelligence](docs/REPOSITORY_INTELLIGENCE.md) for development navigation. Managed, self-hosted and headless deployment share [one Core](docs/adr/ADR-CORE-DEPLOYMENT-MODEL.md).

Run `npm run dev` for the browser demo or follow [PostgreSQL setup](docs/EXTERNAL_POSTGRESQL_RUN.md) and `npm run dev:server` for authenticated server mode. Dependencies must already be installed from package.json; the baseline has no committed npm lockfile. Preserve local runtime data and secrets.
