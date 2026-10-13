"""E1 part B — isolated mechanism experiments (category B, labeled latches).

B1: PostgreSQL advisory-lock fair queueing using the app's REAL lock
    function (organization.lock): S holder -> X waiter -> new S requester
    must queue BEHIND the pending X waiter. This is the accumulation step of
    the Day-1 chain, proven deterministically with a labeled latch.

B2: Dynamic capture of the actual lock set a real bootstrap transaction
    holds (org SHARED advisory via can_view on scoped tasks) and a real
    claim command transaction holds — mid-transaction pg_locks snapshots,
    no code modification. Real claim lock order (verified against
    task_services.claim_task @ this commit): org EXCLUSIVE advisory
    (exclusive_guarded) -> task row FOR UPDATE (get_task, lock=True) ->
    org SHARED advisory (can_view/admit, redundant under the held X) ->
    user FOR NO KEY UPDATE (require_capacity). The capability check
    (@requires) is a lock-free SELECT — it takes NO advisory lock.

Every injected wait is labeled 'latch' in the evidence record.

Gate C: the classification is DERIVED from actual thread outcomes — both
threads must reach their acquisition boundaries, both must finish (a join
timeout is an explicit failure outcome, never silent proof), the actual
acquisition order is verified, and a B2 capture error invalidates the run.
An unfinished participant cannot count as proof of fair queueing.
"""
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402
import _decisions as D  # noqa: E402

RID = lab.validate_run_id(sys.argv[1])
BASE = lab.OUT_ROOT / RID / 'e1b'
ev = lab.Evidence(BASE)
ev.event('fingerprint', **lab.fingerprint())

pg = lab.DisposablePG(BASE / 'pg', db_tag='e1b',
                     run_dir=lab.OUT_ROOT / RID)
UPLOAD = BASE / 'uploads'
UPLOAD.mkdir(parents=True, exist_ok=True)

