"""Versioned E80 SQL. No E8 event names or feature-specific authority branches."""
from ..economic_effects.schema import INSTALL_SQL as E7_SQL

OLD_PREDICATE = """e.type IN ('external.customer.praise','external.repository.merged','custom.signal.observed')
      AND ((e.source_kind='MANUAL' AND e.actor_id IS NOT NULL AND e.source_id=e.actor_id)
        OR (e.source_kind='GENERIC_WEBHOOK' AND EXISTS (SELECT 1 FROM webhook_sources w WHERE w.id=e.source_id AND w.company_id=e.company_id)))"""
OLD_EFFECT = E7_SQL.split('CREATE FUNCTION check_economic_effect()',1)[1].split('CREATE CONSTRAINT TRIGGER economic_effect_complete',1)[0]
RESTORE_EFFECT = 'CREATE OR REPLACE FUNCTION check_economic_effect()'+OLD_EFFECT
assert OLD_EFFECT.count(OLD_PREDICATE)==1
REPLACE_EFFECT = RESTORE_EFFECT.replace(OLD_PREDICATE,'economic_source_authorized(e.company_id,e.id)')

INSTALL_SQL = """
CREATE FUNCTION economic_source_legacy_v1(company varchar, event_id varchar) RETURNS boolean
LANGUAGE sql STABLE AS $$
SELECT EXISTS (SELECT 1 FROM canonical_events e WHERE e.company_id=$1 AND e.id=$2
 AND """+OLD_PREDICATE+"""); $$;
CREATE FUNCTION economic_source_authorized(company varchar, event_id varchar) RETURNS boolean
LANGUAGE sql STABLE AS $$
SELECT economic_source_legacy_v1($1,$2) OR EXISTS (
 SELECT 1 FROM source_receipts r JOIN trusted_producers p
 ON p.company_id=r.company_id AND p.source_kind=r.source_kind AND p.source_id=r.source_id
 JOIN canonical_events e ON e.company_id=r.company_id AND e.id=r.event_id
 WHERE r.company_id=$1 AND r.event_id=$2
 AND e.source_kind=p.source_kind AND e.source_id=p.source_id); $$;
CREATE FUNCTION economic_source_rejection(company varchar, event_id varchar) RETURNS varchar
LANGUAGE sql STABLE AS $$
 SELECT CASE WHEN EXISTS (SELECT 1 FROM canonical_events e WHERE e.company_id=$1 AND e.id=$2
  AND e.type IN ('external.customer.praise','external.repository.merged','custom.signal.observed')
  AND e.source_kind IN ('MANUAL','GENERIC_WEBHOOK'))
 THEN 'ECONOMIC_EFFECT_NOT_ELIGIBLE' ELSE 'LEGACY_ECONOMIC_SOURCE' END; $$;
CREATE FUNCTION check_source_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM canonical_events e WHERE e.company_id=NEW.company_id AND e.id=NEW.event_id
   AND e.source_kind=NEW.source_kind AND e.source_id=NEW.source_id) THEN
  RAISE EXCEPTION 'Source receipt identity mismatch' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER source_receipt_binding BEFORE INSERT ON source_receipts
FOR EACH ROW EXECUTE FUNCTION check_source_receipt();
CREATE TRIGGER source_receipts_immutable BEFORE UPDATE OR DELETE ON source_receipts
FOR EACH ROW EXECUTE FUNCTION reject_economic_mutation();
CREATE TRIGGER trusted_producers_immutable BEFORE UPDATE OR DELETE ON trusted_producers
FOR EACH ROW EXECUTE FUNCTION reject_economic_mutation();
"""+REPLACE_EFFECT

UNINSTALL_SQL = RESTORE_EFFECT+"""
DROP TRIGGER IF EXISTS source_receipt_binding ON source_receipts;
DROP TRIGGER IF EXISTS source_receipts_immutable ON source_receipts;
DROP TRIGGER IF EXISTS trusted_producers_immutable ON trusted_producers;
DROP FUNCTION IF EXISTS check_source_receipt();
DROP FUNCTION IF EXISTS economic_source_authorized(varchar,varchar);
DROP FUNCTION IF EXISTS economic_source_rejection(varchar,varchar);
DROP FUNCTION IF EXISTS economic_source_legacy_v1(varchar,varchar);
"""
