"""Gate 0/G: preserve RA-1.1 evidence for a run and export a sanitized review archive.

Usage:  python _gate0_preserve.py [run_id]   (default: final-20261012)

For the given run id:
- Leaves uat-out/ra11/<run_id>/ byte-identical (hash manifest recorded).
- Builds uat-out/ra11/review-archive-<run_id>/ with path redactions,
  a REDACTIONS.md log, a repro-instructions file, and a recomputed
  SHA-256 manifest.
- Zips the sanitized copy into a single portable archive.

Run _results.py FIRST so results.json is included in the archive.

Checksums prove archive integrity in transit — they are NOT independent
verification of the results; reproduction comes from the repro instructions
and the tracked harness code.

Credential scan performed beforehand found no passwords, tokens, JWTs, or
Authorization headers in the evidence (only the password_hash COLUMN NAME in
SELECT lists). Redactions below are limited to local filesystem paths.
"""
import hashlib, json, shutil, sys, zipfile
from pathlib import Path

RID = sys.argv[1] if len(sys.argv) > 1 else "final-20261012"
ROOT = Path("uat-out/ra11")
SRC = ROOT / RID
DST = ROOT / f"review-archive-{RID}"
ZIP = ROOT / f"review-archive-{RID}.zip"

_cwd = str(Path.cwd()).replace("/", "\\")
REDACTIONS = [
    # (needle, replacement, reason) — match both raw and JSON-escaped forms
    (_cwd.replace("\\", "\\\\"), "<REPO_ROOT>", "local workspace absolute path (JSON-escaped)"),
    (_cwd, "<REPO_ROOT>", "local workspace absolute path"),
    ("C:\\\\Users\\\\Rasul", "<USER_PROFILE>", "local user profile path (JSON-escaped)"),
    ("C:\\Users\\Rasul", "<USER_PROFILE>", "local user profile path"),
]

REPRO = """# Reproducing this run

1. Check out the commit recorded in `fingerprint` events / `results.json`.
2. From the repository root, with the managed venv:

   .venv/Scripts/python.exe backend/tests/ra11/smoke.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/oracle_tests.py
   .venv/Scripts/python.exe backend/tests/ra11/e1_freeze.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e1b_mechanism.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e2_upgrade.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e4_lock_order.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e7_races.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e7_r6.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e3_auth_pool.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e6_orphans.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/_results.py {rid}

Requirements: Windows host, the repo venv (psutil pinned there — harness-only,
used for port-ownership verification), pgserver disposable PostgreSQL, no
production database involved. All artifacts land under `uat-out/ra11/{rid}/`
(git-ignored). The harness never deletes anything outside the current run
directory (fail-closed containment; see oracle_tests.py).

Checksums in `manifest_sanitized.json` prove archive integrity in transit.
They are NOT independent verification of the results.
"""

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

if not SRC.is_dir():
    sys.exit(f"missing {SRC}")
if DST.exists():
    shutil.rmtree(DST)

# 1) Record original hashes (originals untouched)
orig_hashes = {}
for p in sorted(SRC.rglob("*")):
    if p.is_file():
        orig_hashes[str(p.relative_to(SRC)).replace("\\", "/")] = sha256(p)
(ROOT / f"ORIGINAL_HASHES_{RID}.json").write_text(
    json.dumps(orig_hashes, indent=2) + "\n", encoding="utf-8")

# 2) Sanitized copy
redaction_log = []
new_hashes = {}
for p in sorted(SRC.rglob("*")):
    rel = p.relative_to(SRC)
    out = DST / rel
    if p.is_dir():
        out.mkdir(parents=True, exist_ok=True)
        continue
    out.parent.mkdir(parents=True, exist_ok=True)
    data = p.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        shutil.copy2(p, out)  # binary artifact (uploads) copied as-is
        new_hashes[str(rel).replace("\\", "/")] = sha256(out)
        continue
    original = text
    for needle, repl, reason in REDACTIONS:
        if needle in text:
            n = text.count(needle)
            text = text.replace(needle, repl)
            redaction_log.append({"file": str(rel).replace("\\", "/"),
                                  "replacement": repl, "occurrences": n, "reason": reason})
    out.write_text(text, encoding="utf-8", newline="\n")
    new_hashes[str(rel).replace("\\", "/")] = sha256(out)
    if text != original and not any(r["file"] == str(rel).replace("\\", "/") for r in redaction_log):
        redaction_log.append({"file": str(rel).replace("\\", "/"), "replacement": "(line-ending normalization)", "occurrences": 0, "reason": "n/a"})

(DST / "REPRODUCE.md").write_text(REPRO.format(rid=RID), encoding="utf-8")
new_hashes["REPRODUCE.md"] = sha256(DST / "REPRODUCE.md")

(DST / "REDACTIONS.md").write_text(
    "# Redaction log\n\n"
    f"Original evidence at `uat-out/ra11/{RID}/` is preserved byte-identical;\n"
    f"original hashes in `../ORIGINAL_HASHES_{RID}.json`.\n\n"
    "Credential scan: no passwords, tokens, JWTs, Authorization headers, or keys were\n"
    "present in the evidence (matches were limited to the `password_hash` column NAME\n"
    "in SELECT lists). Redactions are limited to local absolute paths.\n\n"
    "Hashed/foreign identifiers (request IDs, backend PIDs, transaction IDs, lock\n"
    "identities, timestamps, ordering) are preserved verbatim.\n\n"
    + "\n".join(f"- `{r['file']}`: {r['occurrences']}x `{r['replacement']}` ({r['reason']})"
               for r in redaction_log) + "\n\n"
    "Sanitized-file hashes: see `manifest_sanitized.json`.\n", encoding="utf-8")

new_hashes["REDACTIONS.md"] = sha256(DST / "REDACTIONS.md")
(DST / "manifest_sanitized.json").write_text(
    json.dumps(new_hashes, indent=2) + "\n", encoding="utf-8")

# 3) Portable zip
if ZIP.exists():
    ZIP.unlink()
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(DST.rglob("*")):
        if p.is_file():
            z.write(p, p.relative_to(ROOT))
print(json.dumps({
    "run_id": RID,
    "original_files": len(orig_hashes),
    "sanitized_files": len(new_hashes),
    "redactions": len(redaction_log),
    "zip": str(ZIP), "zip_sha256": sha256(ZIP),
}, indent=2))