obs = None
try:
    url = pg.start()
    env = lab.app_env(url, UPLOAD)
    for k, v in env.items():
        if k.startswith('CVE_') or k in ('PYTHONPATH', 'XDG_RUNTIME_DIR'):
            os.environ[k] = v
    os.environ['CVE_DATABASE_URL'] = url
    os.environ['CVE_UPLOAD_DIR'] = str(UPLOAD)
    os.environ['CVE_DEV_MODE'] = 'true'

    sys.path.insert(0, str(lab.BACKEND))
    from app.db import SessionLocal, engine  # noqa: E402
    from app.models import Base, Company, User  # noqa: E402
    import app.models  # noqa: E402
    # register all model modules (same list as _boot.py)
    import app.capabilities.model  # noqa: F401,E402
    import app.organization.model  # noqa: F401,E402
    import app.canonical_events.model  # noqa: F401,E402
    import app.ingestion.model  # noqa: F401,E402
    import app.rules.model  # noqa: F401,E402
    import app.policies.model  # noqa: F401,E402
    import app.approvals.model  # noqa: F401,E402
    import app.economic_effects.model  # noqa: F401,E402
    import app.collaboration.model  # noqa: F401,E402
    import app.github_connector.model  # noqa: F401,E402
    import app.slack_connector.model  # noqa: F401,E402
    import app.notifications.model  # noqa: F401,E402
    import app.shadow.model  # noqa: F401,E402

    Base.metadata.create_all(engine)
    from app.seed import run as seed_run
    with SessionLocal() as db:
        seed_run(db)
        db.commit()

    obs = lab.Observer(url, ev)

    # ── B1: advisory fair queueing (labeled latch) ────────────────────────
    from app.organization import service as org

    s1 = SessionLocal()  # org S holder
    org.lock(s1, 'co-aster')  # shared
    ev.event('latch', step='B1-T1-holds-org-S')
    obs.snap_locks('B1-T1-holds-S')

    t2_state = {}
    t3_state = {}
    thread_errors = []

    def t2():
        s2 = SessionLocal()
        try:
            t2_state['waiting_at'] = time.perf_counter()
            org.lock(s2, 'co-aster', exclusive=True)
            t2_state['acquired_at'] = time.perf_counter()
            ev.event('latch', step='B1-T2-acquired-org-X')
            time.sleep(0.3)
            s2.rollback()  # release X
        except Exception as e:
            # unexpected exception: recorded, and it invalidates B1
            thread_errors.append(f'T2: {type(e).__name__}: {str(e)[:200]}')
            try:
                s2.rollback()
            except Exception:
                pass
        finally:
            s2.close()

    def t3():
        time.sleep(0.4)  # ensure T2's X request is queued first (labeled latch)
        s3 = SessionLocal()
        try:
            t3_state['waiting_at'] = time.perf_counter()
            ev.event('latch', step='B1-T3-requests-org-S-while-X-pending')
            obs.snap_locks('B1-X-pending-T3-about-to-request-S')
            org.lock(s3, 'co-aster')
            t3_state['acquired_at'] = time.perf_counter()
            ev.event('latch', step='B1-T3-acquired-org-S')
            s3.rollback()
        except Exception as e:
            thread_errors.append(f'T3: {type(e).__name__}: {str(e)[:200]}')
            try:
                s3.rollback()
            except Exception:
                pass
        finally:
            s3.close()

    th2 = threading.Thread(target=t2)
    th3 = threading.Thread(target=t3)
    th2.start()
    time.sleep(0.4)  # labeled latch: let T2's X request queue
    obs.snap_locks('B1-T2-X-pending')
    th3.start()
    time.sleep(1.0)  # T1 still holding S; if fair queueing holds, T3 waits
    obs.snap_locks('B1-T1-still-holding')
    ev.event('B1_states_before_release',
             t2_acquired='acquired_at' in t2_state,
             t3_acquired='acquired_at' in t3_state)
    s1.rollback()  # T1 releases S
    ev.event('latch_released', step='B1-T1-released-org-S',
             note='persistence/ordering measured only after latch release')
    s1.close()
    th2.join(timeout=15)
    th3.join(timeout=15)
    b1_finished = {'t2': not th2.is_alive(), 't3': not th3.is_alive()}
    # Gate C: an unfinished participant can never count as proof of fair
    # queueing; the acquisition order is verified from recorded timestamps.
    b1_order_verified = ('acquired_at' in t2_state and 'acquired_at' in t3_state
                         and t3_state['acquired_at'] > t2_state['acquired_at'])
    b1 = {
        't2_boundary': 'waiting_at' in t2_state,
        't3_boundary': 'waiting_at' in t3_state,
        't2_acquired': 'acquired_at' in t2_state,
        't3_acquired': 'acquired_at' in t3_state,
        't2_finished': b1_finished['t2'],
        't3_finished': b1_finished['t3'],
        't3_waited_behind_pending_x': (
            # fair queueing: T3's compatible ShareLock must NOT be granted
            # while T2's ExclusiveLock is pending (see states_before_release
            # and the pg_locks snapshots), and X must acquire before S.
            'acquired_at' not in t3_state
            or t3_state.get('acquired_at', 0) > t2_state.get('acquired_at', 0)),
        'order_verified': b1_order_verified,
        'exceptions': thread_errors,
    }
    ev.event('B1_result',
             t2_acquired_at=t2_state.get('acquired_at'),
             t3_acquired_at=t3_state.get('acquired_at'),
             threads_finished=b1_finished,
             thread_errors=thread_errors,
             order_verified=b1_order_verified,
             t3_waited_behind_pending_X=b1['t3_waited_behind_pending_x'])

    # ── B2: real lock sets mid-transaction ────────────────────────────────
    from app.serializers import bootstrap
    from app.models import Task
    from app.organization.model import Team, TeamMembership
    from sqlalchemy import select

    # fixture: scoped tasks for this company
    with SessionLocal() as db:
        team = Team(company_id='co-aster', name='E1B Scope Team')
        db.add(team)
        db.flush()
        db.add(TeamMembership(company_id='co-aster', team_id=team.id,
                              user_id='u-priya'))
        now = 0
        from app.models import now_ms
        now = now_ms()
        for i in range(25):
            db.add(Task(company_id='co-aster', title=f'E1B {i}', description='',
                        priority='NORMAL', deadline=None, reward=1,
                        audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                        assignee_id=None, status='OPEN', owner_id=None,
                        cycle=1, verified=0, reported=0, paid=0,
                        created_at=now, updated_at=now, created_by='u-marcus',
                        team_id=team.id))
        db.commit()

    db = SessionLocal()
    company = db.get(Company, 'co-aster')
    viewer = db.get(User, 'u-priya')
    b2 = {'bootstrap_captured': False, 'claim_captured': False,
          'claim_error': None}
    try:
        bootstrap(db, company, viewer=viewer)
        obs.snap_locks('B2-bootstrap-tx-open')  # locks held until commit/rollback
        b2['bootstrap_captured'] = True
    except Exception as e:
        b2['bootstrap_error'] = repr(e)
        ev.event('B2_bootstrap_error', error=repr(e))
    finally:
        db.rollback()
        db.close()

    # claim command lock set: call the real decorated service, keep tx open
    from app.task_services import claim_task
    db = SessionLocal()
    actor = db.get(User, 'u-priya')
    task_id = db.scalar(select(Task.id).where(Task.company_id == 'co-aster',
                                              Task.status == 'OPEN',
                                              Task.team_id.is_(None)).limit(1))
    try:
        claim_task(db, actor, task_id)  # org X -> task row U -> user NKU
        obs.snap_locks('B2-claim-tx-open')
        b2['claim_captured'] = True
        db.rollback()
    except Exception as e:
        b2['claim_error'] = repr(e)
        ev.event('B2_claim_error', error=repr(e))
        db.rollback()
    db.close()

    # Gate C: classification DERIVED from actual thread/capture outcomes.
    verdict = D.decide_e1b(b1, b2)
    ev.classify(
        'e1b',
        harness_validity=verdict['harness_validity'],
        product_observation=verdict['product_observation'],
        causal_claim=verdict['causal_claim'],
        rationale=('PostgreSQL advisory fair queueing with the app\'s real '
                   'organization.lock (labeled latches, released before '
                   'ordering was measured); real bootstrap/claim lock sets '
                   'captured mid-transaction. This proves the queueing '
                   'mechanism, not the full wedge by itself. '
                   + ' '.join(verdict['reasons'])),
        fair_queueing_proven=verdict['fair_queueing_proven'],
        b1=b1, b2={k: v for k, v in b2.items()})
    ev.event('e1_partB_done')
finally:
    if obs:
        obs.close()
    pg.stop()
    ev.finish()
    print('E1 part B evidence at', BASE)
