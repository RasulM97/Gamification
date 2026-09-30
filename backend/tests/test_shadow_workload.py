"""Three clean runs: real capture adapters and internal production events."""
import copy
import hashlib
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app.models import Company, User, LedgerTransaction
from app.canonical_events.model import CanonicalEvent
from app.github_connector import management
from app.github_connector.delivery import receive
from app.collaboration.appreciation import create as thanks
from app.rules.service import create_rule
from app.rules.model import RuleCandidate
from app.policies.service import create_policy
from app.policies.model import PolicyDecision
from app.shadow.model import ShadowEvaluation
from app.shadow.queries import query, view
from tests.golden.conftest import golden_db
from tests.test_internal_events import headers, rows
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy
from tests.github_helpers import encoded, signed
from tests.test_shadow import positions

FOLDER = Path(__file__).with_name('github_fixtures')
HASHES = []
MODES = ('ALLOW', 'BLOCK', 'REQUIRE_APPROVAL', 'SHADOW_ONLY')


def captures():
    entries = json.loads((FOLDER/'manifest.json').read_text())['fixtures']
    for entry in entries:
        body = (FOLDER/entry['file']).read_bytes()
        assert hashlib.sha256(body).hexdigest() == entry['sha256']
        yield entry, json.loads(body)


@pytest.mark.parametrize('run', [1, 2, 3])
def test_three_clean_shadow_workloads(golden_db, run):
    db = golden_db
    started = time.perf_counter()
    originals = list(captures())
    events, logical_events, auth = [], {}, {}
    for number in range(5):
        company = 'shadow-company-'+str(number)
        db.add(Company(id=company, name='E10 disposable company')); db.flush()
        for suffix, role in [('admin','ADMIN'),('sender','EMPLOYEE'),('recipient','EMPLOYEE')]:
            uid = company+'-'+suffix
            db.add(User(id=uid, company_id=company, name=suffix, role=role,
                        email=uid+'@shadow.invalid', password_hash='disabled'))
        db.commit()
        admin = db.get(User,company+'-admin')
        auth[company] = headers(db, admin.id)
        kinds = [entry['canonicalType'] for entry, _ in originals]+['internal.peer.thanks']
        for kind in kinds:
            for index, mode in enumerate(MODES):
                create_rule(db, admin, rule(name=mode, eventType=kind, conditions=[],
                    outcome={'kind':'INCENTIVE','data':{'proposedReward':(index+1)*10, 'reasonCode':mode}}))
        create_policy(db, admin, policy(decision='ALLOW', priority=999))
        for mode in MODES[1:]:
            create_policy(db, admin, policy(decision=mode, priority=-999,
                conditions=[{'field':'candidate.data.reasonCode','op':'EQ','value':mode}]))
        source = management.create(db,admin,{'name':'E10 frozen capture source','repositoryId':'123'})
        management.mapping(db,admin,source['id'],'20',{'userId':company+'-recipient'})
        db.commit()
        for index in range(50):
            entry, original = originals[index % 5]
            payload = copy.deepcopy(original)
            key = 'pull_request' if entry['eventName']=='pull_request' else 'issue'
            payload[key]['id'] = 10000+index; payload[key]['number'] = index+1
            raw = encoded(payload); metadata = signed(source,raw,index+1,entry['eventName'])
            def deliver():
                return receive(db,source['webhookPath'].rsplit('/',1)[1],metadata['X-GitHub-Delivery'],
                               metadata['X-GitHub-Event'],metadata['X-Hub-Signature-256'],raw)
            first = deliver(); db.commit()
            assert deliver()['eventId'] == first['eventId']; db.commit()
            event = db.get(CanonicalEvent, first['eventId'])
            assert event.company_id == company and event.subject_id == company+'-recipient'
            assert event.type == entry['canonicalType']
            events.append((company,event.id)); logical_events[event.id] = ('github',index)
            item = thanks(db,db.get(User,company+'-sender'),'thanks',dict(
                recipientUserId=company+'-recipient', message='Controlled offline Thanks',submissionId=str(index)))
            db.commit()
            internal = db.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.company_id==company,
                CanonicalEvent.source_event_id==item['id'],CanonicalEvent.type=='internal.peer.thanks'))
            assert internal is not None
            events.append((company,internal.id)); logical_events[internal.id] = ('thanks',index)
        # Existing negative/positive positions prove observation cannot erase debt.
        db.add(LedgerTransaction(company_id=company,user_id=company+'-recipient',
            type='ADMIN_ADJUSTMENT', amount=Decimal(number-2), ref='Pre-shadow position'))
        db.commit()
    before, wallets = rows(), positions(db)
    db.commit()
    client = TestClient(app, raise_server_exceptions=False)
    jobs = events + events[::4]  # 125 complete transaction retries.
    def evaluate(job):
        company, event_id = job
        response = client.post('/api/shadow/events/'+event_id+'/evaluate',headers=auth[company])
        assert response.status_code == 200, response.text
        assert len(response.json()['evaluationIds']) == 4
        return response.json()['evaluationIds']
    evaluation_start = time.perf_counter()
    with ThreadPoolExecutor(20) as pool: results = list(pool.map(evaluate,jobs))
    evaluation_seconds = time.perf_counter()-evaluation_start
    db.expire_all()
    count = lambda model: db.scalar(sa.select(sa.func.count()).select_from(model))
    assert count(CanonicalEvent) == 500
    assert count(RuleCandidate) == count(PolicyDecision) == count(ShadowEvaluation) == 2000
    assert len({sid for group in results for sid in group}) == 2000
    assert positions(db) == wallets
    after = rows()
    excluded = {'rule_candidates','policy_decisions','shadow_evaluations'}
    assert {k:v for k,v in before.items() if k not in excluded} == {k:v for k,v in after.items() if k not in excluded}
    logical, decisions, outcomes, users = [], Counter(), Counter(), set()
    proposed, authorized = Decimal(0), Decimal(0)
    for number in range(5):
        company = 'shadow-company-'+str(number)
        records = db.execute(query(company)).all()
        assert len(records) == 400
        for row in records:
            record = view(row)
            assert row[0].company_id == row[1].company_id == row[2].company_id == company
            assert record['recipientUserId'] == company+'-recipient'
            mode = record['policyDecision']
            assert mode == row[1].data['reasonCode']
            expected = {'ALLOW':('AUTHORIZED','10'), 'BLOCK':('BLOCKED','0'),
                        'REQUIRE_APPROVAL':('PENDING_APPROVAL',None), 'SHADOW_ONLY':('AUTHORIZED','40')}[mode]
            assert (record['outcome'],record['authorizedHypotheticalAmount']) == expected
            proposed += row[0].proposed_amount; authorized += row[0].authorized_amount or 0
            decisions[mode]+=1; outcomes[record['outcome']]+=1; users.add(record['recipientUserId'])
            logical.append((company,logical_events[record['canonicalEventId']],mode,record['governanceState'],
                record['proposedAmount'],record['authorizedHypotheticalAmount'],record['recipientUserId'],record['outcome']))
        foreign = client.get('/api/shadow',headers=auth[company],params={'recipient_id':'gold-admin-a'})
        assert foreign.status_code == 200 and foreign.json()['evaluations'] == []
    assert decisions == Counter({mode:500 for mode in MODES})
    assert proposed == 50000 and authorized == 25000 and len(users) == 5
    digest = hashlib.sha256(json.dumps(sorted(logical),separators=(',',':')).encode()).hexdigest()
    assert not HASHES or all(previous == digest for previous in HASHES)
    HASHES.append(digest)
    report = dict(status='PASS',run=run,companies=5,workers=20,canonicalEvents=500,
        githubEvents=250,internalThanksEvents=250,sourceDeliveryRetries=250,evaluationAttempts=2500,
        candidates=2000,policyDecisions=2000,shadowEvaluations=2000,governance=dict(decisions),
        proposedCoins=str(proposed),authorizedHypotheticalCoins=str(authorized),affectedUsers=len(users),
        duplicateShadowResults=0,accidentalEconomicEffects=0,accidentalLedgerWrites=0,walletDifference=0,
        realApprovalRequests=0,notificationChanges=0,crossTenantLeakage=0,deadlocks=0,unexpected5xx=0,
        logicalHash=digest,evaluationSeconds=round(evaluation_seconds,2),
        evaluationsPerSecond=round(2500/evaluation_seconds,2),totalSeconds=round(time.perf_counter()-started,2))
    output = os.environ.get('CVE_E10_REPORT_DIR')
    if output: (Path(output)/f'e10-workload-{run}.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))
