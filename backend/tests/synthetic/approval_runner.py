"""E6 acceptance: reuse E5.1 STANDARD, then explicitly exercise governance only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import time
from .generator import Config, generate
from .safety import guard


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    url=os.environ.get('CVE_SYNTHETIC_DATABASE_URL','')
    guard(url)  # Before application imports, connections or schema creation.
    os.environ.update(CVE_DATABASE_URL=url,CVE_WEBHOOK_MASTER_KEY=secrets.token_hex(32),
                      CVE_JWT_SECRET=secrets.token_hex(32),CVE_DEV_MODE='false')
    import sqlalchemy as sa
    from fastapi.testclient import TestClient
    from app.db import engine, SessionLocal, logger
    from app.models import User, Base
    from app.security import make_token
    from app.domain import DomainError
    from app.approvals.model import ApprovalRequest, ApprovalDecision
    from app.approvals.service import create_request, decide, list_requests
    from app.policies.model import PolicyDecision
    from app.rules.model import RuleCandidate
    from app.canonical_events.model import CanonicalEvent
    from .workload import Workload
    logger.setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    config=Config(seed=int(os.environ.get('CVE_SYNTHETIC_SEED','20260925')))
    report=dict(status='IN PROGRESS',timestamp=datetime.now(timezone.utc).isoformat(),
                git_commit=os.environ.get('CVE_SYNTHETIC_COMMIT','UNSPECIFIED'),
                command='python -m tests.synthetic.approval_runner '+' '.join(sys.argv[1:]),
                database='cve_synthetic_test',seed=config.seed,workers=config.workers,
                unexpected_errors=0,deadlocks=0)
    started=time.perf_counter()
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)
    try:
        work=Workload(config); work.setup()
        results,source_seconds=work.run(generate(config))
        eligible=[(r,d) for r in results for d in r['decisions'] if d['decision']=='REQUIRE_APPROVAL']
        report.update(source_events=len(results), source_require_approval=len(eligible), source_seconds=source_seconds,
                      direct_allow=sum(d['decision']=='ALLOW' for r in results for d in r['decisions']))
        assert len(eligible)>=1000
        reserved=[pair for pair in eligible if pair[0]['tenant']==0][:100]
        reserved_ids={d['id'] for r,d in reserved}
        selected=[pair for pair in eligible if pair[1]['id'] not in reserved_ids][:900]+reserved
        assert len(reserved)==100 and len(selected)==1000
        print(f'Source pipeline PASS: {len(results)} events; {len(eligible)} REQUIRE_APPROVAL',flush=True)
        reviewers=[]
        with SessionLocal() as db:
            for t in range(config.companies):
                user=User(id=f'syn-reviewer-{t}',company_id=f'syn-co-{t}',name='Synthetic governance reviewer',
                          email=f'reviewer-{t}@synthetic.invalid',role='ADMIN',password_hash='disabled')
                db.add(user); reviewers.append(user)
            db.commit(); db.expunge_all()

        def source_fingerprints():
            with engine.connect() as conn:
                return {name:conn.scalar(sa.text(f'SELECT md5(coalesce(string_agg(md5(t::text), \'\' ORDER BY t::text), \'\')) FROM "{name}" t'))
                        for name in Base.metadata.tables if name not in ('approval_requests','approval_decisions')}
        before=source_fingerprints()
        def create(pair):
            r,d=pair
            with work.metrics.stage('request_creation','approval'), SessionLocal() as db:
                request=create_request(db,work.actors[r['tenant']],d['id']); db.commit()
                return r,request
        t=time.perf_counter()
        with ThreadPoolExecutor(max_workers=config.workers) as pool: requests=list(pool.map(create,selected))
        creation_seconds=time.perf_counter()-t
        for pair,(_,request) in zip(selected[:100],requests[:100]):
            assert create(pair)[1]==request

        def reject(actor,request,expected):
            with SessionLocal() as db:
                try: decide(db,actor,request['id'],{'decision':'APPROVED'})
                except DomainError as exc:
                    assert exc.code==expected; db.rollback()
                else: raise AssertionError('Unauthorized governance succeeded')
        for r,request in requests[:10]:
            with SessionLocal() as db:
                for u in (1,4):
                    reject(db.get(User,f"syn-u-{r['tenant']}-{u}"),request,'APPROVAL_FORBIDDEN')
        self_cases=[(r,q) for r,q in requests if r['mode']=='canonical'][:10]
        for r,request in self_cases: reject(work.actors[r['tenant']],request,'SELF_APPROVAL_FORBIDDEN')
        report.update(role_rejections=20,self_approval_rejections=len(self_cases),duplicate_request_collapses=100)

        def finalize(index):
            r,request=requests[index]
            body={'decision':'APPROVED' if index%10<7 else 'REJECTED','reasonCode':'SYNTHETIC_REVIEW'}
            with work.metrics.stage('decision','approval'), SessionLocal() as db:
                value=decide(db,reviewers[r['tenant']],request['id'],body); db.commit()
                return value
        t=time.perf_counter()
        with ThreadPoolExecutor(max_workers=config.workers) as pool: finals=list(pool.map(finalize,range(900)))
        decision_seconds=time.perf_counter()-t
        for i in range(100): assert finalize(i)==finals[i]
        # One tenant's actual 100-row pending page; no per-row provenance reads.
        t=time.perf_counter(); pending=[]
        with work.metrics.stage('list','approval'),SessionLocal() as db:
            pending=list_requests(db,reviewers[0])['approvals']; db.commit()
        assert len(pending)==100
        report['list_pending_100_seconds']=time.perf_counter()-t

        # A separate 50-way mixed finalization of one still-pending request.
        import threading
        chosen=pending[0]; tenant=int(chosen['companyId'].split('-')[-1])
        auth={'Authorization':'Bearer '+make_token(reviewers[tenant])}
        barrier=threading.Barrier(50)
        def attempt(i):
            barrier.wait(timeout=30)
            with TestClient(__import__('app.main',fromlist=['app']).app,raise_server_exceptions=False) as client:
                return client.post('/api/approvals/'+chosen['id']+'/decision',headers=auth,
                                   json={'decision':'APPROVED' if i%2 else 'REJECTED'})
        with ThreadPoolExecutor(max_workers=50) as pool: responses=list(pool.map(attempt,range(50)))
        assert all(r.status_code in (200,409) for r in responses)
        wins=[r.json() for r in responses if r.status_code==200]
        assert len(wins)==25 and all(r==wins[0] for r in wins)
        report.update(race_conflicts=25,mixed_race_final= wins[0]['status'],unexpected_5xx=0)

        with SessionLocal() as db:
            report['requests_created']=db.scalar(sa.select(sa.func.count()).select_from(ApprovalRequest))
            groups=dict(db.execute(sa.select(ApprovalDecision.decision,sa.func.count()).group_by(ApprovalDecision.decision)).all())
            report.update(approved=groups.get('APPROVED',0),rejected=groups.get('REJECTED',0),pending=99)
            assert report['requests_created']==1000 and sum(groups.values())==901
            # Deterministic spread through the finalized source order.
            for i in range(0,900,9):
                request=db.get(ApprovalRequest,finals[i]['id'])
                terminal=db.get(ApprovalDecision,finals[i]['finalDecision']['id'])
                policy=db.get(PolicyDecision,request.policy_decision_id)
                candidate=db.get(RuleCandidate,request.candidate_id)
                event=db.get(CanonicalEvent,candidate.canonical_event_id)
                assert request.company_id==terminal.company_id==policy.company_id==candidate.company_id==event.company_id
                assert policy.candidate_id==candidate.id and terminal.approval_request_id==request.id
                assert policy.effective_decision=='REQUIRE_APPROVAL' and candidate.rule_version==1
            report['provenance']=dict(sampled_chains=100,broken_chains=0)
        assert source_fingerprints()==before
        report['source_and_business_mutations']=0
        metrics=work.metrics.report()
        report['latency_ms']={k:v for k,v in metrics['latency_ms'].items() if k.startswith('approval.')}
        report['sql']={k:v for k,v in metrics['service_sql'].items() if k.startswith('approval.')}
        assert report['sql']['approval.request_creation']['max']==5
        assert report['sql']['approval.decision']['max']==5
        assert report['sql']['approval.list']['max']==2
        report['throughput_per_second']=dict(request_creation=1000/creation_seconds,decisions=900/decision_seconds)
        report['stage_seconds']=dict(creation=creation_seconds,decision=decision_seconds)
        report['potential_economic_outcomes']=report['direct_allow']+report['approved']
        report['status']='PASS'
    except Exception as exc:
        report['status']='FAIL'; report['unexpected_errors']+=1; report['failure_type']=type(exc).__name__
        if getattr(getattr(exc,'orig',None),'pgcode',None)=='40P01': report['deadlocks']+=1
        raise
    finally:
        report['runtime_seconds']=time.perf_counter()-started
        report['exit_code']=0 if report['status']=='PASS' else 1
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        output.with_suffix('.md').write_text('# E6 executed approval workload\n\nDevelopment measurements only.\n\n```json\n'+json.dumps(report,indent=2)+'\n```\n',encoding='utf-8')
        engine.dispose()
        print(f"{report['status']}: {output}; {report['runtime_seconds']:.3f}s",flush=True)


if __name__=='__main__': main()
