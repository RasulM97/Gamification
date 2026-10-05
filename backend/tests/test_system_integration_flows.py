"""Combined production paths. No inserted decisions, fake Safety outcomes or payouts."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from app.models import User, LedgerTransaction
from app.domain import DomainError
from app.canonical_events.model import CanonicalEvent
from app.organization import service as org
from app.collaboration import appreciation, help as help_service
from app.github_connector import attribution
from app.rules import service as rules
from app.rules.model import RuleCandidate
from app.policies import service as policies
from app.policies.model import PolicyDecision
from app.incentive_safety import service as safety, shadow
from app.incentive_safety.contracts import DEFAULTS
from app.incentive_safety.model import SafetyEvaluation
from app.approvals import service as approvals
from app.approvals.model import ApprovalRequest
from app.economic_effects import service as economics
from app.economic_effects.model import EconomicEffect
from app.economic_effects.reversal import reverse
from app.economy_position import net_position
from app.capabilities.service import update as capability
from tests.approval_helpers import approval_db, golden_db
from tests.github_helpers import github, deliver
from tests.test_github_real_captures import specimens
from tests.test_organization import context, actor, thanks
from tests.test_rule_evaluator import rule
from tests.policy_helpers import policy


def count(db, model):
    return db.scalar(sa.select(sa.func.count()).select_from(model))


def configure(db, event_type, scope, decision='ALLOW', outcome='CLEAR'):
    settings = deepcopy(DEFAULTS)
    if outcome != 'CLEAR':
        settings['ACTOR_VELOCITY'].update(threshold=1, outcome=outcome)
    safety.update_settings(db, actor(db), settings)
    rules.create_rule(db, actor(db), rule(eventType=event_type, conditions=[], scope=scope,
        outcome={'kind': 'INCENTIVE', 'data': {'proposedReward': 10, 'approvalHint': 'MANAGER'}}))
    policies.create_policy(db, actor(db), policy(eventType=event_type, scope=scope, decision=decision))
    if decision == 'SHADOW_ONLY':
        policies.create_policy(db, actor(db), policy(eventType=event_type, scope=scope, decision='ALLOW'))
    db.commit()


def govern(db, event):
    cid = rules.evaluate_event(db, actor(db), event.id)['candidateIds'][0]
    db.commit()
    pd = policies.evaluate_candidate(db, actor(db), cid)
    db.commit()
    assessment = safety.assess(db, 'gold-a', cid)
    db.commit()
    return cid, pd, assessment


def review_and_pay(db, pd, assessment):
    with pytest.raises(DomainError):
        economics.issue(db, actor(db), pd['decisionId'])
    db.rollback()
    req = approvals.create_request(db, actor(db), pd['decisionId'], safety_evaluation_id=assessment.id)
    db.commit()
    assert req['safetyEvaluationId'] == assessment.id
    with pytest.raises(DomainError):
        approvals.decide(db, actor(db, 'ap-manager'), req['id'], {'decision': 'APPROVED'})
    db.rollback()
    approved = approvals.decide(db, actor(db, 'org-manager'), req['id'], {'decision': 'APPROVED'})
    db.commit()
    effect = economics.issue(db, actor(db), pd['decisionId'])
    db.commit()
    assert economics.issue(db, actor(db), pd['decisionId']) == effect
    db.commit()
    stored = db.get(EconomicEffect, effect['id'])
    assert stored.safety_evaluation_id == assessment.id
    assert stored.approval_decision_id == approved['finalDecision']['id']
    assert stored.candidate_id == pd['candidateId']
    assert db.get(LedgerTransaction, stored.ledger_transaction_id).amount == 10
    assert net_position(db, 'gold-a', 'ap-employee') == 10
    return effect


def test_a_frozen_github_project_review_to_ledger(github):
    client, db, source, _ = github
    scope = context(db)
    configure(db, 'github.pull_request.merged', scope, outcome='REQUIRE_REVIEW')
    entry, original = next((e, v) for e, v in specimens() if e['canonicalType'] == 'github.pull_request.merged')
    payload = deepcopy(original)
    resource = payload['pull_request']
    attribution.assign(db, actor(db), source['id'], 'pull_request', str(resource['id']), {'projectId': scope['id']})
    db.commit()
    resource['merged_at'] = datetime.now(timezone.utc).isoformat()
    response = deliver(client, source, payload, 8001)
    assert response.status_code == 200, response.text
    event = db.get(CanonicalEvent, response.json()['eventId'])
    assert event.subject_id == 'ap-employee' and org.event_scope(db, 'gold-a', event.id) == scope
    cid, pd, assessment = govern(db, event)
    assert assessment.outcome == 'REQUIRE_REVIEW'
    effect = review_and_pay(db, pd, assessment)
    assert db.get(RuleCandidate, cid).canonical_event_id == event.id
    attribution.assign(db, actor(db), source['id'], 'pull_request', str(resource['id']), {'projectId': None})
    db.commit()
    assert deliver(client, source, payload, 8001).json()['eventId'] == event.id
    assert org.event_scope(db, 'gold-a', event.id) == scope
    assert economics.issue(db, actor(db), pd['decisionId']) == effect


def test_b_recognition_team_exact_safety_review(approval_db):
    db = approval_db
    scope = context(db, 'TEAM')
    configure(db, 'internal.manager.recognition', scope, outcome='REQUIRE_REVIEW')
    row = appreciation.create(db, actor(db, 'org-manager'), 'recognition', {
        'recipientUserId': 'ap-employee', 'message': 'Verified help', 'submissionId': 'recognition', 'scope': scope})
    db.commit()
    event = db.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.source_event_id == row['id']))
    _, pd, assessment = govern(db, event)
    assert pd['effectiveDecision'] == 'ALLOW' and assessment.outcome == 'REQUIRE_REVIEW'
    review_and_pay(db, pd, assessment)
    org.membership(db, actor(db), scope, 'org-manager', {'active': False, 'manager': False})
    db.commit()
    assert org.event_scope(db, 'gold-a', event.id) == scope
    assert count(db, EconomicEffect) == count(db, LedgerTransaction) == 1


def test_c_and_g_live_and_shadow_have_separate_economic_identity(approval_db):
    db = approval_db
    scope = context(db, 'TEAM')
    configure(db, 'internal.peer.thanks', scope, decision='SHADOW_ONLY')
    event = thanks(db, scope)
    _, pd, assessment = govern(db, event)
    result = shadow.observe(db, actor(db), pd['decisionId'])
    db.commit()
    assert result['proposedAmount'] == result['hypotheticalAuthorizedAmount'] == '10'
    assert result['realExecution'] == 'PREVENTED'
    with pytest.raises(DomainError):
        economics.issue(db, actor(db), pd['decisionId'])
    db.rollback()
    assert count(db, EconomicEffect) == count(db, LedgerTransaction) == 0
    configure(db, 'internal.manager.recognition', scope)
    row = appreciation.create(db, actor(db, 'org-manager'), 'recognition', dict(
        recipientUserId='ap-employee', message='Live work', submissionId='live', scope=scope))
    db.commit()
    live = db.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.source_event_id == row['id']))
    _, live_pd, _ = govern(db, live)
    economics.issue(db, actor(db), live_pd['decisionId'])
    db.commit()
    assert shadow.observe(db, actor(db), pd['decisionId']) == result
    assert count(db, EconomicEffect) == count(db, LedgerTransaction) == 1


@pytest.mark.parametrize('change', ['TEAM_TRANSFER', 'PROJECT_LEAVE_REJOIN'])
def test_d_and_e_help_membership_capability_history(approval_db, change):
    db = approval_db
    scope = context(db)
    configure(db, 'internal.help.completed', scope)
    row = help_service.create(db, actor(db, 'ap-manager'), dict(title='Review', description='Help', submissionId='help', scope=scope))
    help_service.transition(db, actor(db, 'ap-employee'), row['id'], 'accept')
    db.commit()
    if change == 'TEAM_TRANSFER':
        for name in ['Old', 'New']:
            team = org.create(db, actor(db), 'TEAM', {'name': name})
            org.membership(db, actor(db), {'kind': 'TEAM', 'id': team['id']}, 'ap-employee', {'active': True, 'manager': False})
            db.commit()
    else:
        org.membership(db, actor(db), scope, 'ap-employee', {'active': False, 'manager': False})
        db.commit()
        with pytest.raises(DomainError):
            help_service.transition(db, actor(db, 'ap-employee'), row['id'], 'finish')
        db.rollback()
        org.membership(db, actor(db), scope, 'ap-employee', {'active': True, 'manager': False})
        db.commit()
    capability(db, actor(db), 'HELP', {'enabled': False})
    db.commit()
    assert any(r['id'] == row['id'] for r in help_service.listing(db, actor(db)))
    with pytest.raises(DomainError, match='disabled'):
        help_service.transition(db, actor(db, 'ap-employee'), row['id'], 'finish')
    db.rollback()
    capability(db, actor(db), 'HELP', {'enabled': True})
    db.commit()
    help_service.transition(db, actor(db, 'ap-employee'), row['id'], 'finish')
    help_service.transition(db, actor(db, 'ap-manager'), row['id'], 'confirm')
    db.commit()
    event = db.scalar(sa.select(CanonicalEvent).where(CanonicalEvent.source_event_id == row['id']))
    _, pd, _ = govern(db, event)
    effect = economics.issue(db, actor(db), pd['decisionId'])
    db.commit()
    org.close(db, actor(db), scope)
    db.commit()
    assert org.event_scope(db, 'gold-a', event.id) == scope
    assert economics.issue(db, actor(db), pd['decisionId']) == effect


def test_f_suppression_cannot_create_approval_or_money(approval_db):
    db = approval_db
    scope = context(db, 'TEAM')
    configure(db, 'internal.peer.thanks', scope, outcome='SUPPRESS_INCENTIVE')
    _, pd, assessment = govern(db, thanks(db, scope))
    assert assessment.outcome == 'SUPPRESS_INCENTIVE'
    for operation in [lambda: approvals.create_request(db, actor(db), pd['decisionId'], safety_evaluation_id=assessment.id),
                      lambda: economics.issue(db, actor(db), pd['decisionId'])]:
        with pytest.raises(DomainError):
            operation()
        db.rollback()
    result = shadow.observe(db, actor(db), pd['decisionId'])
    db.commit()
    assert result['hypotheticalExecutionState'] == 'SUPPRESSED'
    assert count(db, ApprovalRequest) == count(db, EconomicEffect) == count(db, LedgerTransaction) == 0


def test_h_reversal_preserves_review_and_scope(approval_db):
    db = approval_db
    scope = context(db)
    configure(db, 'internal.peer.thanks', scope, outcome='REQUIRE_REVIEW')
    event = thanks(db, scope)
    _, pd, assessment = govern(db, event)
    effect = review_and_pay(db, pd, assessment)
    reversal = reverse(db, actor(db), effect['id'], {'reasonCode': 'ADMIN_CORRECTION'})
    db.commit()
    assert reverse(db, actor(db), effect['id'], {'reasonCode': 'ADMIN_CORRECTION'}) == reversal
    assert net_position(db, 'gold-a', 'ap-employee') == 0
    assert org.event_scope(db, 'gold-a', event.id) == scope
    assert count(db, EconomicEffect) == 1 and count(db, LedgerTransaction) == 2
    with pytest.raises(DomainError, match='consumed'):
        economics.issue(db, actor(db), pd['decisionId'])
    db.rollback()


@pytest.mark.parametrize('boundary', ['rule', 'policy', 'safety', 'approval', 'effect', 'lost_response'])
def test_committed_upstream_survives_downstream_failure_and_retry(approval_db, boundary, monkeypatch):
    db = approval_db
    scope = context(db)
    configure(db, 'internal.peer.thanks', scope, outcome='REQUIRE_REVIEW')
    event = thanks(db, scope)

    def transact(name, operation, model):
        before = count(db, model)
        if boundary == name:
            with pytest.raises(RuntimeError, match='boundary fault'):
                operation()
                raise RuntimeError('boundary fault')
            db.rollback()
            assert count(db, model) == before
            assert db.get(CanonicalEvent, event.id) is not None
        result = operation()
        db.commit()
        return result

    cid = transact('rule', lambda: rules.evaluate_event(db, actor(db), event.id), RuleCandidate)['candidateIds'][0]
    pd = transact('policy', lambda: policies.evaluate_candidate(db, actor(db), cid), PolicyDecision)
    assessment = transact('safety', lambda: safety.assess(db, 'gold-a', cid), SafetyEvaluation)
    req = transact('approval', lambda: approvals.create_request(db, actor(db), pd['decisionId'], safety_evaluation_id=assessment.id), ApprovalRequest)
    approvals.decide(db, actor(db, 'org-manager'), req['id'], {'decision': 'APPROVED'})
    db.commit()
    if boundary == 'effect':
        with monkeypatch.context() as patch:
            def failed_append(*args, **kwargs):
                raise RuntimeError('ledger write fault')
            patch.setattr(economics, 'append_exact', failed_append)
            with pytest.raises(RuntimeError, match='ledger write fault'):
                economics.issue(db, actor(db), pd['decisionId'])
            db.commit()  # Catching caller must still not persist a half-effect.
        assert count(db, EconomicEffect) == count(db, LedgerTransaction) == 0
    effect = economics.issue(db, actor(db), pd['decisionId'])
    db.commit()
    if boundary == 'lost_response':
        with pytest.raises(RuntimeError):
            raise RuntimeError('response failed after commit')
    assert economics.issue(db, actor(db), pd['decisionId']) == effect
    db.commit()
    assert count(db, RuleCandidate) == count(db, PolicyDecision) == count(db, SafetyEvaluation) == 1
    assert count(db, ApprovalRequest) == count(db, EconomicEffect) == count(db, LedgerTransaction) == 1
