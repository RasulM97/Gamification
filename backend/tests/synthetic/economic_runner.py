"""E7 acceptance extension of E5.1 STANDARD and the E6 explicit approval lifecycle."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import threading
import time
from .generator import Config, generate
from .safety import guard


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',required=True)
    args=parser.parse_args(); url=os.environ.get('CVE_SYNTHETIC_DATABASE_URL',''); guard(url)
    os.environ.update(CVE_DATABASE_URL=url,CVE_WEBHOOK_MASTER_KEY=secrets.token_hex(32),
                      CVE_JWT_SECRET=secrets.token_hex(32),CVE_DEV_MODE='false')
    import sqlalchemy as sa
    from app.db import engine,SessionLocal,logger
    from app.models import User,LedgerTransaction
    from app.canonical_events.contracts import EventInput
    from app.canonical_events.store import PostgresEventStore
    from app.approvals.service import create_request,decide
    from app.policies.service import update_policy,evaluate_candidate
    from app.economic_effects.contracts import SAFE_EVENT_TYPES
    from app.economic_effects.service import issue
    from app.economic_effects.reversal import reverse
    from app.domain import DomainError
    from .workload import Workload
    from .economic_audits import reconcile
    logger.setLevel(logging.WARNING); logging.getLogger('httpx').setLevel(logging.WARNING)
    config=Config(); started=time.perf_counter()
    report=dict(status='IN PROGRESS',command='python -m tests.synthetic.economic_runner '+' '.join(sys.argv[1:]),
        database='cve_synthetic_test',timestamp=datetime.now(timezone.utc).isoformat(),
        git_commit=os.environ.get('CVE_SYNTHETIC_COMMIT','UNSPECIFIED'),seed=config.seed,workers=config.workers,
        unexpected_errors=0,deadlocks=0,unmodified_baseline_eligible=0,
        adaptation='Reuse E5.1 generated payloads/rules/policies. Safe canonical slice becomes MANUAL with explicit subjects before persistence. Actual raw webhook slice remains subjectless. Policy oracle uses non-INTERNAL mode for MANUAL.')
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)

    class EconomicWorkload(Workload):
        def persist(self,event,measured=True):
            if not event.get('economic_manual'): return super().persist(event,measured)
            tenant=event['tenant']; user=1+(event['index']//config.companies)%39
            with SessionLocal() as db:
                stored=PostgresEventStore(db).append(f'syn-co-{tenant}',EventInput(
                    type=event['type'],schema_version=1,source_kind='MANUAL',source_id=f'syn-u-{tenant}-0',
                    source_event_id=event['payload']['logicalId'],actor_id=f'syn-u-{tenant}-0',
                    subject_id=f'syn-u-{tenant}-{user}',occurred_at=event['occurredAt'],payload=event['payload']))
                db.commit(); return stored.id
    try:
        work=EconomicWorkload(config); work.setup()
        events=generate(config)
        for event in events:
            event['economic_manual']=event['mode']=='canonical' and event['type'] in SAFE_EVENT_TYPES
            if event['economic_manual']: event['mode']='raw'  # independent oracle: source is non-INTERNAL
        results,seconds=work.run(events)
        report.update(source_events=len(results),source_seconds=seconds,
            source_governance=dict(Counter(d['decision'] for r in results for d in r['decisions'])),
            manual_events=sum(e['economic_manual'] for e in events))
        print('E7 source pipeline persisted: '+str(report['source_governance']),flush=True)
        pairs=[(r,d) for r in results for d in r['decisions']]
        require=[pair for pair in pairs if pair[1]['decision']=='REQUIRE_APPROVAL' and events[pair[0]['index']]['economic_manual']]
        def approve(pair):
            r,d=pair; actor=work.actors[r['tenant']]
            with work.metrics.stage('approval','economic'),SessionLocal() as db:
                request=create_request(db,actor,d['id']); db.commit()
                result=decide(db,actor,request['id'],{'decision':'APPROVED'}); db.commit()
                return result
        with ThreadPoolExecutor(max_workers=config.workers) as pool: approvals=list(pool.map(approve,require))
        eligible=[pair for pair in pairs if events[pair[0]['index']]['economic_manual'] and pair[1]['decision'] in ('ALLOW','REQUIRE_APPROVAL')]
        assert len({d['candidate'] for r,d in eligible})==len(eligible)
        report.update(approved=len(approvals),eligible_unique_candidates=len(eligible),
            source_eligible_governance_outcomes=len(approvals)+sum(d['decision']=='ALLOW' for r,d in pairs))
        # No weakened gate: every source/governance rejection is exercised.
        rejected=Counter()
        for r,d in pairs:
            if events[r['index']]['economic_manual'] and d['decision'] in ('ALLOW','REQUIRE_APPROVAL'): continue
            with SessionLocal() as db:
                try: issue(db,work.actors[r['tenant']],d['id'])
                except DomainError as exc: rejected[exc.code]+=1; db.rollback()
                else: raise AssertionError('Ineligible synthetic candidate paid')
        report['blocked']=dict(rejected)
        # Known existing debt, with no auxiliary settlement ledger or wallet.
        with SessionLocal() as db:
            for t in range(config.companies):
                for u in range(1,40):
                    db.add(LedgerTransaction(company_id=f'syn-co-{t}',user_id=f'syn-u-{t}-{u}',
                        type='ADMIN_ADJUSTMENT',amount=Decimal(-7),ref='synthetic initial debt'))
            db.commit()
        report['debt_users']=312
        # Re-evaluate eligible histories after a non-decision policy edit.
        with SessionLocal() as db:
            for t in range(config.companies): update_policy(db,work.actors[t],work.policies[t][0]['id'],{'priority':100})
            db.commit()
        histories=[]
        for r,d in eligible[:20]:
            with SessionLocal() as db:
                newer=evaluate_candidate(db,work.actors[r['tenant']],d['candidate']); db.commit()
                alternate=(r,dict(d,id=newer['decisionId'],decision=newer['effectiveDecision']))
                assert alternate[1]['id']!=d['id']
            if alternate[1]['decision']=='REQUIRE_APPROVAL': approve(alternate)
            histories.append(alternate)
        report['multiple_eligible_histories']=len(histories)
        def execute(pair,stage='issue'):
            r,d=pair
            with work.metrics.stage(stage,'economic'),SessionLocal() as db:
                effect=issue(db,work.actors[r['tenant']],d['id']); db.commit(); return effect
        barrier=threading.Barrier(50)
        def contested(i): barrier.wait(timeout=30); return execute(eligible[0] if i%2 else histories[0],'contention')
        t=time.perf_counter()
        with ThreadPoolExecutor(max_workers=50) as pool: race=list(pool.map(contested,range(50)))
        assert len({e['id'] for e in race})==1
        report['contention']=dict(workers=50,attempts=50,effects=1,seconds=time.perf_counter()-t)
        t=time.perf_counter()
        with ThreadPoolExecutor(max_workers=config.workers) as pool: issued=list(pool.map(execute,eligible))
        issue_seconds=time.perf_counter()-t
        assert len({e['id'] for e in issued})==len(eligible)
        for pair in histories+eligible[:100]: execute(pair,'retry')
        reversals=[]
        def undo(pair):
            i,e=pair
            with work.metrics.stage('reverse','economic'),SessionLocal() as db:
                value=reverse(db,work.actors[int(e['companyId'].split('-')[-1])],e['id'],{'reasonCode':'SOURCE_REVERTED'})
                db.commit(); return value
        subset=[(i,e) for i,e in enumerate(issued) if i%10==0]
        t=time.perf_counter()
        with ThreadPoolExecutor(max_workers=config.workers) as pool: reversals=list(pool.map(undo,subset))
        reverse_seconds=time.perf_counter()-t
        for pair in subset[:20]: undo(pair)
        report.update(processed=len(eligible),issued=len(issued),reversals=len(reversals),
            duplicate_collapses=50+len(histories)+min(100,len(eligible))+min(20,len(subset)),
            throughput_per_second=dict(issue=len(issued)/issue_seconds,reverse=len(reversals)/reverse_seconds),
            reconciliation=reconcile(),**work.metrics.report(),status='PASS',exit_code=0)
        report['economic_sql_hotspots_seconds']=[dict(category=key,seconds=round(value,3))
            for key,value in work.metrics.sql_time.most_common()
            if key.split(':',1)[0] in ('issue','reverse','contention')][:10]
        print('Economic reconciliation PASS: '+str(report['reconciliation']),flush=True)
    except Exception as exc:
        report.update(status='FAIL',exit_code=1,error_type=type(exc).__name__,unexpected_errors=1)
        raise
    finally:
        report['runtime_seconds']=time.perf_counter()-started
        output.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
        output.with_suffix('.md').write_text('# E7 economic execution\n\nDevelopment measurement; no production SLA.\n\n```json\n'+json.dumps(report,indent=2,default=str)+'\n```\n',encoding='utf-8')


if __name__=='__main__': main()
