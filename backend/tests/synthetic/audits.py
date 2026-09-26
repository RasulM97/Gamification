"""PostgreSQL, service and authenticated HTTP acceptance probes."""
import random
import sqlalchemy as sa
from app.db import engine, SessionLocal
from app.models import Base
from app.domain import DomainError
from app.canonical_events.model import CanonicalEvent
from app.canonical_events.store import PostgresEventStore
from app.rules.model import RuleCandidate
from app.rules.service import get_candidate, evaluate_event
from app.policies.model import PolicyDecision
from app.policies.service import get_decision, evaluate_candidate
from .generator import rule_specs, policy_specs

OWNED = {'companies', 'users', 'canonical_events', 'rules', 'rule_candidates',
         'policies', 'policy_decisions', 'webhook_sources'}


def business_state():
    with engine.connect() as conn:
        return {name:[dict(row) for row in conn.execute(sa.select(table)).mappings()]
                for name,table in Base.metadata.tables.items() if name not in OWNED}


def counts():
    with engine.connect() as conn:
        return {name:conn.scalar(sa.select(sa.func.count()).select_from(Base.metadata.tables[name]))
                for name in sorted(OWNED)}


def invalid_slice(work, event):
    n = round(work.config.events*work.config.invalid_rate)
    categories = ['malformed_type', 'oversize_payload', 'invalid_evidence', 'bad_shape', 'invalid_rule', 'invalid_policy']
    observed = dict.fromkeys(categories, 0)
    auth = work.headers(event['tenant'])
    for i in range(n):
        category = categories[i % len(categories)]
        if category == 'invalid_rule':
            body = rule_specs()[0] | {'conditions':[dict(field='payload.__class__', op='EQ', value=1)]}
            response = work.client.post('/api/rules', headers=auth, json=body)
        elif category == 'invalid_policy':
            body = policy_specs(0)[0] | {'decision':'AUTO_PAY'}
            response = work.client.post('/api/policies', headers=auth, json=body)
        else:
            overrides = {'malformed_type':{'eventType':'INVALID'},
                         'oversize_payload':{'payload':{'text':'x'*17000}},
                         'invalid_evidence':{'evidence':[{'kind':'link', 'reference':False}]},
                         'bad_shape':{'payload':[]}}
            response = work.raw(event, overrides[category] | {'sourceEventId':f'invalid-{i}'})
        assert response.status_code == 422, (category, response.status_code)
        observed[category] += 1
    assert work.raw(event, bad_signature=True).status_code == 401
    return observed


def isolation(work, results):
    result = next(r for r in results if r['tenant'] == 0 and r['decisions'])
    eid, candidate, decision = result['event_id'], result['decisions'][0]['candidate'], result['decisions'][0]['id']
    paths = [('POST', '/api/rules/evaluate/'+eid), ('POST', '/api/policies/evaluate/'+candidate),
             ('GET', '/api/rules/candidates/'+candidate), ('GET', '/api/policies/decisions/'+decision)]
    before = counts()
    for method,path in paths:
        assert work.client.request(method, path, headers=work.headers(1)).status_code == 404
        for role_user in (1, 4):
            assert work.client.request(method, path, headers=work.headers(0, role_user)).status_code == 403
        assert work.client.request(method, path).status_code == 401
        assert work.client.request(method, path, headers=work.headers(0)).status_code == 200
    with SessionLocal() as db:
        actions = [lambda:PostgresEventStore(db).get('syn-co-1', eid),
                   lambda:evaluate_event(db, work.actors[1], eid),
                   lambda:evaluate_candidate(db, work.actors[1], candidate),
                   lambda:get_candidate(db, work.actors[1], candidate),
                   lambda:get_decision(db, work.actors[1], decision)]
        for action in actions:
            try:
                action()
            except DomainError as exc:
                assert exc.code == 'NOT_FOUND'
                db.rollback()
            else:
                raise AssertionError('Cross-tenant service access succeeded')
        for model, identity in ((RuleCandidate, candidate), (PolicyDecision, decision)):
            row = db.get(model, identity)
            values = {column.name:getattr(row, column.name) for column in model.__table__.columns}
            try:
                with db.begin_nested():
                    db.execute(sa.insert(model).values(values | {'id':'synthetic-foreign', 'company_id':'syn-co-1'}))
            except sa.exc.IntegrityError as exc:
                assert exc.orig.pgcode == '23503'
            else:
                raise AssertionError('Cross-tenant FK insert succeeded')
    assert counts() == before
    return dict(cross_tenant_events_visible=0, cross_tenant_candidates_visible=0,
                cross_tenant_decisions_visible=0, foreign_evaluations_succeeded=0,
                api_probes=20, service_probes=5, foreign_key_probes=2)


def provenance(work, events, results):
    rng = random.Random(work.config.seed+1)
    by_index = {e['index']:e for e in events}
    sampled = rng.sample(results, min(100, len(results)))
    chains = [(r, d) for r in results for d in r['decisions']]
    candidate_sample = rng.sample(chains, min(100, len(chains)))
    decision_sample = rng.sample(chains, min(100, len(chains)))
    with SessionLocal() as db:
        for result in sampled:
            row = db.get(CanonicalEvent, result['event_id'])
            spec = by_index[result['index']]
            assert row.company_id == f"syn-co-{result['tenant']}"
            assert row.payload == spec['payload'] and row.type == spec['type']
            assert row.occurred_at == spec['occurredAt'] and row.received_at > row.occurred_at
        event_chains = [(r, d) for r in sampled for d in r['decisions']]
        for result, decision in event_chains + candidate_sample + decision_sample:
            candidate = db.get(RuleCandidate, decision['candidate'])
            event = db.get(CanonicalEvent, result['event_id'])
            stored = db.get(PolicyDecision, decision['id'])
            assert candidate.company_id == event.company_id == stored.company_id == f"syn-co-{result['tenant']}"
            assert candidate.canonical_event_id == event.id and stored.candidate_id == candidate.id
            assert candidate.rule_id == work.rules[result['tenant']][decision['rule']]['id']
            assert candidate.rule_version == 1 and candidate.rule_snapshot == rule_specs()[decision['rule']]
            assert candidate.data == candidate.rule_snapshot['outcome']['data']
            expected = {p['id']:p for p in work.policies[result['tenant']]}
            assert len(stored.evaluated_policies) == 12
            for policy in stored.evaluated_policies:
                assert policy['version'] == expected[policy['id']]['version'] == 1
                assert policy['definition'] == {k:expected[policy['id']][k] for k in policy['definition']}
            assert stored.effective_decision == decision['decision']
    return dict(events=len(sampled), candidates=len(candidate_sample), decisions=len(decision_sample), broken_references=0)


def immutability(results):
    result = next(r for r in results if r['decisions'])
    d = result['decisions'][0]
    for model, identity, column in ((CanonicalEvent, result['event_id'], 'payload'),
                                   (RuleCandidate, d['candidate'], 'data'),
                                   (PolicyDecision, d['id'], 'explanation')):
        for statement in (sa.update(model).where(model.id == identity).values(**{column:{}}),
                          sa.delete(model).where(model.id == identity)):
            with SessionLocal() as db:
                try:
                    db.execute(statement)
                    db.commit()
                except sa.exc.IntegrityError as exc:
                    assert exc.orig.pgcode == '23514'
                    db.rollback()
                else:
                    raise AssertionError('Protected history mutation succeeded')
    return dict(update_probes=3, delete_probes=3, accepted_mutations=0)
