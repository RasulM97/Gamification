"""Frozen E11 approval/economic provenance extension. Accounting SQL is retained."""
from ..source_authority.schema import REPLACE_EFFECT as E80_EFFECT

OLD_GOVERNANCE = """((p.effective_decision='ALLOW' AND NEW.approval_decision_id IS NULL)
        OR (p.effective_decision='REQUIRE_APPROVAL' AND EXISTS (
          SELECT 1 FROM approval_decisions a JOIN approval_requests r ON r.id=a.approval_request_id AND r.company_id=a.company_id
          WHERE a.id=NEW.approval_decision_id AND a.company_id=NEW.company_id AND a.decision='APPROVED'
            AND r.policy_decision_id=p.id AND r.candidate_id=c.id)))"""
assert E80_EFFECT.count(OLD_GOVERNANCE)==1

RESTORE_APPROVAL = """
CREATE OR REPLACE FUNCTION check_approval_eligibility() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM policy_decisions WHERE id=NEW.policy_decision_id
  AND company_id=NEW.company_id AND candidate_id=NEW.candidate_id AND effective_decision='REQUIRE_APPROVAL') THEN
  RAISE EXCEPTION 'Approval requires matching REQUIRE_APPROVAL provenance' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
"""

INSTALL_SQL = """
CREATE FUNCTION safety_lock(company varchar,candidate varchar) RETURNS void LANGUAGE sql VOLATILE AS $$
 SELECT pg_advisory_xact_lock(hashtextextended('cve-safety:' || $1 || ':' || $2,0)); $$;

CREATE FUNCTION check_safety_head() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous_sequence bigint; next_sequence bigint;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Safety authority cannot be erased' USING ERRCODE='23514'; END IF;
 PERFORM safety_lock(NEW.company_id,NEW.candidate_id);
 IF TG_OP='UPDATE' THEN
  IF NEW.company_id<>OLD.company_id OR NEW.candidate_id<>OLD.candidate_id THEN
   RAISE EXCEPTION 'Safety authority identity is fixed' USING ERRCODE='23514'; END IF;
  SELECT sequence INTO previous_sequence FROM incentive_safety_evaluations WHERE id=OLD.evaluation_id;
  SELECT sequence INTO next_sequence FROM incentive_safety_evaluations WHERE id=NEW.evaluation_id;
  IF next_sequence<previous_sequence THEN
   RAISE EXCEPTION 'Safety authority cannot move backwards' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER safety_head_guard BEFORE INSERT OR UPDATE OR DELETE ON incentive_safety_heads
FOR EACH ROW EXECUTE FUNCTION check_safety_head();

CREATE OR REPLACE FUNCTION check_approval_eligibility() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE policy_outcome varchar;
BEGIN
 PERFORM safety_lock(NEW.company_id,NEW.candidate_id);
 SELECT effective_decision INTO policy_outcome FROM policy_decisions WHERE id=NEW.policy_decision_id
  AND company_id=NEW.company_id AND candidate_id=NEW.candidate_id;
 IF NEW.trigger='POLICY' AND NEW.safety_evaluation_id IS NULL AND policy_outcome='REQUIRE_APPROVAL' THEN RETURN NEW; END IF;
 IF NEW.trigger='INCENTIVE_SAFETY' AND policy_outcome='ALLOW' AND EXISTS (
  SELECT 1 FROM incentive_safety_evaluations e JOIN incentive_safety_heads h
   ON h.company_id=e.company_id AND h.candidate_id=e.candidate_id AND h.evaluation_id=e.id
  WHERE e.id=NEW.safety_evaluation_id AND e.company_id=NEW.company_id
   AND e.candidate_id=NEW.candidate_id AND e.outcome='REQUIRE_REVIEW') THEN RETURN NEW; END IF;
 RAISE EXCEPTION 'Approval requires exact eligible governance provenance' USING ERRCODE='23514';
END; $$;

CREATE FUNCTION safety_economic_authorized(company varchar,candidate varchar,policy_id varchar,safety_id varchar,approval_id varchar)
RETURNS boolean LANGUAGE plpgsql VOLATILE AS $$
DECLARE current_id varchar; safety_outcome varchar; policy_outcome varchar;
BEGIN
 PERFORM safety_lock(company,candidate);
 SELECT h.evaluation_id,e.outcome INTO current_id,safety_outcome FROM incentive_safety_heads h
  JOIN incentive_safety_evaluations e ON e.id=h.evaluation_id AND e.company_id=h.company_id AND e.candidate_id=h.candidate_id
  WHERE h.company_id=$1 AND h.candidate_id=$2;
 IF current_id IS DISTINCT FROM safety_id OR safety_outcome='SUPPRESS_INCENTIVE' THEN RETURN false; END IF;
 IF current_id IS NULL AND EXISTS (SELECT 1 FROM incentive_safety_settings WHERE company_id=$1) THEN RETURN false; END IF;
 SELECT effective_decision INTO policy_outcome FROM policy_decisions WHERE company_id=$1 AND candidate_id=$2 AND id=$3;
 IF policy_outcome='ALLOW' AND coalesce(safety_outcome,'CLEAR')<>'REQUIRE_REVIEW' THEN
  RETURN approval_id IS NULL;
 ELSIF policy_outcome='ALLOW' AND safety_outcome='REQUIRE_REVIEW' THEN
  RETURN EXISTS (SELECT 1 FROM approval_decisions a JOIN approval_requests r
   ON r.id=a.approval_request_id AND r.company_id=a.company_id
   WHERE a.id=$5 AND a.company_id=$1 AND a.decision='APPROVED' AND r.policy_decision_id=$3
    AND r.candidate_id=$2 AND r.trigger='INCENTIVE_SAFETY' AND r.safety_evaluation_id=$4);
 ELSIF policy_outcome='REQUIRE_APPROVAL' THEN
  RETURN EXISTS (SELECT 1 FROM approval_decisions a JOIN approval_requests r
   ON r.id=a.approval_request_id AND r.company_id=a.company_id
   WHERE a.id=$5 AND a.company_id=$1 AND a.decision='APPROVED' AND r.policy_decision_id=$3
    AND r.candidate_id=$2 AND r.trigger='POLICY' AND r.safety_evaluation_id IS NULL);
 END IF;
 RETURN false;
END; $$;
""" + E80_EFFECT.replace(OLD_GOVERNANCE,
    'safety_economic_authorized(NEW.company_id,NEW.candidate_id,NEW.policy_decision_id,NEW.safety_evaluation_id,NEW.approval_decision_id)')

UNINSTALL_SQL = E80_EFFECT + RESTORE_APPROVAL + """
DROP FUNCTION IF EXISTS safety_economic_authorized(varchar,varchar,varchar,varchar,varchar);
DROP TRIGGER IF EXISTS safety_head_guard ON incentive_safety_heads;
DROP FUNCTION IF EXISTS check_safety_head();
DROP FUNCTION IF EXISTS safety_lock(varchar,varchar);
"""
