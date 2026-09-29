# Trusted economic source authority (E8 contract)

E7 protects against double-paying already settled Task/Rewards observations and
against clients claiming internal authority through an event type string. Its
Python gate and deferred PostgreSQL trigger both restrict exact source/type
combinations. E8 cannot satisfy that original closed contract.

The extension uses tenant-owned immutable producer registrations and immutable
event receipts. Trusted producer namespaces begin `TRUSTED_`; external MANUAL
and GENERIC_WEBHOOK adapters never accept a caller-selected source namespace.
Registration and receipt creation are server-code-only facilities, with no HTTP
management surface, no configuration field in raw/manual envelopes, and no
payload flag interpreted as authority. An event alone, even bearing a trusted
namespace, is insufficient: a matching receipt and registered producer are
required. Trusted application code remains responsible for domain authorization
and for creating the domain fact and receipt atomically. Direct database-owner
compromise is outside this boundary, as it is for existing ledger guards.

Producer identity is `(company, source_kind, source_id)`; a receipt is bound by
composite foreign keys to that producer and the same-company canonical event.
A database trigger verifies the event's source identity matches the receipt.
Registrations/receipts cannot be updated or deleted. Receipts can only accompany
new events from the trusted writer; it refuses to promote existing unreceipted
facts or attest a changed command under an existing logical identity.

The Economic Effect service and deferred guard call the same PostgreSQL
`economic_source_authorized(company,event)` predicate. It knows no E8 event names
and reads only producer/receipt provenance. A frozen E7 compatibility predicate
retains exactly the previously allowed MANUAL/webhook combinations, including
the existing source binding; it grants no new external event authority. Future
modules use the trusted writer without economic-engine or SQL event-name changes.

Candidate identity, immutable decisions, approval authority, exact amounts,
reversals, ledger semantics and derived balances remain unchanged. A source
receipt is permission to reach governance checks, not permission to pay. No
rule, BLOCK, SHADOW_ONLY and unapproved REQUIRE_APPROVAL still yield no payout.

Migration E80 adds only source registrations/receipts and replaces the source
predicate in the deferred effect guard. Historical E7 SQL stays frozen. Downgrade
refuses to discard issued trusted-source provenance; safe unused registrations
may be removed when explicitly downgrading. Existing E7 credits are not rewritten.

Impact map: source-authority package → canonical store/internal recorder;
Economic Effect eligibility → source-authority SQL predicate; new migration →
source-authority tables/guards. No reverse import from Canonical Core, ledger,
rules, policies or approvals into feature modules. E8 domain work starts only
after contract, Golden, economic and public replay gates pass.

Approved canonical names are `internal.peer.thanks`,
`internal.manager.recognition`, `internal.help.completed`. Naming validation
and canonical identity semantics are unchanged.
