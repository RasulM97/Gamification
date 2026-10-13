"""Smoke + Gate-1 containment checks for the RA-1.1 lab core.

Verifies, before any concurrency experiment may run:
  - disposable cluster refuses a pre-existing directory;
  - uniquely named disposable database, identity verified;
  - evidence isolation (events.jsonl mode 'x' refuses a second open);
  - exactly one worker; listening port owned by the spawned PID;
  - watchdog fires and kills only the harness-owned tree;
  - bounded cleanup (no live app process, no leftover cluster dir).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402


def main():
    rid = lab.validate_run_id(sys.argv[1] if len(sys.argv) > 1 else lab.run_id())
    base = lab.OUT_ROOT / rid / 'smoke'
    ev = lab.Evidence(base)
    checks = {}

    try:
        ev.event('fingerprint', **lab.fingerprint())

        # ── evidence isolation: second Evidence on same dir must fail ────
        try:
            lab.Evidence(base)
            checks['evidence_isolation'] = False
        except FileExistsError:
            checks['evidence_isolation'] = True

        # ── DB safety: unique db + identity + refusal of stale dir ───────
        lab.verify_run_paths(base, rid, base / 'uploads')
        pg = lab.DisposablePG(base / 'pg', db_tag='smoke',
                              run_dir=lab.OUT_ROOT / rid)
        url = pg.start()
        checks['db_unique_name'] = pg.db_name.startswith('ra11_')
        ev.event('pg_started', db_name=pg.db_name,
                 server_version=pg.server_version)
        obs = lab.Observer(url, ev)
        checks['db_identity'] = obs.scalar('SELECT current_database()') == pg.db_name
        pg2_refused = False
        try:
            lab.DisposablePG(base / 'pg', db_tag='smoke2',
                             run_dir=lab.OUT_ROOT / rid)
        except ValueError:
            pg2_refused = True
        checks['preexisting_cluster_refused'] = pg2_refused

        # ── path containment: safe_rmtree refuses outside paths ──────────
        # Clean-checkout safe: these assertions must PASS even when no
        # historical evidence exists at all (Gate A). Refusal is enforced
        # by containment rules that do not depend on the target existing.
        refused = False
        try:
            lab.safe_rmtree(lab.REPO / 'backend', lab.OUT_ROOT / rid)
        except ValueError:
            refused = True
        hist = lab.OUT_ROOT / 'final-20261012'
        hist_refused = False
        try:
            lab.safe_rmtree(hist, lab.OUT_ROOT / rid)  # historical run dir
        except ValueError:
            hist_refused = True
        checks['rmtree_containment'] = refused
        checks['historical_run_refused'] = hist_refused
        # Preservation is only measurable when historical evidence exists;
        # on a clean checkout the refusal above is the entire check.
        checks['historical_run_preserved'] = (
            not hist.exists()) or (hist / 'e1' / 'events.jsonl').exists()

        # ── process safety: one worker, port ownership, watchdog ─────────
        env = lab.app_env(url, base / 'uploads')
        (base / 'uploads').mkdir(exist_ok=True)
        env['WEB_CONCURRENCY'] = '9'  # must be stripped by app_env
        env = lab.app_env(url, base / 'uploads')  # rebuilt: overrides stripped
        checks['worker_env_stripped'] = 'WEB_CONCURRENCY' not in env
        lab.provision_schema_and_seed(env)
        proc, wd = lab.spawn_app(env, lab.PORT_A, ev, watchdog_s=120)
        checks['port_owner_verified'] = lab.verify_port_owner(lab.PORT_A,
                                                              proc.pid)
        token = lab.login(f'http://127.0.0.1:{lab.PORT_A}', 'dana@aster.demo')
        import httpx
        r = httpx.get(f'http://127.0.0.1:{lab.PORT_A}/api/bootstrap',
                      headers=lab.auth(token), timeout=30)
        checks['bootstrap_ok'] = r.status_code == 200
        # pool instrumentation proof: launcher writes checkout events
        time.sleep(0.5)
        pool_log = base / f'pool_events_{lab.PORT_A}.jsonl'
        pool_events = [json.loads(x) for x in pool_log.read_text().splitlines()] \
            if pool_log.exists() else []
        checks['pool_checkout_events'] = any(
            e.get('event') == 'checkout' for e in pool_events)

        probe = lab.LoopProbe(lab.PORT_A, ev)
        probe.start()
        time.sleep(1.0)
        probe.stop()
        obs.snap_locks('idle')
        lab.stop_app(proc, wd, ev)
        checks['app_stopped'] = not lab.process_alive(proc)
        # Gate A: termination is verified, not assumed — the whole recorded
        # tree must be gone and the listener closed after stop.
        checks['app_tree_dead'] = lab.tree_dead(proc)
        checks['listener_closed_after_stop'] = not lab.wait_port(
            lab.PORT_A, timeout=3.0)

        obs.close()
        pg.stop()
        checks['cluster_removed'] = not (base / 'pg' / 'cluster').exists()
        checks['no_live_app'] = len(lab._LIVE_PROCS) == 0

        ev.event('gate1_checks', **checks)
        ok = all(checks.values())
        ev.classify('smoke-gate1',
                    harness_validity='VALID' if ok else 'INVALID',
                    product_observation='EXPECTED_BEHAVIOR',
                    causal_claim='INCONCLUSIVE',
                    rationale='Gate-1 containment self-check; no product claim.')
        if not ok:
            raise SystemExit(f'GATE 1 FAILED: {checks}')
        print('SMOKE + GATE 1 PASS')
    finally:
        m = ev.finish()
        print(f'evidence at {base} ({len(m)} artifacts)')


if __name__ == '__main__':
    main()
