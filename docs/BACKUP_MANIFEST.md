# Backup manifest — 2026-11-02

This file lists what GitHub received and what stayed on disk. It contains no secrets.

Repository: https://github.com/RasulM97/Gamification

Local filesystem snapshot, not modified by this publication: `F:\Flutter and web projects\CVE-freeze-2026-11-02`.

Original workspace, not modified: `D:\Web projects\Gamification app`.

## Source code archived on GitHub

Pushed without force and without changing `main`:

| Ref | SHA |
| --- | --- |
| `stabilization-day2-batch1` | `41bfde0204293a64c39b689980d90cb3d57aec0f` |
| `stabilization-day2-batch2` | `32ade0768d57ae5a225659e164d1198de3d477dc` |
| `archive/cve-pause-2026-11-02` | the pause commit that adds this document |
| tag `cve-pause-2026-11-02` | same commit as the archive branch |

`main` stays `394d1c6e6d8c9cfcb5317aac0a05aa4b31eb6444`.

Batch 2 includes Alembic revisions through `ee05d2b22601_task_recommendations.py` and `ee04f0202601_command_receipts.py`. `main` stops at `ee03b2c4d503_auth_sessions.py`.

The archive adds only documentation: root `README.md`, `docs/README.md`, this file, `docs/PROJECT_FREEZE_2026-11-02.md` and `docs/RESUME_DEVELOPMENT.md`.

## Documentation archived

Pause documents are on the archive branch and tag. Historical contracts (`docs/ARCHITECTURE.md`, `docs/PRODUCT.md`, and the rest of the index) were already on Batch 2 and remain there. They describe the WS4-era baseline and are marked historical in `docs/README.md`.

## Locally preserved, not on GitHub

These stayed in the F: snapshot. They were not uploaded:

- `private-encrypted\` — `backend/.env`, UAT credential files, SQL dumps, and three PostgreSQL 16 `.pgtest` clusters. EFS-encrypted to the creating Windows user. ACL limited to that user, SYSTEM and Administrators. **No EFS recovery certificate.**
- `app_log\` except two omitted Playwright browser caches, including the local CPython 3.12.11 tree.
- `uat-out\ra11` evidence and `FINAL_DAY1_REPORT.md`.
- `report\` except dumps (dumps are inside `private-encrypted`).
- Untracked founder handoff text files and `scripts/add_i18n_keys.py`, `scripts/add_i18n_keys_ws5.py`, which are in the F: snapshot working tree. They are not part of Batch 2 or this archive commit.
- Broken `.worktrees` checkouts. Their commits are the GitHub branches above. The directories themselves are not a second repository.

SHA-256 of the non-secret snapshot tree on 2026-11-02: 25,187 files, 1,275,249,347 bytes, 0 mismatches against D:. Private files: 33,307 files, 659,000,579 bytes, 0 mismatches. Manifest file on the snapshot: `BACKUP-SHA256.tsv`.

## Not recovered and not verified

- Database `cve_e9_live` at `127.0.0.1:5432`. **NOT RECOVERED.**
- Uploads at `D:\Web projects\Gami app N2.1\backend\uploads`. **NOT RECOVERED.**
- `C:\Users\Rasul\AppData\Local\Docker\wsl\disk\docker_data.vhdx` (23,007 MB). Docker was stopped. The file was **not opened**. It is not established that this disk contains `cve_e9_live`.
- `.pgtest` and the SQL dumps are local test artifacts. They are **not** a verified copy of `cve_e9_live`.

## Omitted from both GitHub and the slimmer snapshot tree

Regenerable copies were left out of the F: snapshot on purpose: `node_modules`, the broken `.venv`, `dist`, `graphify-out`, and the Playwright browser directories under `app_log`. `backend/requirements.txt` and `package.json` are in Git. There is no npm lockfile.

## What may be deleted later, and what must stay

Deletion is a separate founder decision. This publication does not delete D: or F:.

Safe to treat as replaceable **after** the founder accepts the GitHub SHAs:

- Source files on D: that match Batch 2, because those commits are on GitHub.
- Regenerable `node_modules`, `dist`, and the broken `.venv`.

Must stay until the founder makes a separate copy they can still open:

- `F:\Flutter and web projects\CVE-freeze-2026-11-02\private-encrypted` (secrets, dumps, `.pgtest`). GitHub does not have them. There is no EFS recovery agent.
- Anything still only on D: inside `backend/.env`, `uat-out\credentials.txt`, `uat-out\uat-env.local`, `*.dump`, and `.pgtest`, until those bytes are confirmed readable from the F: private folder.
- The Docker virtual disk, until someone inspects it. It was not proven empty of CVE data.
- Untracked handoff text on D: and in the F: snapshot root. Those files are not in this Git commit.

`cve_e9_live` and the old upload directory cannot be preserved by deleting or keeping D:. They were not found.
