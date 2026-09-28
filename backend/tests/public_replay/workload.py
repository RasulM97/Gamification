"""Explicit offline orchestration, real HTTP HMAC boundary, caller-owned commits."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import threading
import time
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine, SessionLocal
from app.models import Base, Company, User
from app.canonical_events.store import PostgresEventStore
from app.ingestion.service import create_source
from app.ingestion.contracts import RawEvent
from app.ingestion.normalizers import GenericWebhookNormalizer
from app.rules.service import create_rule, evaluate_event
from app.rules.model import RuleCandidate
from app.policies.service import create_policy, evaluate_candidate
from app.approvals.service import create_request, decide
from app.economic_effects.service import issue
from app.economic_effects.reversal import reverse
from app.domain import DomainError
from tests.synthetic.metrics import Metrics
from .mapping import envelope, canonical, rules, policies, expected
from .safety import guard


class Workload:
    def __init__(self, workers):
        guard(engine.url)
        self.workers = workers
        self.metrics = Metrics(engine)
        self.client = TestClient(app, raise_server_exceptions=False)
        self.actors, self.sources = [], []

    def setup(self):
        guard(engine.url)
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(sa.text('TRUNCATE '+', '.join(Base.metadata.tables)+' CASCADE'))
        with SessionLocal() as db:
            for tenant in range(2): db.add(Company(id=f'real-co-{tenant}', name=f'Replay {tenant}'))
            db.flush()
            for tenant in range(2):
                for user in range(61):
                    db.add(User(id=f'real-u-{tenant}-{user}', company_id=f'real-co-{tenant}',
                        name=f'Synthetic replay user {tenant}/{user}', email=f'{tenant}-{user}@replay.invalid',
                        role='ADMIN' if user==0 else 'MANAGER', password_hash='disabled'))
            db.commit()
            for tenant in range(2):
                actor = db.get(User, f'real-u-{tenant}-0')
                self.actors.append(actor)
                self.sources.append([create_source(db, actor, f'Replay source {tenant}/{i}') for i in range(3)])
                for spec in rules(): create_rule(db, actor, spec)
                for spec in policies(): create_policy(db, actor, spec)
                db.commit()
            db.expunge_all()

    def raw(self, record, tenant, source_index=0, override=None, stamp_offset=0, bad_signature=False):
        source = self.sources[tenant][source_index]
        body = envelope(record) | (override or {})
        raw = json.dumps(body, separators=(',', ':')).encode()
        stamp = str(int(time.time())+stamp_offset)
        signature = hmac.new(source['secret'].encode(), stamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        return self.client.post('/api/webhooks/'+source['sourceKey']+'/events', content=raw,
            headers={'Content-Type':'application/json', 'X-CVE-Timestamp':stamp,
                     'X-CVE-Signature':'sha256='+('0'*64 if bad_signature else signature)})

    def persist(self, record, index, mode):
        tenant = index%2
        if mode == 'raw':
            response = self.raw(record, tenant)
            assert response.status_code == 200, f'Unexpected HTTP {response.status_code}'
            return response.json()['eventId']
        with SessionLocal() as db:
            subject = f'real-u-{tenant}-{1+(index//2)%60}' if record['family']=='merged' else None
            event = canonical(record, self.sources[tenant][1]['id'], subject)
            value = PostgresEventStore(db).append(f'real-co-{tenant}', event)
            db.commit()
            return value.id

    def process(self, item):
        index, record, mode = item
        tenant = index%2
        # Pure normalization cost measured separately from full HTTP ingress+commit.
        if mode == 'raw':
            body = envelope(record)
            with self.metrics.stage('normalization', mode):
                GenericWebhookNormalizer(self.sources[tenant][0]['id']).normalize(RawEvent(
                    body['eventType'], body['occurredAt'], body['payload'], body['evidence'], body['sourceEventId']))
        with self.metrics.stage('persistence', mode): value = self.persist(record, index, mode)
        with self.metrics.stage('rules', mode), SessionLocal() as db:
            result = evaluate_event(db, self.actors[tenant], value)
            db.commit()
        count, decision = expected(record)
        assert len(result['candidateIds']) == count and result['invalidCount'] == 0
        pairs = []
        for candidate in result['candidateIds']:
            with self.metrics.stage('policies', mode), SessionLocal() as db:
                pd = evaluate_candidate(db, self.actors[tenant], candidate)
                db.commit()
            with SessionLocal() as db:
                snapshot=db.get(RuleCandidate,candidate)
                data=snapshot.data
                rule_name=snapshot.rule_snapshot['name']
            reward=5 if rule_name=='Replay labeled merge' else 10 if record['family']=='merged' else 20
            assert data==dict(proposedReward=reward,reasonCode='PUBLIC_REPLAY_TEST',approvalHint='MANAGER')
            expected_decision='ALLOW' if rule_name=='Replay labeled merge' else decision
            assert pd['effectiveDecision'] == expected_decision
            assert (pd['explanation']['reason']=='DEFAULT_GOVERNANCE') == (record['family']=='issue_reopened')
            pairs.append(dict(candidate=candidate, decision=pd['decisionId'], outcome=expected_decision,
                              rule_name=rule_name,data=data))
        return dict(index=index, mode=mode, tenant=tenant, family=record['family'], event=value, pairs=pairs,
                    rules_evaluated=len(result['evaluations']),mapped=envelope(record))

    def run(self, records, mode):
        started = time.perf_counter()
        # Reverse capture order intentionally; no provider temporal state is inferred.
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            result = list(pool.map(self.process, [(i,r,mode) for i,r in reversed(list(enumerate(records)))]))
        return sorted(result, key=lambda r:r['index']), time.perf_counter()-started

    def govern(self, results):
        approvals, effects, refusals = [], [], []
        eligible = []
        for row in results:
            for number,pair in enumerate(row['pairs']):
                actor = self.actors[row['tenant']]
                approved = False
                if pair['outcome']=='REQUIRE_APPROVAL':
                    with self.metrics.stage('approval', row['mode']), SessionLocal() as db:
                        request = create_request(db, actor, pair['decision'])
                        db.commit()
                        approved = (row['index']+number)%10 < 7
                        result = decide(db, actor, request['id'], {'decision':'APPROVED' if approved else 'REJECTED'})
                        db.commit()
                    approvals.append(dict(index=row['index'], mode=row['mode'], request=request['id'],
                                          status=result['status']))
                can_issue = row['mode']=='canonical' and row['family']=='merged' and (approved or pair['outcome']=='ALLOW')
                if can_issue:
                    eligible.append((row,pair))
                    if len(effects)>=200: continue
                    if not effects:
                        barrier=threading.Barrier(50)
                        def contested(_):
                            barrier.wait(timeout=30)
                            with SessionLocal() as db:
                                effect = issue(db, actor, pair['decision'])
                                db.commit()
                                return effect['id']
                        with ThreadPoolExecutor(max_workers=50) as pool:
                            ids = list(pool.map(contested, range(50)))
                        assert len(set(ids)) == 1
                with self.metrics.stage('issuance' if can_issue else 'economic_refusal', row['mode']), SessionLocal() as db:
                    try:
                        effect = issue(db, actor, pair['decision'])
                        db.commit()
                    except DomainError as exc:
                        db.rollback()
                        assert not can_issue
                        refusals.append(exc.code)
                    else:
                        assert can_issue
                        effects.append(dict(effect=effect, tenant=row['tenant'], pair=pair, index=row['index']))
        reversals = []
        for value in effects[::10]:
            with SessionLocal() as db:
                result = reverse(db, self.actors[value['tenant']], value['effect']['id'], {'reasonCode':'SOURCE_REVERTED'})
                db.commit()
                assert reverse(db, self.actors[value['tenant']], value['effect']['id'], {'reasonCode':'SOURCE_REVERTED'})==result
                db.commit()
                reversals.append(result)
        assert 100 <= len(effects) <= 250
        return dict(approvals=approvals, effects=effects, refusals=refusals, eligible=len(eligible), reversals=reversals)
