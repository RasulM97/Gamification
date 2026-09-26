"""Test-only orchestration using unmodified real services and HTTP boundaries."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import time
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine, SessionLocal
from app.models import Base, Company, User
from app.security import make_token
from app.canonical_events.contracts import EventInput
from app.canonical_events.store import PostgresEventStore
from app.ingestion.service import create_source
from app.rules.service import create_rule, evaluate_event
from app.policies.service import create_policy, evaluate_candidate
from .generator import rule_specs, policy_specs, expected_rules, expected_policies
from .metrics import Metrics
from .safety import guard


class Workload:
    def __init__(self, config):
        guard(engine.url)
        self.config = config
        self.actors, self.sources, self.rules, self.policies = [], [], [], []
        self.client = TestClient(app, raise_server_exceptions=False)
        self.metrics = Metrics(engine)

    def setup(self):
        guard(engine.url)
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(sa.text('TRUNCATE '+', '.join(Base.metadata.tables)+' CASCADE'))
        with SessionLocal() as db:
            for t in range(self.config.companies):
                db.add(Company(id=f'syn-co-{t}', name=f'Synthetic company {t}'))
            db.flush()
            for t in range(self.config.companies):
                for u in range(self.config.users//self.config.companies):
                    role = 'ADMIN' if u == 0 else 'MANAGER' if u < 4 else 'EMPLOYEE'
                    db.add(User(id=f'syn-u-{t}-{u}', company_id=f'syn-co-{t}', name=f'Synthetic user {t}/{u}',
                                email=f'user-{t}-{u}@synthetic.invalid', role=role, password_hash='disabled'))
            db.commit()
            for t in range(self.config.companies):
                actor = db.get(User, f'syn-u-{t}-0')
                self.actors.append(actor)
                self.sources.append(create_source(db, actor, f'Synthetic source {t}'))
                self.rules.append([create_rule(db, actor, spec) for spec in rule_specs()])
                self.policies.append([create_policy(db, actor, spec) for spec in policy_specs(t % 4)])
                db.commit()
            db.expunge_all()

    def headers(self, tenant=0, user=0):
        with SessionLocal() as db:
            return {'Authorization': 'Bearer '+make_token(db.get(User, f'syn-u-{tenant}-{user}'))}

    def raw(self, event, override=None, bad_signature=False):
        source = self.sources[event['tenant']]
        body = dict(eventType=event['type'], sourceEventId=event['payload']['logicalId'],
                    occurredAt=event['occurredAt'], payload=event['payload'])
        body.update(override or {})
        raw = json.dumps(body, separators=(',', ':')).encode()
        stamp = str(int(time.time()))
        signature = hmac.new(source['secret'].encode(), stamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        return self.client.post('/api/webhooks/'+source['sourceKey']+'/events', content=raw,
            headers={'Content-Type':'application/json', 'X-CVE-Timestamp':stamp,
                     'X-CVE-Signature':'sha256='+('0'*64 if bad_signature else signature)})

    def persist(self, event, measured=True):
        if event['mode'] == 'raw':
            response = self.raw(event)
            if response.status_code != 200:
                raise RuntimeError(f'Unexpected HTTP {response.status_code}: webhook')
            return response.json()['eventId']
        with SessionLocal() as db:
            value = EventInput(type=event['type'], schema_version=1, source_kind='INTERNAL',
                source_id='synthetic-internal', source_event_id=event['payload']['logicalId'],
                actor_id=f"syn-u-{event['tenant']}-0", occurred_at=event['occurredAt'], payload=event['payload'])
            result = PostgresEventStore(db).append(f"syn-co-{event['tenant']}", value)
            db.commit()
            return result.id

    def rules_for(self, event, event_id):
        with SessionLocal() as db:
            value = evaluate_event(db, self.actors[event['tenant']], event_id)
            db.commit()
            return value

    def policy_for(self, event, candidate_id):
        with SessionLocal() as db:
            value = evaluate_candidate(db, self.actors[event['tenant']], candidate_id)
            db.commit()
            return value

    def process(self, event):
        start = time.perf_counter()
        mode, tenant = event['mode'], event['tenant']
        with self.metrics.stage('persistence', mode):
            event_id = self.persist(event)
        with self.metrics.stage('rules', mode):
            evaluation = self.rules_for(event, event_id)
        indices = expected_rules(event)
        expected = {self.rules[tenant][i]['id'] for i in indices}
        assert set(evaluation['matchedRules']) == expected
        applicable = sum(s['eventType'] == event['type'] for s in rule_specs())
        assert len(evaluation['evaluations']) == applicable and evaluation['invalidCount'] == 0
        index_by_id = {s['id']:i for i,s in enumerate(self.rules[tenant])}
        decisions = []
        for rule_id, candidate_id in zip(evaluation['matchedRules'], evaluation['candidateIds']):
            expected_matches, expected_decision = expected_policies(event, index_by_id[rule_id])
            with self.metrics.stage('policies', mode):
                decision = self.policy_for(event, candidate_id)
            assert decision['effectiveDecision'] == expected_decision
            assert [(p['id'], p['version'], p['decision']) for p in decision['matchedPolicies']] == [
                (self.policies[tenant][i]['id'], 1, d) for i,d in expected_matches]
            assert (decision['explanation']['reason'] == 'DEFAULT_GOVERNANCE') == (not expected_matches)
            decisions.append(dict(rule=index_by_id[rule_id], candidate=candidate_id,
                                  id=decision['decisionId'], decision=decision['effectiveDecision'],
                                  matches=len(decision['matchedPolicies'])))
        self.metrics.e2e(mode, start)
        return dict(index=event['index'], tenant=tenant, mode=mode, event_id=event_id,
                    applicable=applicable, decisions=sorted(decisions, key=lambda d:d['rule']))

    def run(self, events):
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=self.config.workers) as pool:
            results = list(pool.map(self.process, events))
        return results, time.perf_counter()-start

    def burst(self, event):
        # This event is held out from normal replay so every burst creates its first row.
        import threading
        def parallel(fn):
            barrier = threading.Barrier(50)
            def call(_):
                barrier.wait(timeout=30)
                return fn()
            with ThreadPoolExecutor(max_workers=50) as pool:
                return list(pool.map(call, range(50)))
        ids = parallel(lambda: self.persist(event))
        assert len(set(ids)) == 1
        evaluations = parallel(lambda: self.rules_for(event, ids[0]))
        assert all(len(v['candidateIds']) == 1 for v in evaluations)
        candidates = {v['candidateIds'][0] for v in evaluations}
        assert len(candidates) == 1
        decisions = parallel(lambda: self.policy_for(event, next(iter(candidates))))
        assert len({v['decisionId'] for v in decisions}) == 1
        return {kind:dict(workers=50, attempts=50, rows_created=1, deduped=49)
                for kind in ('events', 'candidates', 'decisions')}
