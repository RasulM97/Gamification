"""E7 v1 database guards. Keep this revision's SQL stable for migration replay."""
INSTALL_SQL = """
CREATE FUNCTION reject_economic_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Economic history is immutable' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER economic_effects_immutable BEFORE UPDATE OR DELETE ON economic_effects
FOR EACH ROW EXECUTE FUNCTION reject_economic_mutation();
CREATE TRIGGER economic_reversals_immutable BEFORE UPDATE OR DELETE ON economic_reversals
FOR EACH ROW EXECUTE FUNCTION reject_economic_mutation();

CREATE FUNCTION protect_economic_ledger() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='UPDATE' OR OLD.type IN ('INCENTIVE_REWARD','INCENTIVE_REVERSAL')
    OR coalesce(current_setting('cve.legacy_workspace_reset_company',true),'')<>OLD.company_id THEN
    RAISE EXCEPTION 'Ledger history is immutable' USING ERRCODE='23514';
  END IF;
  RETURN OLD;
END; $$;
CREATE TRIGGER economic_ledger_immutable BEFORE UPDATE OR DELETE ON ledger
FOR EACH ROW EXECUTE FUNCTION protect_economic_ledger();

CREATE FUNCTION check_economic_effect() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM rule_candidates c
    JOIN canonical_events e ON e.id=c.canonical_event_id AND e.company_id=c.company_id
    JOIN policy_decisions p ON p.id=NEW.policy_decision_id AND p.company_id=c.company_id AND p.candidate_id=c.id
    WHERE c.id=NEW.candidate_id AND c.company_id=NEW.company_id AND c.kind='INCENTIVE'
      AND e.subject_id=NEW.beneficiary_user_id
      AND e.type IN ('external.customer.praise','external.repository.merged','custom.signal.observed')
      AND ((e.source_kind='MANUAL' AND e.actor_id IS NOT NULL AND e.source_id=e.actor_id)
        OR (e.source_kind='GENERIC_WEBHOOK' AND EXISTS (SELECT 1 FROM webhook_sources w WHERE w.id=e.source_id AND w.company_id=e.company_id)))
      AND jsonb_typeof(c.data->'proposedReward')='number'
      AND (c.data->>'proposedReward')::numeric=NEW.amount
      AND ((p.effective_decision='ALLOW' AND NEW.approval_decision_id IS NULL)
        OR (p.effective_decision='REQUIRE_APPROVAL' AND EXISTS (
          SELECT 1 FROM approval_decisions a JOIN approval_requests r ON r.id=a.approval_request_id AND r.company_id=a.company_id
          WHERE a.id=NEW.approval_decision_id AND a.company_id=NEW.company_id AND a.decision='APPROVED'
            AND r.policy_decision_id=p.id AND r.candidate_id=c.id)))) THEN
    RAISE EXCEPTION 'Invalid economic governance provenance' USING ERRCODE='23514';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM ledger l WHERE l.id=NEW.ledger_transaction_id
    AND l.company_id=NEW.company_id AND l.user_id=NEW.beneficiary_user_id
    AND l.type='INCENTIVE_REWARD' AND l.amount=NEW.amount
    AND l.ref='economic:' || NEW.candidate_id
    AND l.params->>'economicEffectId'=NEW.id AND l.params->>'candidateId'=NEW.candidate_id) THEN
    RAISE EXCEPTION 'Economic effect requires matching ledger credit' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER economic_effect_complete AFTER INSERT ON economic_effects
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_economic_effect();

CREATE FUNCTION check_economic_reversal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM economic_effects e JOIN ledger l ON l.id=NEW.ledger_transaction_id
    WHERE e.id=NEW.original_effect_id AND e.company_id=NEW.company_id AND NEW.amount=-e.amount
      AND l.company_id=e.company_id AND l.user_id=e.beneficiary_user_id AND l.amount=NEW.amount
      AND l.type='INCENTIVE_REVERSAL' AND l.ref='economic-reversal:' || e.id
      AND l.params->>'economicEffectId'=e.id AND l.params->>'economicReversalId'=NEW.id) THEN
    RAISE EXCEPTION 'Reversal requires matching original and ledger debit' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER economic_reversal_complete AFTER INSERT ON economic_reversals
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_economic_reversal();

CREATE FUNCTION check_economic_ledger() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.type='INCENTIVE_REWARD' AND NOT EXISTS (
    SELECT 1 FROM economic_effects e WHERE e.ledger_transaction_id=NEW.id AND e.company_id=NEW.company_id
      AND e.amount=NEW.amount AND e.beneficiary_user_id=NEW.user_id) THEN
    RAISE EXCEPTION 'Incentive credit requires economic provenance' USING ERRCODE='23514';
  ELSIF NEW.type='INCENTIVE_REVERSAL' AND NOT EXISTS (
    SELECT 1 FROM economic_reversals r WHERE r.ledger_transaction_id=NEW.id AND r.company_id=NEW.company_id AND r.amount=NEW.amount) THEN
    RAISE EXCEPTION 'Incentive debit requires reversal provenance' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER economic_ledger_complete AFTER INSERT ON ledger
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_economic_ledger();
"""

UNINSTALL_SQL = """
DROP TRIGGER IF EXISTS economic_ledger_complete ON ledger;
DROP TRIGGER IF EXISTS economic_ledger_immutable ON ledger;
DROP TRIGGER IF EXISTS economic_reversal_complete ON economic_reversals;
DROP TRIGGER IF EXISTS economic_effect_complete ON economic_effects;
DROP TRIGGER IF EXISTS economic_reversals_immutable ON economic_reversals;
DROP TRIGGER IF EXISTS economic_effects_immutable ON economic_effects;
DROP FUNCTION IF EXISTS check_economic_ledger();
DROP FUNCTION IF EXISTS check_economic_reversal();
DROP FUNCTION IF EXISTS check_economic_effect();
DROP FUNCTION IF EXISTS protect_economic_ledger();
DROP FUNCTION IF EXISTS reject_economic_mutation();
"""
