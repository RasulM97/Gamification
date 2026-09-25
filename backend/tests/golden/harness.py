"""Replay fixed inputs through real production services; compare logical fields."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import hashlib
import hmac
import json
from pathlib import Path
import time
import pytest
import sqlalchemy as sa
from app.canonical_events.contracts import EventInput
from app.canonical_events.model import CanonicalEvent
from app.canonical_events.store import PostgresEventStore
from app.db import SessionLocal
from app.domain import DomainError
from app.ingestion.service import create_source, webhook_event
from app.models import Base, User
from app.rules.model import Rule, RuleCandidate
from app.rules.service import create_rule, evaluate_event, get_candidate, update_rule

ROOT = Path(__file__).parent / 'scenarios'


def load_scenarios():
    scenarios = []
    for path in sorted(ROOT.rglob('*.json')):
        scenarios.append(json.loads(path.read_text(encoding='utf-8')))
    ids = [s['id'] for s in scenarios]
    assert len(ids) == len(set(ids)), 'Duplicate Golden scenario ID'
    return scenarios


def same(expected, actual):
    # JSON has one numeric group; PostgreSQL Float may return 10.0 for input 10.
    # Bool must still differ from number, including inside nested dictionaries.
    if type(expected) in (int, float) and type(actual) in (int, float):
        return Decimal(str(expected)) == Decimal(str(actual))
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return expected.keys() == actual.keys() and all(same(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(same(e, a) for e, a in zip(expected, actual))
    return expected == actual


def check(scenario, field, expected, actual):
    left = json.dumps(expected, sort_keys=True, ensure_ascii=False)
    right = json.dumps(actual, sort_keys=True, ensure_ascii=False)
    if not same(expected, actual):
        def short(value):
            return value if len(value) <= 1400 else value[:1400] + '…'
        pytest.fail(f"{scenario['id']} :: {field}\nexpected: {short(left)}\nactual:   {short(right)}", pytrace=False)


def business_state(db):
    excluded = {'rules', 'rule_candidates', 'canonical_events', 'webhook_sources'}
    return {name: [dict(row) for row in db.execute(sa.select(table).order_by(*table.primary_key)).mappings()]
            for name, table in Base.metadata.tables.items() if name not in excluded}


def event_projection(event):
    return {key: getattr(event, key) for key in ('company_id', 'type', 'schema_version',
        'source_kind', 'source_event_id', 'occurred_at', 'payload', 'evidence', 'actor_id', 'subject_id')}


def replay(scenario, db):
    expected = scenario['expected']
    before = business_state(db)
    actors = {t: db.get(User, 'gold-admin-'+t) for t in ('a', 'b')}
    errors, refs, definitions = [], {}, {}
    for entry in scenario['rules']:
        try:
            with db.begin_nested():
                created = create_rule(db, actors[entry['tenant']], deepcopy(entry['definition']))
                # Fixed test-only IDs make priority ties reviewable, not random.
                row = db.get(Rule, created['id'])
                row.id = entry['ref']; db.flush()
                refs[row.id] = entry['ref']
                definitions[entry['ref']] = deepcopy(entry['definition'])
        except DomainError as exc:
            errors.append({'stage': 'rule', 'ref': entry['ref'], 'code': exc.code})
    db.commit()
    source = None
    incoming = scenario['input']
    if incoming['kind'] == 'webhook':
        source = create_source(db, actors[incoming['tenant']], 'Synthetic Golden source')
        db.commit()

    def ingest():
        if source is None:
            return PostgresEventStore(db).append('gold-'+incoming['tenant'], EventInput(**incoming['event']))
        raw = json.dumps(incoming['raw'], separators=(',', ':')).encode()
        timestamp = str(int(time.time()))
        digest = hmac.new(source['secret'].encode(), timestamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        result = webhook_event(db, source['sourceKey'], timestamp, 'sha256='+digest, raw)
        return PostgresEventStore(db).get('gold-'+incoming['tenant'], result['eventId'])

    try:
        event = ingest(); db.commit()
    except DomainError as exc:
        db.rollback()
        errors.append({'stage': 'ingestion', 'code': exc.code})
        check(scenario, 'errors', expected['errors'], errors)
        check(scenario, 'canonical event', expected['canonical'], None)
        check(scenario, 'persisted events', 0, db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent)))
        check(scenario, 'candidates', expected['candidates'], [])
        check(scenario, 'matched rules', expected['matchedRules'], [])
        check(scenario, 'non-matched rules', expected['nonMatchedRules'], [])
        check(scenario, 'persisted candidates', 0, db.scalar(sa.select(sa.func.count()).select_from(RuleCandidate)))
        check(scenario, 'business effects', before, business_state(db))
        return
    check(scenario, 'canonical event', expected['canonical'], event_projection(event))
    if source is not None:
        check(scenario, 'source link', source['id'], event.source_id)
    event_before = asdict(event)
    check(scenario, 'automatic candidates', 0, db.scalar(sa.select(sa.func.count()).select_from(RuleCandidate)))
    if scenario.get('duplicateInput'):
        check(scenario, 'duplicate input ID', event.id, ingest().id); db.commit()
        check(scenario, 'duplicate event count', 1, db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent)))
    actor = actors[scenario.get('evaluateAs', incoming['tenant'])]
    actor_id = actor.id  # Resolve expired ORM state before starting worker threads.

    def evaluate_once():
        with SessionLocal() as worker:
            current_actor = worker.get(User, actor_id)
            result = evaluate_event(worker, current_actor, event.id)
            worker.commit()
            return result

    try:
        if scenario.get('concurrent'):
            with ThreadPoolExecutor(max_workers=20) as pool:
                results = list(pool.map(lambda _: evaluate_once(), range(20)))
        else:
            results = [evaluate_once() for _ in range(scenario.get('evaluations', 1))]
    except DomainError as exc:
        errors.append({'stage': 'evaluation', 'code': exc.code})
        results = []
    candidates = []
    if not results:
        check(scenario, 'matched rules', expected['matchedRules'], [])
        check(scenario, 'non-matched rules', expected['nonMatchedRules'], [])
    for result in results:
        check(scenario, 'matched rules', expected['matchedRules'], [refs[r] for r in result['matchedRules']])
        check(scenario, 'non-matched rules', expected['nonMatchedRules'],
              [refs[r['ruleId']] for r in result['evaluations'] if r['status'] == 'NOT_MATCHED'])
        check(scenario, 'invalid count', 0, result['invalidCount'])
        check(scenario, 'stable candidate IDs', results[0]['candidateIds'], result['candidateIds'])
    if results:
        for cid in results[0]['candidateIds']:
            candidate = get_candidate(db, actor, cid)
            check(scenario, 'candidate event link', event.id, candidate['canonicalEventId'])
            check(scenario, 'rule snapshot', definitions[candidate['ruleId']], candidate['ruleSnapshot'])
            candidates.append({'rule': refs[candidate['ruleId']], 'ruleVersion': candidate['ruleVersion'],
                'kind': candidate['kind'], 'data': candidate['data'], 'status': candidate['status'], 'event': scenario['id']})
    check(scenario, 'candidates', expected['candidates'], candidates)
    if scenario.get('foreignRead'):
        try:
            get_candidate(db, actors['b'], results[0]['candidateIds'][0])
        except DomainError as exc:
            errors.append({'stage': 'candidateRead', 'code': exc.code})
        else:
            pytest.fail(scenario['id']+': foreign candidate read succeeded')
    if 'update' in scenario:
        historical = deepcopy(get_candidate(db, actor, results[0]['candidateIds'][0]))
        patch = scenario['update']
        update_rule(db, actor, patch['rule'], patch['patch']); db.commit()
        check(scenario, 'no automatic replay', len(candidates), db.scalar(sa.select(sa.func.count()).select_from(RuleCandidate)))
        new_result = evaluate_once()
        new_candidates = []
        for cid in new_result['candidateIds']:
            candidate = get_candidate(db, actor, cid)
            check(scenario, 'updated event link', event.id, candidate['canonicalEventId'])
            new_candidates.append({'rule': candidate['ruleId'], 'ruleVersion': candidate['ruleVersion'],
                'kind': candidate['kind'], 'data': candidate['data'], 'status': candidate['status'], 'event': scenario['id']})
        check(scenario, 'updated candidates', expected['afterUpdate'], new_candidates)
        check(scenario, 'historical candidate unchanged', historical, get_candidate(db, actor, historical['id']))
        candidates += new_candidates
    check(scenario, 'errors', expected['errors'], errors)
    check(scenario, 'persisted candidate count', len(candidates), db.scalar(sa.select(sa.func.count()).select_from(RuleCandidate)))
    check(scenario, 'event immutability', event_before, asdict(PostgresEventStore(db).get(event.company_id, event.id)))
    check(scenario, 'business effects', before, business_state(db))
