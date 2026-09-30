"""Frozen E10 history guards, shared by create_all and migration replay."""
INSTALL_SQL = """
CREATE FUNCTION reject_shadow_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Shadow history is immutable' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER shadow_evaluations_immutable BEFORE UPDATE OR DELETE ON shadow_evaluations
FOR EACH ROW EXECUTE FUNCTION reject_shadow_mutation();
"""
UNINSTALL_SQL = """
DROP TRIGGER IF EXISTS shadow_evaluations_immutable ON shadow_evaluations;
DROP FUNCTION IF EXISTS reject_shadow_mutation();
"""
