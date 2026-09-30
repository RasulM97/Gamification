"""Offline verification and bounded workload derived from real E9 deliveries."""
import copy
import hashlib
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import Company, User, LedgerTransaction
from app.github_connector import management
from app.github_connector.model import GithubDelivery, GithubSource
from app.canonical_events.model import CanonicalEvent
from app.source_authority.model import SourceReceipt
from app.rules.service import create_rule, evaluate_event
from app.rules.model import RuleCandidate
from app.policies.service import create_policy, evaluate_candidate
from app.policies.model import PolicyDecision
from app.approvals.service import create_request, decide
from app.economic_effects.service import issue
from app.economic_effects.reversal import reverse
from app.economic_effects.model import EconomicEffect
from app.economy_position import net_position
from app.domain import DomainError
from tests.github_helpers import encoded, signed
from tests.golden.conftest import golden_db
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy

FOLDER = Path(__file__).with_name('github_fixtures')
MANIFEST = json.loads((FOLDER / 'manifest.json').read_text())


def specimens():
    values = []
    for entry in MANIFEST['fixtures']:
        body = (FOLDER / entry['file']).read_bytes()
        assert hashlib.sha256(body).hexdigest() == entry['sha256']
        assert 0 < entry['originalBytes'] <= 32768
        values.append((entry, json.loads(body)))
    return values


