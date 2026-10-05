"""Integrated economic ownership, debt and concurrent historical authority."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
import sqlalchemy as sa
from app.db import SessionLocal
from app.domain import DomainError
from app.models import User, LedgerTransaction
from app.canonical_events.model import CanonicalEvent
from app.organization import service as org
from app.approvals import service as approvals
from app.economic_effects import service as economics
from app.economic_effects.reversal import reverse
from app.economic_effects.model import EconomicEffect, EconomicReversal
from app.economy_position import net_position, balance_of, debt_of
from app.rules import service as rules
from app.policies import service as policies
from app.reward_services import admin_adjust
from app.task_services import create_task, claim_task, submit_work, approve_work
from tests.approval_helpers import approval_db, golden_db
from tests.test_organization import actor, context, thanks
from tests.test_system_integration_flows import configure, govern, review_and_pay, count
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy


def test_overlapping_projects_do_not_union_rule_or_policy_scope(approval_db):
    db = approval_db
    first, second = context(db), context(db)
    # Identical participants belong to both Projects; explicit event context wins.
    for scope, amount, decision in [(first, 3, 'ALLOW'), (second, 9, 'BLOCK')]:
        rules.create_rule(db, actor(db), rule(eventType='internal.peer.thanks', conditions=[], scope=scope,
            outcome={'kind': 'INCENTIVE', 'data': {'proposedReward': amount}}))
        policies.create_policy(db, actor(db), policy(eventType='internal.peer.thanks', scope=scope, decision=decision))
    db.commit()
    for scope, key, expected in [(first, 'first', 'ALLOW'), (second, 'second', 'BLOCK')]:
        event = thanks(db, scope, key=key)
        matches = rules.evaluate_event(db, actor(db), event.id)['candidateIds']
        db.commit()
        assert len(matches) == 1
        pd = policies.evaluate_candidate(db, actor(db), matches[0])
        db.commit()
        assert pd['effectiveDecision'] == expected
        if expected == 'ALLOW':
            assert economics.issue(db, actor(db), pd['decisionId'])['amount'] == '3'
            db.commit()
        else:
            with pytest.raises(DomainError):
                economics.issue(db, actor(db), pd['decisionId'])
            db.rollback()
    assert count(db, EconomicEffect) == 1 and net_position(db, 'gold-a', 'ap-employee') == 3


def test_task_and_generic_incentive_share_wallet_without_double_paying_task(approval_db):
    db = approval_db
    scope = context(db)
    task = create_task(db, actor(db), title='Review', description='', priority='NORMAL',
        deadline=None, reward=7, audience='EMPLOYEES', assign_mode='SPECIFIC_EMPLOYEE',
        assignee_id='ap-employee', context=scope)
    db.commit()
    claim_task(db, actor(db, 'ap-employee'), task.id)
    submit_work(db, actor(db, 'ap-employee'), task.id, note_text='Complete')
    approve_work(db, actor(db, 'org-manager'), task.id)
    db.commit()
    event = db.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.type == 'internal.task.approved'))
    configure(db, event.type, scope)
    _, pd, _ = govern(db, event)
    with pytest.raises(DomainError):
        economics.issue(db, actor(db), pd['decisionId'])
    db.rollback()
    assert net_position(db, 'gold-a', 'ap-employee') == 7
    configure(db, 'internal.peer.thanks', scope)
    _, pd, _ = govern(db, thanks(db, scope))
    effect = economics.issue(db, actor(db), pd['decisionId'])
    db.commit()
    assert net_position(db, 'gold-a', 'ap-employee') == 17
    admin_adjust(db, actor(db), user_id='ap-employee', amount=-15, reason='Controlled adjustment')
    db.commit()
    reverse(db, actor(db), effect['id'], {'reasonCode': 'ADMIN_CORRECTION'})
    db.commit()
    assert net_position(db, 'gold-a', 'ap-employee') == -8
    assert balance_of(db, 'gold-a', 'ap-employee') == 0
    assert debt_of(db, 'gold-a', 'ap-employee') == 8
    assert org.event_scope(db, 'gold-a', event.id) == scope


def test_twenty_way_issue_retry_races_reversal_after_scoped_review(approval_db):
    db = approval_db
    scope = context(db)
    configure(db, 'internal.peer.thanks', scope, outcome='REQUIRE_REVIEW')
    _, pd, assessment = govern(db, thanks(db, scope))
    effect = review_and_pay(db, pd, assessment)
    barrier = Barrier(20)

    def work(index):
        with SessionLocal() as worker:
            barrier.wait(timeout=20)
            try:
                if index % 2:
                    result = reverse(worker, actor(worker), effect['id'], {'reasonCode': 'INVALIDATED'})
                else:
                    result = economics.issue(worker, actor(worker), pd['decisionId'])
                worker.commit()
                return result['id']
            except DomainError as exc:
                worker.rollback()
                assert index % 2 == 0 and exc.code == 'ECONOMIC_EFFECT_ALREADY_REVERSED'
                return exc.code

    with ThreadPoolExecutor(20) as pool:
        results = list(pool.map(work, range(20)))
    assert len(set(results[1::2])) == 1
    assert count(db, EconomicEffect) == count(db, EconomicReversal) == 1
    assert count(db, LedgerTransaction) == 2 and net_position(db, 'gold-a', 'ap-employee') == 0


def test_project_closure_during_approval_preserves_historical_governance(approval_db):
    db = approval_db
    scope = context(db)
    configure(db, 'internal.peer.thanks', scope, outcome='REQUIRE_REVIEW')
    event = thanks(db, scope)
    _, pd, assessment = govern(db, event)
    req = approvals.create_request(db, actor(db), pd['decisionId'], safety_evaluation_id=assessment.id)
    db.commit()
    started = Event()
    with SessionLocal() as writer, ThreadPoolExecutor(1) as pool:
        org.close(writer, actor(writer), scope)

        def decide():
            with SessionLocal() as worker:
                started.set()
                result = approvals.decide(worker, actor(worker, 'org-manager'), req['id'], {'decision': 'APPROVED'})
                worker.commit()
                return result

        future = pool.submit(decide)
        try:
            assert started.wait(10)
            assert not future.done()
        finally:
            writer.commit()
        # Closure blocks new activity, not review of already captured historical work.
        assert future.result(timeout=20)['status'] == 'APPROVED'
    economics.issue(db, actor(db), pd['decisionId'])
    db.commit()
    assert org.event_scope(db, 'gold-a', event.id) == scope


@pytest.mark.parametrize('attack', ['foreign_tenant', 'employee', 'unrelated_manager', 'stale_manager', 'missing', 'malformed'])
def test_scoped_safety_review_rejects_invalid_authority_without_economics(approval_db, attack):
    db = approval_db
    scope = context(db)
    configure(db, 'internal.peer.thanks', scope, outcome='REQUIRE_REVIEW')
    _, pd, assessment = govern(db, thanks(db, scope))
    req = approvals.create_request(db, actor(db), pd['decisionId'], safety_evaluation_id=assessment.id)
    db.commit()
    who = {'foreign_tenant': 'gold-admin-b', 'employee': 'ap-employee', 'unrelated_manager': 'ap-manager'}.get(attack, 'org-manager')
    if attack == 'stale_manager':
        stale = actor(db, who)
        org.membership(db, actor(db), scope, who, {'active': False, 'manager': False})
        db.commit()
    else:
        stale = actor(db, who)
    with pytest.raises(DomainError):
        approvals.decide(db, stale, 'missing' if attack == 'missing' else req['id'],
            {'decision': ['APPROVED']} if attack == 'malformed' else {'decision': 'APPROVED'})
    db.rollback()
    with pytest.raises(DomainError):
        economics.issue(db, actor(db), pd['decisionId'])
    db.rollback()
    assert count(db, EconomicEffect) == count(db, LedgerTransaction) == 0
