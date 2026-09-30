# Real E9 webhook capture specimens

These five JSON files derive from actual signed GitHub repository webhooks,
received by the production E9 connector on 2026-09-29 UTC. They are not generated
by `github_helpers.specimen`, and are distinct from the E7.1 GH Archive corpus.

The manifest links each specimen to its provider delivery GUID, original body
SHA-256 and measured byte length, immutable raw row and canonical event. A local
acceptance observer measured bytes/hash/status only; it never saved request bodies,
signature headers or secrets. Its body hashes match the production raw records.
Successful signature verification, repository binding and the generic source
receipt preceded acceptance. Original full request bodies are deliberately absent.

Export starts from the production minimized raw payload. Repository/resource/user
identities and resource numbers are replaced with stable fictional numeric values.
Stored decimal strings are restored to numeric JSON values expected on the wire.
Lifecycle dates, action, state, merge and draft flags remain capture-derived. No
names, descriptions, emails, profile URLs, tokens or signatures are retained.
Each file has a frozen SHA-256 in `manifest.json`.

Run offline on the existing disposable PostgreSQL test configuration:

```sh
python -m pytest tests/test_github_real_captures.py -q
```

Set `CVE_E9_WORKLOAD_REPORT` to an optional local output path for machine-readable
workload results. Golden's database guard permits only `cve_test` or
`cve_golden_test`; never point tests at `cve_e9_live` or a customer database.

The workload derives 1,600 deliveries from these five specimens: 800 supported,
400 retries, 160 unsupported, 80 malformed and 160 invalid signatures. It uses
four companies, two connector instances each and 20 delivery workers. The same
delivery IDs/resource IDs recur in different source instances intentionally.
Rule evaluation runs under contention after ingress. Existing focused economic
tests separately exercise concurrent effect issuance. All four policy outcomes,
approval gating, repeated issuance, reversals and wallet reconciliation are checked.

Frozen specimens and workloads are offline evidence, not provider redelivery,
byte-for-byte original payloads or production capacity certification. Payloads
larger than 32 KiB remain refused by the unchanged production ingress boundary.
