"""Real PostgreSQL provenance checks before introducing the issuance boundary."""
from decimal import Decimal
import pytest
from app.domain import DomainError
from app.models import User
from app.ingestion.service import create_source
from app.rules.service import update_rule
from app.policies.service import update_policy, evaluate_candidate
from app.economic_effects.eligibility import economic_admin, is_candidate_economically_processable
from tests.golden.conftest import golden_db
from tests.approval_helpers import approval_db
from tests.economic_helpers import economic_chain


@pytest.mark.parametrize('governance,approval,default,allowed', [
    ('ALLOW', None, False, True), ('REQUIRE_APPROVAL', 'APPROVED', False, True),
    ('REQUIRE_APPROVAL', 'APPROVED', True, True), ('REQUIRE_APPROVAL', None, False, False),
    ('REQUIRE_APPROVAL', 'PENDING', False, False), ('REQUIRE_APPROVAL', 'REJECTED', False, False),
    ('BLOCK', None, False, False), ('SHADOW_ONLY', None, False, False),
])
def test_governance_gate(approval_db, governance, approval, default, allowed):
    db = approval_db
    chain = economic_chain(db, governance=governance, approval=approval, default=default)
    if not allowed:
        with pytest.raises(DomainError) as error:
            is_candidate_economically_processable(db, 'gold-a', chain['decision']['decisionId'])
        assert error.value.code == 'ECONOMIC_EFFECT_NOT_ELIGIBLE'
    else:
        value = is_candidate_economically_processable(db, 'gold-a', chain['decision']['decisionId'])
        assert value.amount == Decimal(10) and value.beneficiary_user_id == 'ap-employee'
        assert value.approval_decision_id == (
            chain['approval']['finalDecision']['id'] if approval else None)


@pytest.mark.parametrize('kind,event_type', [
    ('TASK_LITE', 'internal.task.approved'), ('MANUAL', 'internal.task.approved'),
    ('GENERIC_WEBHOOK', 'internal.task.approved'), ('REWARDS', 'reward.redemption.created'),
    ('INTERNAL', 'external.customer.praise'), ('MANUAL', 'external.unknown.reward'),
])
def test_closed_source_authority(approval_db, kind, event_type):
    chain = economic_chain(approval_db, source_kind=kind, event_type=event_type)
    with pytest.raises(DomainError) as error:
        is_candidate_economically_processable(approval_db, 'gold-a', chain['decision']['decisionId'])
    assert error.value.code == 'LEGACY_ECONOMIC_SOURCE'


@pytest.mark.parametrize('subject', [None, 'gold-admin-a'])
def test_subject_required_no_actor_fallback_or_admin_wallet(approval_db, subject):
    chain = economic_chain(approval_db, subject=subject)
    with pytest.raises(DomainError) as error:
        is_candidate_economically_processable(approval_db, 'gold-a', chain['decision']['decisionId'])
    assert error.value.code == 'ECONOMIC_BENEFICIARY_MISSING'


def test_inactive_historical_participant(approval_db):
    chain = economic_chain(approval_db)
    approval_db.get(User, 'ap-employee').active = False
    approval_db.commit()
    assert is_candidate_economically_processable(approval_db, 'gold-a',
        chain['decision']['decisionId']).beneficiary_user_id == 'ap-employee'


def test_foreign_policy_hidden(approval_db):
    chain = economic_chain(approval_db)
    with pytest.raises(DomainError) as error:
        is_candidate_economically_processable(approval_db, 'gold-b', chain['decision']['decisionId'])
    assert error.value.code == 'ECONOMIC_EFFECT_NOT_FOUND'


@pytest.mark.parametrize('actor_id', ['ap-manager', 'ap-employee', 'ap-inactive'])
def test_admin_gate(approval_db, actor_id):
    with pytest.raises(DomainError) as error:
        economic_admin(approval_db, approval_db.get(User, actor_id))
    assert error.value.code == 'FORBIDDEN'


def test_invalid_manual_source_provenance(approval_db):
    chain = economic_chain(approval_db, source_id='unrelated')
    with pytest.raises(DomainError) as error:
        is_candidate_economically_processable(approval_db, 'gold-a', chain['decision']['decisionId'])
    assert error.value.code == 'ECONOMIC_EFFECT_NOT_ELIGIBLE'


@pytest.mark.parametrize('registered,foreign', [(True, False), (False, False), (True, True)])
def test_webhook_source_tenant_binding(approval_db, registered, foreign):
    db = approval_db
    actor = db.get(User, 'gold-admin-b' if foreign else 'gold-admin-a')
    source_id = create_source(db, actor, 'Synthetic source')['id'] if registered else 'unknown'
    db.commit()
    chain = economic_chain(db, source_kind='GENERIC_WEBHOOK', source_id=source_id)
    if registered and not foreign:
        assert is_candidate_economically_processable(db, 'gold-a',
            chain['decision']['decisionId']).amount == Decimal(10)
    else:
        with pytest.raises(DomainError) as error:
            is_candidate_economically_processable(db, 'gold-a', chain['decision']['decisionId'])
        assert error.value.code == 'ECONOMIC_EFFECT_NOT_ELIGIBLE'


def test_current_rule_and_policy_do_not_reinterpret_historical_evidence(approval_db):
    db = approval_db
    chain = economic_chain(db, amount=10.5)
    actor = db.get(User, 'gold-admin-a')
    update_rule(db, actor, chain['rule']['id'],
        {'outcome': {'kind': 'INCENTIVE', 'data': {'proposedReward': 99}}})
    update_policy(db, actor, chain['policy']['id'], {'decision': 'BLOCK'})
    db.commit()
    newer = evaluate_candidate(db, actor, chain['candidate'])
    db.commit()
    assert newer['effectiveDecision'] == 'BLOCK'
    assert is_candidate_economically_processable(db, 'gold-a',
        chain['decision']['decisionId']).amount == Decimal('10.5')
    with pytest.raises(DomainError) as error:
        is_candidate_economically_processable(db, 'gold-a', newer['decisionId'])
    assert error.value.code == 'ECONOMIC_EFFECT_NOT_ELIGIBLE'


def test_foreign_subject_refused_at_canonical_boundary(approval_db):
    with pytest.raises(DomainError):
        economic_chain(approval_db, subject='gold-admin-b')
    approval_db.rollback()


def test_stale_admin_role_cannot_authorize(approval_db):
    db = approval_db
    actor = db.get(User, 'gold-admin-a')
    db.expunge(actor)
    current = db.get(User, actor.id)
    current.role = 'EMPLOYEE'
    db.commit()
    with pytest.raises(DomainError) as error:
        economic_admin(db, actor)
    assert error.value.code == 'FORBIDDEN'
