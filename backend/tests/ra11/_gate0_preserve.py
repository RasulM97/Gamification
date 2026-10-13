"""Gate 0/G: preserve RA-1.1 evidence for a run and export a sanitized review archive.

Usage:  python _gate0_preserve.py [run_id]   (default: final-20261012)

For the given run id:
- Leaves uat-out/ra11/<run_id>/ byte-identical (hash manifest recorded).
- Builds uat-out/ra11/review-archive-<run_id>/ with path redactions,
  a REDACTIONS.md log, a repro-instructions file, a credential scan of the
  CURRENT run, and a recomputed SHA-256 manifest.
- Zips the sanitized copy into a single portable archive.

Run _results.py FIRST so results.json is included in the archive.

Containment (Gate A): the run id is validated (traversal / sibling /
historical-run names are rejected) and every deletion is guarded — the only
removable paths are exactly review-archive-<run-id>[.zip] inside the
evidence root. There is no direct unguarded shutil.rmtree.

Credential discipline (Gate G): this exporter NEVER states that credentials
were absent without scanning. Every export scans the current run directory
for credential-shaped strings and records the raw result in
credential_scan.json; REDACTIONS.md summarizes exactly what the scan found.

Checksums prove archive integrity in transit — they are NOT independent
verification of the results; reproduction comes from the repro instructions
and the tracked harness code.
"""
import hashlib, json, re, shutil, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402

RID = lab.validate_run_id(sys.argv[1] if len(sys.argv) > 1
                          else "final-20261012")
ROOT = lab.OUT_ROOT
SRC = (ROOT / RID).resolve()
DST = (ROOT / f"review-archive-{RID}").resolve()
ZIP = (ROOT / f"review-archive-{RID}.zip").resolve()

_cwd = str(Path.cwd()).replace("/", "\\")
REDACTIONS = [
    # (needle, replacement, reason) — match both raw and JSON-escaped forms
    (_cwd.replace("\\", "\\\\"), "<REPO_ROOT>", "local workspace absolute path (JSON-escaped)"),
    (_cwd, "<REPO_ROOT>", "local workspace absolute path"),
    ("C:\\\\Users\\\\Rasul", "<USER_PROFILE>", "local user profile path (JSON-escaped)"),
    ("C:\\Users\\Rasul", "<USER_PROFILE>", "local user profile path"),
]

# Test-only constants that are part of the tracked harness source (not real
# credentials), plus the schema identifier `password_hash` (a column NAME in
# SELECT lists — never a value). Matches on these are reported but
# classified KNOWN-TEST.
KNOWN_TEST_CONSTANTS = (
    "ra11-lab-fixed-test-secret-not-a-credential",
    "demo1234",
    "password_hash",
)

CREDENTIAL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"password", r"passwd", r"secret", r"authorization",
        r"bearer\s+\S+", r"\btoken\b", r"\bjwt\b", r"api[-_]?key",
        r"private[-_]?key",
    )
]

