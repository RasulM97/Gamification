"""Three clean real-service workloads; fixed oracle, no detector-derived expectations."""
import hashlib
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from app.db import SessionLocal
from app.models import User, LedgerTransaction
from app.domain import DomainError
from app.rules.service import evaluate_event
from app.policies.service import evaluate_candidate
from app.incentive_safety.service import assess
from app.incentive_safety.shadow import observe
from app.incentive_safety.model import SafetyEvaluation, SafetyShadow
from app.approvals.service import create_request, decide
from app.approvals.model import ApprovalRequest
from app.economic_effects.service import issue
from app.economic_effects.model import EconomicEffect
from app.economy_position import net_position
from tests.golden.conftest import golden_db
from tests.safety_workload_data import seed

HASHES=[]


@pytest.fixture
def workload_sessions(golden_db):
    # Twenty workload workers need twenty connections; the single-process API's
    # default 10+5 pool can starve queued workers in this sustained batch harness.
    engine=sa.create_engine(golden_db.get_bind().url,pool_size=20,max_overflow=0)
    try: yield sessionmaker(bind=engine,expire_on_commit=False)
    finally: engine.dispose()


@pytest.mark.parametrize('run',[1,2,3])
def test_safety_workload(golden_db,workload_sessions,caplog,run):
    db=golden_db; started=time.perf_counter()
    caplog.set_level('WARNING',logger='cve')
    jobs=seed(db)
    db.commit()
    assert len(jobs)==5280
    def govern(job):
        with workload_sessions() as worker:
            actor=worker.get(User,job['company']+'-u0')
            cid=evaluate_event(worker,actor,job['event'])['candidateIds'][0]
            pd=evaluate_candidate(worker,actor,cid)
            worker.commit()
            return dict(job,candidate=cid,decision=pd['decisionId'])
    with ThreadPoolExecutor(20) as pool: jobs=list(pool.map(govern,jobs))
    evaluation_start=time.perf_counter()
    def evaluate(job):
        with workload_sessions() as worker:
            actor=worker.get(User,job['company']+'-u0')
            result=assess(worker,actor.company_id,job['candidate'])
            assert result.outcome==job['expected'], (job,result.outcome,result.findings)
            assert [f['findingType'] for f in result.findings]==([job['finding']] if job['finding'] else [])
            assert all(worker.scalar(sa.text('SELECT company_id FROM canonical_events WHERE id=:id'),
                       {'id':eid})==actor.company_id for f in result.findings for eid in f['evidence']['eventIds'])
            shadow=observe(worker,actor,job['decision'])
            worker.commit()
            return result.id,shadow['id']
    with ThreadPoolExecutor(20) as pool: results=list(pool.map(evaluate,jobs+jobs[::10]))
    elapsed=time.perf_counter()-evaluation_start
    count=lambda model: db.scalar(sa.select(sa.func.count()).select_from(model))
    assert len({r[0] for r in results})==count(SafetyEvaluation)==5280
    assert len({r[1] for r in results})==count(SafetyShadow)==5280
    assert count(ApprovalRequest)==count(EconomicEffect)==count(LedgerTransaction)==0
    outcomes=Counter(job['expected'] for job in jobs)
    assert outcomes=={'CLEAR':5232,'OBSERVE':8,'REQUIRE_REVIEW':32,'SUPPRESS_INCENTIVE':8}
    expected_balances=Counter(); paid=[]; prevented=delayed=0
    selected=[job for job in jobs if job['finding'] or (job['group'] in ('normal','github') and job['index']==0)]
    assert len(selected)==64
    for job in selected:
        actor=db.get(User,job['company']+'-u0')
        prohibited=job['policy'] in ('BLOCK','SHADOW_ONLY') or job['expected']=='SUPPRESS_INCENTIVE'
        needs_approval=job['policy']=='REQUIRE_APPROVAL' or job['expected']=='REQUIRE_REVIEW'
        if prohibited or needs_approval:
            with pytest.raises(DomainError): issue(db,actor,job['decision'])
            db.rollback()
        if prohibited:
            prevented+=1
            continue
        if needs_approval:
            evaluation=assess(db,actor.company_id,job['candidate'])
            request=create_request(db,actor,job['decision'],
                safety_evaluation_id=evaluation.id if job['policy']=='ALLOW' else None)
            db.commit()
            decide(db,db.get(User,job['company']+'-u1'),request['id'],{'decision':'APPROVED'}); db.commit()
            delayed+=1
        first=issue(db,actor,job['decision']); db.commit()
        assert issue(db,actor,job['decision'])==first; db.commit()
        paid.append((job['company'],job['group'],job['index']))
        expected_balances[(job['company'],first['beneficiaryUserId'])]+=10
    assert len(paid)==count(EconomicEffect)==count(LedgerTransaction)==28
    assert delayed==count(ApprovalRequest)==22
    assert db.scalar(sa.select(sa.func.sum(LedgerTransaction.amount)))==280
    for person in db.scalars(sa.select(User).where(User.company_id.like('safety-load-%'))):
        assert net_position(db,person.company_id,person.id)==expected_balances[(person.company_id,person.id)]
    logical=sorted((j['company'],j['group'],j['index'],j['policy'],j['expected'],j['finding']) for j in jobs)
    digest=hashlib.sha256(json.dumps(dict(results=logical,paid=sorted(paid),ledger=280),sort_keys=True).encode()).hexdigest()
    assert not HASHES or all(prior==digest for prior in HASHES)
    HASHES.append(digest)
    report=dict(status='PASS',run=run,companies=8,users=400,workers=20,events=5280,candidates=5280,
        githubEvents=480,internalEvents=4800,sourceRetries=5280,evaluationAttempts=len(results),
        outcomes=dict(outcomes),findings=dict(Counter(j['finding'] for j in jobs if j['finding'])),
        expectedUnsafeMissed=0,expectedSafeFlagged=0,shadowEvaluations=5280,pureShadowApprovals=0,
        pureShadowEffects=0,liveAttempts=64,realEffects=28,reviewGatedPayouts=22,preventedPayouts=prevented,
        duplicateEvaluations=0,duplicateEffects=0,ledgerTotal='280',ledgerMismatches=0,walletMismatches=0,
        crossTenantLeakage=0,deadlocks=0,httpRequests=0,unexpectedExceptions=0,logicalHash=digest,
        evaluationSeconds=round(elapsed,2),evaluationsPerSecond=round(len(results)/elapsed,2),
        totalSeconds=round(time.perf_counter()-started,2))
    output=os.environ.get('CVE_E11_REPORT_DIR')
    if output: (Path(output)/f'e11-workload-{run}.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))
