"""Append-only recommendation history, also installed by the additive migration."""
INSTALL_SQL = """
CREATE FUNCTION cve_task_recommendation_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Task recommendation history is immutable' USING ERRCODE = '23514';
END $$;
CREATE TRIGGER task_recommendation_immutable BEFORE UPDATE OR DELETE ON task_recommendations
FOR EACH ROW EXECUTE FUNCTION cve_task_recommendation_immutable();
"""
UNINSTALL_SQL = """
DROP TRIGGER IF EXISTS task_recommendation_immutable ON task_recommendations;
DROP FUNCTION IF EXISTS cve_task_recommendation_immutable();
"""
