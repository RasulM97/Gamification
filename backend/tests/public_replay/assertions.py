"""Physical database, isolation, retry and provenance assertions."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading
import sqlalchemy as sa
from app.db import SessionLocal, engine
from app.domain import DomainError
from app.models import User
from app.canonical_events.store import PostgresEventStore
from app.canonical_events.model import CanonicalEvent
from app.rules.service import evaluate_event, get_candidate
from app.rules.model import RuleCandidate
from app.policies.service import evaluate_candidate, get_decision
from app.policies.model import PolicyDecision
from app.approvals.service import decide
from app.approvals.model import ApprovalRequest, ApprovalDecision
from app.economic_effects.service import economic_detail, issue
from app.economic_effects.model import EconomicEffect
from app.economy_position import net_position
from .mapping import envelope


def refused(call, codes):
    try: call()
    except DomainError as exc:
        assert exc.code in codes, exc.code
        return exc.code
    raise AssertionError('Expected refusal')


def burst(call):
    barrier = threading.Barrier(50)
    def run(_):
        barrier.wait(timeout=30)
        return call()
    with ThreadPoolExecutor(max_workers=50) as pool: return list(pool.map(run, range(50)))


def retries(work, records, rows, governed):
    record = next(r for r in records if r['family']=='closed')
    def send():
        response = work.raw(record, 0, source_index=2)
        assert response.status_code == 200
        return response.json()['eventId']
    ids = burst(send)
    assert len(set(ids)) == 1
    for _ in range(10): assert send()==ids[0]
    changed = work.raw(record, 0, source_index=2, override={'payload':{'changed':True}})
    assert changed.status_code==200 and changed.json()['eventId']==ids[0]
    with SessionLocal() as db:
        stored = PostgresEventStore(db).get('real-co-0', ids[0])
        assert stored.payload==envelope(record)['payload']
    def rule_call():
        with SessionLocal() as db:
            value=evaluate_event(db,work.actors[0],ids[0]); db.commit()
            return value['candidateIds'][0]
    candidates=burst(rule_call)
    assert len(set(candidates))==1
    def policy_call():
        with SessionLocal() as db:
            value=evaluate_candidate(db,work.actors[0],candidates[0]); db.commit()
            return value['decisionId']
    decisions=burst(policy_call)
    assert len(set(decisions))==1
    other_source=work.raw(record,0,source_index=1)
    other_tenant=work.raw(record,1,source_index=2)
    assert other_source.status_code==other_tenant.status_code==200
    assert len({ids[0],other_source.json()['eventId'],other_tenant.json()['eventId']})==3
    auth=[]
    for kwargs in [dict(stamp_offset=-600),dict(stamp_offset=600),dict(bad_signature=True)]:
        response=work.raw(record,0,**kwargs)
        assert response.status_code==401
        auth.append(response.status_code)
    validation=[]
    for override in [dict(eventType='invalid'), dict(occurredAt=-1),
                     dict(payload={'oversize':'x'*33000}), dict(payload={'oversize':'x'*17000}),
                     dict(evidence=[{'kind':'public-replay','reference':'r'}]*11),
                     dict(evidence=[{'kind':'public-replay','reference':'r','metadata':{'large':'x'*8300}}])]:
        response=work.raw(record,0,override=override)
        assert 400<=response.status_code<500
        validation.append(response.status_code)
    cross=Counter()
    with SessionLocal() as db:
        for row in rows[:100]:
            other=work.actors[1-row['tenant']]
            refused(lambda:PostgresEventStore(db).get(other.company_id,row['event']),{'NOT_FOUND'})
            cross['events_checked']+=1
            for pair in row['pairs']:
                refused(lambda:get_candidate(db,other,pair['candidate']),{'NOT_FOUND'})
                refused(lambda:get_decision(db,other,pair['decision']),{'NOT_FOUND'})
                cross['candidates_checked']+=1; cross['decisions_checked']+=1
        for value in governed['effects'][:50]:
            refused(lambda:economic_detail(db,work.actors[1-value['tenant']],value['effect']['id']),{'ECONOMIC_EFFECT_NOT_FOUND'})
            cross['effects_checked']+=1
        db.rollback()
        approval=next(a for a in governed['approvals'] if a['mode']=='canonical')
        request=db.get(ApprovalRequest,approval['request'])
        candidate=db.get(RuleCandidate,request.candidate_id)
        event=db.get(CanonicalEvent,candidate.canonical_event_id)
        assert event.subject_id
        subject=db.get(User,event.subject_id)
        refused(lambda:decide(db,subject,request.id,{'decision':'APPROVED'}),{'SELF_APPROVAL_FORBIDDEN'})
        db.rollback()
        # Existing inactive-account authority gate, transaction rolled back after probe.
        actor=db.get(User,work.actors[0].id); actor.active=False; db.flush()
        refused(lambda:decide(db,actor,request.id,{'decision':'APPROVED'}),{'APPROVER_INACTIVE'})
        db.rollback()
    for value in governed['effects'][1:10]:
        with SessionLocal() as db:
            assert issue(db,work.actors[value['tenant']],value['pair']['decision'])['id']==value['effect']['id']
            db.commit()
    return dict(sequential=10,concurrent=50,modified_payload='existing immutable event wins',
        event_rows=1,candidate_rows=1,decision_rows=1,economic_race_workers=50,economic_race_rows=1,
        independent_source_and_tenant_events=3,expected_auth_rejections=len(auth),
        expected_validation_rejections=len(validation),synthetic_perturbations=True,
        cross_tenant=dict(cross,visible=0),self_approval_refusals=1,authority_refusals=1)


def audit(rows, governed):
    samples=Counter()
    with SessionLocal() as db:
        for row in rows:  # Audit every source event/candidate/decision, not just minimum sample.
            event=db.get(CanonicalEvent,row['event'])
            assert event.company_id==f"real-co-{row['tenant']}"
            assert event.payload==row['mapped']['payload'] and event.evidence==row['mapped']['evidence']
            assert event.type==row['mapped']['eventType'] and event.occurred_at==row['mapped']['occurredAt']
            samples['events']+=1
            for pair in row['pairs']:
                candidate=db.get(RuleCandidate,pair['candidate']); decision=db.get(PolicyDecision,pair['decision'])
                assert candidate.canonical_event_id==event.id and candidate.company_id==event.company_id
                assert decision.candidate_id==candidate.id and decision.company_id==event.company_id
                assert decision.effective_decision==pair['outcome']
                assert candidate.data==pair['data'] and candidate.rule_snapshot['name']==pair['rule_name']
                samples['candidates']+=1; samples['decisions']+=1
        for value in governed['approvals']:
            request=db.get(ApprovalRequest,value['request'])
            decision=db.get(PolicyDecision,request.policy_decision_id)
            final=db.scalar(sa.select(ApprovalDecision).where(ApprovalDecision.approval_request_id==request.id))
            assert request.company_id==decision.company_id==final.company_id
            assert request.candidate_id==decision.candidate_id and final.decision==value['status']
            samples['approvals']+=1
        for value in governed['effects']:
            effect=db.get(EconomicEffect,value['effect']['id'])
            decision=db.get(PolicyDecision,effect.policy_decision_id)
            candidate=db.get(RuleCandidate,effect.candidate_id)
            event=db.get(CanonicalEvent,candidate.canonical_event_id)
            assert effect.candidate_id==decision.candidate_id
            assert event.subject_id==effect.beneficiary_user_id
            assert effect.company_id==decision.company_id==event.company_id
            if effect.approval_decision_id:
                final=db.get(ApprovalDecision,effect.approval_decision_id)
                request=db.get(ApprovalRequest,final.approval_request_id)
                assert final.decision=='APPROVED' and request.policy_decision_id==decision.id
            samples['effects']+=1
        # Reuse E7's exact reconciliation SQL without its workload-specific 100-user threshold.
        checks=dict(
            effects='SELECT count(*) FROM economic_effects',
            credits="SELECT count(*) FROM ledger WHERE type='INCENTIVE_REWARD'",
            reversals='SELECT count(*) FROM economic_reversals',
            debits="SELECT count(*) FROM ledger WHERE type='INCENTIVE_REVERSAL'",
            issued='SELECT coalesce(sum(amount),0) FROM economic_effects',
            reversed='SELECT coalesce(sum(amount),0) FROM economic_reversals',
            mismatches='''SELECT count(*) FROM economic_effects e FULL JOIN ledger l ON l.id=e.ledger_transaction_id
                WHERE (l.type='INCENTIVE_REWARD' OR e.id IS NOT NULL) AND
                (e.id IS NULL OR l.id IS NULL OR e.amount<>l.amount OR e.company_id<>l.company_id OR e.beneficiary_user_id<>l.user_id)''',
            reversal_mismatches='''SELECT count(*) FROM economic_reversals r FULL JOIN ledger l ON l.id=r.ledger_transaction_id
                LEFT JOIN economic_effects e ON e.id=r.original_effect_id
                WHERE (l.type='INCENTIVE_REVERSAL' OR r.id IS NOT NULL) AND
                (r.id IS NULL OR l.id IS NULL OR e.id IS NULL OR r.amount<>l.amount OR r.amount<>-e.amount
                 OR r.company_id<>l.company_id OR r.company_id<>e.company_id OR e.beneficiary_user_id<>l.user_id)''',
            duplicates='SELECT count(*) FROM (SELECT candidate_id FROM economic_effects GROUP BY candidate_id HAVING count(*)>1) x',
            deadlocks="SELECT deadlocks FROM pg_stat_database WHERE datname=current_database()")
        result={key:db.scalar(sa.text(sql)) for key,sql in checks.items()}
        assert result['effects']==result['credits'] and result['reversals']==result['debits']
        assert not any(result[key] for key in ('mismatches','reversal_mismatches','duplicates','deadlocks'))
        users=db.execute(sa.text('SELECT company_id,user_id,sum(amount) FROM ledger GROUP BY company_id,user_id')).all()
        assert len(users)>=50
        for company,user,amount in users: assert Decimal(str(net_position(db,company,user)))==amount
        result.update(net=result['issued']+result['reversed'],balance_users=len(users),balance_mismatches=0,amount_variance=0)
    return dict(provenance=dict(samples,broken_chains=0),reconciliation=result)
