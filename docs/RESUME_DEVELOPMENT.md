# Resume CVE development

Resume from `stabilization-day2-batch2` or from tag `cve-pause-2026-11-02`. Do not resume from GitHub `main`. `main` does not contain the Day-2 fixes or migration `ee05d2b22601`.

The tag is Batch 2 plus the 2026-11-02 pause documents. The branch `stabilization-day2-batch2` is Batch 2 without those documents. Either is a valid code base. Prefer the tag when you also want the freeze notes.

## Prerequisites observed on 2026-11-02

- Windows, Node v24.20.0, npm 11.19.0.
- Python 3.12. The machine's default `python` was 3.14.7 and the `py` launcher was absent. A known-good interpreter is not stored in Git. Use a normal Python 3.12.11 install.
- PostgreSQL 16 for server mode and backend tests. Create a **new** database. Do not reuse `cve_e9_live`.
- Git. Docker only if you use `docker-compose.yml` or `deploy/compose.pilot.yml`.

## Get the code

```powershell
git clone https://github.com/RasulM97/Gamification.git cve
cd cve
git switch -c stabilization-day2-batch2 --track origin/stabilization-day2-batch2
git rev-parse HEAD
```

Expected Batch 2 SHA: `32ade0768d57ae5a225659e164d1198de3d477dc`.

To include the pause documents:

```powershell
git switch -c archive/cve-pause-2026-11-02 --track origin/archive/cve-pause-2026-11-02
```

Confirm the recommendation migration is present:

```powershell
Test-Path backend\alembic\versions\ee05d2b22601_task_recommendations.py
```

## Local setup

There is no `package-lock.json`. `npm install` is not byte-reproducible.

```powershell
npm install
npm run dev
```

`npm run dev` is demo mode unless `VITE_CVE_DATA_MODE` is exactly `server`. Demo mode does not need PostgreSQL.

Backend:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

If `py` is missing, invoke a Python 3.12 `python.exe` instead. Copy settings by **name** into a new `backend/.env`. That file is gitignored. Names are listed in `backend/app/config.py` with the `CVE_` prefix, plus `CVE_TEST_DATABASE_URL` for pytest. Generate new secrets. Do not copy values from old machines into Git.

Set `CVE_DATABASE_URL` to the new empty database and `CVE_UPLOAD_DIR` to a new writable folder. The old upload path is gone.

From `backend\`:

```powershell
alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Batch 2, `alembic heads` must include `ee05d2b22601`. Older sentences in `docs/OPERATIONS.md` and `docs/EXTERNAL_POSTGRESQL_RUN.md` name earlier heads.

Server UI from the repository root:

```powershell
npm run dev:server
```

## Tests

Frontend:

```powershell
npm test -- src
npm run build
```

Backend tests truncate the database named by `CVE_TEST_DATABASE_URL`. Use a disposable database. Do not run them against `cve_e9_live`.

```powershell
cd backend
python -m pytest tests --ignore=tests/test_safety_workload.py -q
```

## Worktrees

Old `.worktrees` directories in the local snapshot have `gitdir` pointers into `D:\Web projects\Gami app N2.1`, which no longer exists. Do not repair those directories. From a fresh clone:

```powershell
git worktree add ..\cve-day2 stabilization-day2-batch2
```

## What to do first when work resumes

1. Check out Batch 2 or the pause tag and confirm `ee05d2b22601` is in the tree.
2. Decide whether Batch 2 should become `main`. That merge is not authorized by this pause.
3. Treat F03 (`docs/recovery/RA1_2_F03_POLICY.md`) as open policy, not as a finished code change.
4. Replace historical status pages only when someone is explicitly editing documentation.
5. Schedule human UAT only with new participants. The preserved kit does not record a completed human run.

## Local data this repository does not restore

Secrets, dumps, `.pgtest`, application logs and the encrypted private folder live only on the founder's machine, under `F:\Flutter and web projects\CVE-freeze-2026-11-02\private-encrypted` for the sensitive set. Reading that folder needs the same Windows user. There is no EFS recovery certificate. `cve_e9_live`, the old uploads directory and the unopened Docker disk are not in that folder and are not recovered.