REPRO = """# Reproducing this run

1. Check out the commit recorded in `fingerprint` events / `results.json`.
2. From the repository root, with the managed venv (execution order is
   mandatory; stop at the first failed gate):

   .venv/Scripts/python.exe backend/tests/ra11/regression_tests.py
   .venv/Scripts/python.exe backend/tests/ra11/oracle_tests.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/smoke.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e1_freeze.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e1b_mechanism.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e2_upgrade.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e4_lock_order.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e5_commit_outcomes.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e7_races.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e7_r6.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e3_auth_pool.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/e6_orphans.py {rid}
   .venv/Scripts/python.exe backend/tests/ra11/_results.py {rid}

   (`run_all.py {rid}` executes the same steps under one command and stops
   at the first failed gate.)

Requirements: Windows host, the repo venv (psutil pinned there — harness-only,
used for port-ownership verification and process-tree kills), pgserver
disposable PostgreSQL, no production database involved. All artifacts land
under `uat-out/ra11/{rid}/` (git-ignored). The harness never deletes anything
outside the current run directory (fail-closed containment; see
oracle_tests.py).

Checksums in `manifest_sanitized.json` prove archive integrity in transit.
They are NOT independent verification of the results.
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def guarded_remove(p: Path):
    """The ONLY deletion primitive of this exporter. Refuses anything that
    is not exactly the current run's own archive directory inside the
    evidence root. Fails closed: any doubt -> ValueError, nothing deleted."""
    p = Path(p).resolve()
    root = ROOT.resolve()
    expected = (root / f"review-archive-{RID}").resolve()
    if p != expected:
        raise ValueError(f"refusing to delete {p}: only the current run's "
                         f"own archive dir {expected} may be replaced")
    if p.parent != root:
        raise ValueError(f"archive dir outside evidence root: {p}")
    shutil.rmtree(p)


def guarded_unlink(p: Path):
    p = Path(p).resolve()
    expected = (ROOT.resolve() / f"review-archive-{RID}.zip").resolve()
    if p != expected or p.parent != ROOT.resolve():
        raise ValueError(f"refusing to remove {p}")
    p.unlink()


def scan_credentials(src: Path) -> dict:
    """Scan the CURRENT run directory for credential-shaped strings.
    Records file/pattern/count only — never the matched text."""
    findings = []
    files_scanned = 0
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        files_scanned += 1
        for pat in CREDENTIAL_PATTERNS:
            hits = pat.findall(text)
            if not hits:
                continue
            # A hit is KNOWN-TEST only when the file contains enough
            # occurrences of a tracked test-only constant that itself
            # matches the pattern to account for every hit.
            known = 0
            for k in KNOWN_TEST_CONSTANTS:
                if pat.search(k):
                    known += (len(pat.findall(k))
                              * text.lower().count(k.lower()))
            findings.append({
                "file": str(p.relative_to(src)).replace("\\", "/"),
                "pattern": pat.pattern, "occurrences": len(hits),
                "known_test_constant_hits": known,
                "classification": "KNOWN-TEST" if known >= len(hits)
                else "REVIEW",
            })
    return {"scanned_root": str(src), "files_scanned": files_scanned,
            "patterns": [p.pattern for p in CREDENTIAL_PATTERNS],
            "known_test_constants": list(KNOWN_TEST_CONSTANTS),
            "findings": findings,
            "review_findings": sum(1 for f in findings
                                   if f["classification"] == "REVIEW")}


if not SRC.is_dir():
    sys.exit(f"missing {SRC}")
if SRC.parent != ROOT.resolve():
    sys.exit(f"refusing to export outside the evidence root: {SRC}")
if DST.exists():
    guarded_remove(DST)

# 1) Record original hashes (originals untouched)
orig_hashes = {}
for p in sorted(SRC.rglob("*")):
    if p.is_file():
        orig_hashes[str(p.relative_to(SRC)).replace("\\", "/")] = sha256(p)
(ROOT / f"ORIGINAL_HASHES_{RID}.json").write_text(
    json.dumps(orig_hashes, indent=2) + "\n", encoding="utf-8")

# 2) Credential scan of the CURRENT run (Gate G: no scan, no claim)
scan = scan_credentials(SRC)
(DST).mkdir(parents=True, exist_ok=True)
(DST / "credential_scan.json").write_text(
    json.dumps(scan, indent=2) + "\n", encoding="utf-8")

# 3) Sanitized copy
redaction_log = []
new_hashes = {"credential_scan.json": sha256(DST / "credential_scan.json")}
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

review = scan["review_findings"]
scan_summary = (
    f"Credential scan performed at export time on the CURRENT run "
    f"(`credential_scan.json`): {scan['files_scanned']} text files scanned; "
    f"{len(scan['findings'])} pattern finding(s), of which "
    f"{sum(1 for f in scan['findings'] if f['classification'] == 'KNOWN-TEST')}"
    f" match documented test-only constants and {review} require review."
)
(DST / "REDACTIONS.md").write_text(
    "# Redaction log\n\n"
    f"Original evidence at `uat-out/ra11/{RID}/` is preserved byte-identical;\n"
    f"original hashes in `../ORIGINAL_HASHES_{RID}.json`.\n\n"
    + scan_summary + "\n"
    + ("NOTE: REVIEW-classified findings are listed in credential_scan.json; "
       "this archive makes no absence-of-credentials claim for them.\n"
       if review else
       "No REVIEW-classified credential findings in this run.\n")
    + "\nRedactions are limited to local absolute paths.\n\n"
    "Hashed/foreign identifiers (request IDs, backend PIDs, transaction IDs, lock\n"
    "identities, timestamps, ordering) are preserved verbatim.\n\n"
    + "\n".join(f"- `{r['file']}`: {r['occurrences']}x `{r['replacement']}` ({r['reason']})"
               for r in redaction_log) + "\n\n"
    "Sanitized-file hashes: see `manifest_sanitized.json`.\n", encoding="utf-8")

new_hashes["REDACTIONS.md"] = sha256(DST / "REDACTIONS.md")
(DST / "manifest_sanitized.json").write_text(
    json.dumps(new_hashes, indent=2) + "\n", encoding="utf-8")

# 4) Portable zip
if ZIP.exists():
    guarded_unlink(ZIP)
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(DST.rglob("*")):
        if p.is_file():
            z.write(p, p.relative_to(ROOT))
print(json.dumps({
    "run_id": RID,
    "original_files": len(orig_hashes),
    "sanitized_files": len(new_hashes),
    "redactions": len(redaction_log),
    "credential_scan": {"files_scanned": scan["files_scanned"],
                        "findings": len(scan["findings"]),
                        "review": review},
    "zip": str(ZIP), "zip_sha256": sha256(ZIP),
}, indent=2))
