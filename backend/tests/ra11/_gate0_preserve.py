"""Gate 0: preserve original RA-1.1 evidence and export a sanitized review archive.

- Leaves uat-out/ra11/final-20261012/ byte-identical (hash manifest recorded).
- Builds uat-out/ra11/review-archive-final-20261012/ with path redactions,
  a REDACTIONS.md log, and a recomputed hash manifest.
- Zips the sanitized copy into a single portable archive.

Credential scan performed beforehand found no passwords, tokens, JWTs, or
Authorization headers in the evidence (only the password_hash COLUMN NAME in
SELECT lists). Redactions below are limited to local filesystem paths.
"""
import hashlib, json, shutil, sys, zipfile
from pathlib import Path

ROOT = Path("uat-out/ra11")
SRC = ROOT / "final-20261012"
DST = ROOT / "review-archive-final-20261012"
ZIP = ROOT / "review-archive-final-20261012.zip"

_cwd = str(Path.cwd()).replace("/", "\\")
REDACTIONS = [
    # (needle, replacement, reason) — match both raw and JSON-escaped forms
    (_cwd.replace("\\", "\\\\"), "<REPO_ROOT>", "local workspace absolute path (JSON-escaped)"),
    (_cwd, "<REPO_ROOT>", "local workspace absolute path"),
    ("C:\\\\Users\\\\Rasul", "<USER_PROFILE>", "local user profile path (JSON-escaped)"),
    ("C:\\Users\\Rasul", "<USER_PROFILE>", "local user profile path"),
]

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
(ROOT / "GATE0_ORIGINAL_HASHES_final-20261012.json").write_text(
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

(DST / "REDACTIONS.md").write_text(
    "# Gate 0 redaction log\n\n"
    "Original evidence at `uat-out/ra11/final-20261012/` is preserved byte-identical;\n"
    "original hashes in `../GATE0_ORIGINAL_HASHES_final-20261012.json`.\n\n"
    "Credential scan: no passwords, tokens, JWTs, Authorization headers, or keys were\n"
    "present in the evidence (matches were limited to the `password_hash` column NAME\n"
    "in SELECT lists). Redactions are limited to local absolute paths.\n\n"
    "Hashed/foreign identifiers (request IDs, backend PIDs, transaction IDs, lock\n"
    "identities, timestamps, ordering) are preserved verbatim.\n\n"
    + "\n".join(f"- `{r['file']}`: {r['occurrences']}x `{r['replacement']}` ({r['reason']})"
               for r in redaction_log) + "\n\n"
    "Sanitized-file hashes: see `manifest_gate0_sanitized.json`.\n", encoding="utf-8")

new_hashes["REDACTIONS.md"] = sha256(DST / "REDACTIONS.md")
(DST / "manifest_gate0_sanitized.json").write_text(
    json.dumps(new_hashes, indent=2) + "\n", encoding="utf-8")

# 3) Portable zip
if ZIP.exists():
    ZIP.unlink()
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(DST.rglob("*")):
        if p.is_file():
            z.write(p, p.relative_to(ROOT))
print(json.dumps({
    "original_files": len(orig_hashes),
    "sanitized_files": len(new_hashes),
    "redactions": len(redaction_log),
    "zip": str(ZIP), "zip_sha256": sha256(ZIP),
}, indent=2))