def test_real_capture_privacy_and_provenance():
    assert len(specimens()) == 5
    forbidden = {'email', 'login', 'avatar_url', 'body', 'title', 'token', 'secret', 'signature'}
    def inspect(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    for entry, value in specimens():
        inspect(value)
        assert len(entry['providerBodySha256']) == 64
        assert entry['providerDeliveryId'] and entry['rawId'] and entry['canonicalId']


def test_real_capture_connector_workload(golden_db):
    db = golden_db
    started = time.monotonic()
    modes = ['ALLOW', 'BLOCK', 'REQUIRE_APPROVAL', 'SHADOW_ONLY']
    sources = []
    for index, tenant in enumerate('abcd'):
        company = 'gold-' + tenant
        if tenant in 'cd':
            db.add(Company(id=company, name='E9 offline ' + tenant))
            db.flush()
            db.add(User(id='gold-admin-' + tenant, company_id=company, name='Test Admin',
                        email=tenant+'@e9.invalid', role='ADMIN', password_hash='disabled'))
            db.flush()
        actor = db.get(User, 'gold-admin-' + tenant)
        participant = 'e9-participant-' + tenant
        db.add(User(id=participant, company_id=company, name='Test participant',
                    email=participant+'@e9.invalid', role='EMPLOYEE', password_hash='disabled'))
        db.flush()
        create_rule(db, actor, rule(eventType='github.pull_request.merged', conditions=[],
                    outcome={'kind': 'INCENTIVE', 'data': {'proposedReward': 10}}))
        create_policy(db, actor, policy(eventType='github.pull_request.merged', decision=modes[index]))
        for instance in range(2):
            source = management.create(db, actor, {'name': 'Frozen capture replay', 'repositoryId': '123'})
            management.mapping(db, actor, source['id'], '20', {'userId': participant})
            sources.append((tenant, source))
        db.commit()

    captures = specimens()
    jobs = []
    for tenant, source in sources:
        supported = []
        for number in range(100):
            entry, original = captures[number % 5]
            value = copy.deepcopy(original)
            key = 'pull_request' if entry['eventName'] == 'pull_request' else 'issue'
            value[key]['id'] = 10000 + number
            value[key]['number'] = number + 1
            job = (tenant, source, number+1, entry['eventName'], encoded(value), 'supported', entry['canonicalType'])
            supported.append(job)
        jobs.extend(supported)
        jobs.extend(supported[:50])
        for number in range(20):
            jobs.append((tenant, source, 1001+number, 'ping', encoded({'repository': {'id': 123},
                         'action': 'ping_'+chr(97+number)}), 'unsupported', None))
        for number in range(10):
            jobs.append((tenant, source, 2001+number, 'issues', b'{'+b' '*number, 'malformed', None))
        for number in range(20):
            jobs.append((tenant, source, 3001+number, 'issues', encoded(captures[0][1]), 'invalid', None))
    # Fixed interleaving exercises multiple tenants/source instances concurrently.
    jobs = [jobs[(i % 8)*200 + i//8] for i in range(1600)]
    client = TestClient(app, raise_server_exceptions=False)

    def deliver(job):
        tenant, source, number, event, body, kind, expected = job
        headers = signed(source, body, number, event)
        if kind == 'invalid':
            headers['X-Hub-Signature-256'] = 'sha256=' + '0'*64
        response = client.post(source['webhookPath'], content=body, headers=headers)
        assert response.status_code == {'supported': 200, 'unsupported': 200,
                                         'malformed': 422, 'invalid': 401}[kind], response.text
        result = response.json()
        if kind == 'supported':
            with SessionLocal() as worker:
                event_row = worker.get(CanonicalEvent, result['eventId'])
                assert event_row.company_id == 'gold-'+tenant and event_row.source_id == source['id']
                assert event_row.type == expected and event_row.subject_id == 'e9-participant-'+tenant
                actor = worker.get(User, 'gold-admin-'+tenant)
                ids = evaluate_event(worker, actor, event_row.id)['candidateIds']
                worker.commit()
                assert len(ids) == (1 if expected.endswith('.merged') else 0)
        return result.get('category', 'ACCEPTED')

    with ThreadPoolExecutor(20) as pool:
        categories = Counter(pool.map(deliver, jobs))
    count = lambda model: db.scalar(sa.select(sa.func.count()).select_from(model))
    assert count(GithubSource) == 8
    assert count(GithubDelivery) == 960 and count(CanonicalEvent) == 800
    assert count(SourceReceipt) == 800 and count(RuleCandidate) == 160
    assert categories['DUPLICATE_DELIVERY'] == 400
    outcomes = Counter()
    effect_ids = []
    for candidate in db.scalars(sa.select(RuleCandidate).order_by(RuleCandidate.id)).all():
        tenant = candidate.company_id[-1]
        actor = db.get(User, 'gold-admin-'+tenant)
        decision = evaluate_candidate(db, actor, candidate.id)
        db.commit()
        mode = modes['abcd'.index(tenant)]
        outcomes[mode] += 1
        if mode != 'ALLOW':
            try:
                issue(db, actor, decision['decisionId'])
            except DomainError:
                db.rollback()
            else:
                raise AssertionError('Governance did not block issuance')
        if mode == 'REQUIRE_APPROVAL':
            request = create_request(db, actor, decision['decisionId'])
            db.commit()
            decide(db, actor, request['id'], {'decision': 'APPROVED'})
            db.commit()
        if mode in ('ALLOW', 'REQUIRE_APPROVAL'):
            first = issue(db, actor, decision['decisionId'])
            db.commit()
            again = issue(db, actor, decision['decisionId'])
            db.commit()
            assert first['id'] == again['id']
            effect_ids.append((tenant, first['id']))
    assert outcomes == Counter({mode: 40 for mode in modes})
    assert count(PolicyDecision) == 160 and count(EconomicEffect) == 80
    assert count(LedgerTransaction) == 80
    for tenant in 'abcd':
        assert net_position(db, 'gold-'+tenant, 'e9-participant-'+tenant) == (400 if tenant in 'ac' else 0)
    reversed_by_tenant = Counter()
    for tenant, identity in effect_ids[:8]:
        reverse(db, db.get(User, 'gold-admin-'+tenant), identity, {'reasonCode': 'SOURCE_REVERTED'})
        db.commit()
        reversed_by_tenant[tenant] += 10
    for tenant in 'abcd':
        expected = (400 if tenant in 'ac' else 0) - reversed_by_tenant[tenant]
        assert net_position(db, 'gold-'+tenant, 'e9-participant-'+tenant) == expected
    assert count(LedgerTransaction) == 88
    assert db.scalar(sa.select(sa.func.sum(LedgerTransaction.amount))) == 720
    report = dict(status='PASS', deliveries=1600, workers=20, companies=4, sources=8,
                  acceptedRawEvents=960, canonicalEvents=800, rejected=240, duplicates=400,
                  ruleCandidates=160, policyDecisions=160, governance=dict(outcomes),
                  effects=80, reversals=8, ledgerRows=88, netAmount='720',
                  duplicateEvents=0, duplicateEffects=0, ledgerMismatches=0,
                  crossTenantLeakage=0, unexpected5xx=0, deadlocks=0,
                  elapsedSeconds=round(time.monotonic()-started, 2))
    output = os.environ.get('CVE_E9_WORKLOAD_REPORT')
    if output:
        Path(output).write_text(json.dumps(report, indent=2)+'\n')
