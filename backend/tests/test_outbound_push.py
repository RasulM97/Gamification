"""WS1 outbound outbox: 3-class gating, dedupe, tenant isolation, transactional staging."""
import sqlalchemy as sa
from app.approvals.service import create_request
from app.collaboration import appreciation
from app.models import LedgerTransaction, Notification, User
from app.notifications.model import NotificationDelivery
from app.notifications.push import PUSH_CLASSES, push_class
from tests.approval_helpers import approval_db, chain
from tests.golden.conftest import golden_db


def outbox(db):
    return list(db.scalars(select_notifications()))


def select_notifications():
    return sa.select(NotificationDelivery).order_by(NotificationDelivery.recipient_user_id)


def test_push_taxonomy_is_exactly_three_classes():
    assert set(PUSH_CLASSES) == {
        'HELP_REQUEST_ACTION_REQUIRED', 'INCENTIVE_APPROVAL_ACTION_REQUIRED', 'RECOGNITION_RECEIVED'}
    assert push_class('MANAGER_RECOGNITION') == 'RECOGNITION_RECEIVED'
    assert push_class('APPROVAL_REQUESTED') == 'INCENTIVE_APPROVAL_ACTION_REQUIRED'
    assert push_class('HELP_ROUTED') == 'HELP_REQUEST_ACTION_REQUIRED'
    assert push_class('HELP_ESCALATED') == 'HELP_REQUEST_ACTION_REQUIRED'
    # Not approved for WS1: informational, economic and routine task events.
    for code in ('PEER_THANKS', 'HELP_ROUTING_UNRESOLVED', 'HELP_REQUESTED', 'HELP_ACCEPTED',
                 'TASK_CREATED', 'TASK_APPROVED', 'TASK_REWARD', 'REDEMPTION_APPROVED'):
        assert push_class(code) is None


def test_recognition_push_stages_once_per_logical_outcome(approval_db):
    db = approval_db
    actor = db.get(User, 'gold-admin-a')
    body = dict(recipientUserId='ap-employee', message='Great work', submissionId='push-one')
    appreciation.create(db, actor, 'recognition', body)
    db.commit()
    rows = outbox(db)
    assert len(rows) == 1
    assert rows[0].push_class == 'RECOGNITION_RECEIVED'
    assert rows[0].recipient_user_id == 'ap-employee'
    assert rows[0].status == 'PENDING' and rows[0].channel == 'EMAIL'
    # Idempotent replay of the same submission restages nothing.
    appreciation.create(db, actor, 'recognition', body)
    db.commit()
    assert len(outbox(db)) == 1


def test_thanks_and_task_events_never_stage_outbound(approval_db):
    db = approval_db
    actor = db.get(User, 'gold-admin-a')
    appreciation.create(db, actor, 'thanks',
                        dict(recipientUserId='ap-employee', message='Thanks', submissionId='push-two'))
    db.commit()
    assert db.scalar(sa.select(Notification).where(Notification.event_type == 'PEER_THANKS')) is not None
    assert outbox(db) == []


def test_approval_push_reaches_current_authority_only(approval_db):
    db = approval_db
    actor = db.get(User, 'gold-admin-a')
    made = chain(db, identity='push', hint='MANAGER', subject='ap-employee')
    request = create_request(db, actor, made['decision']['decisionId'])
    db.commit()
    rows = outbox(db)
    # MANAGER_OR_ADMIN authority in company scope: admins + managers, minus the subject.
    assert {r.recipient_user_id for r in rows} == {'gold-admin-a', 'ap-other', 'ap-manager'}
    assert all(r.push_class == 'INCENTIVE_APPROVAL_ACTION_REQUIRED' for r in rows)
    assert all(r.event_type == 'APPROVAL_REQUESTED' for r in rows)
    assert all(r.params['approvalRequestId'] == request['id'] for r in rows)
    # Inactive admin never receives a push row.
    assert 'ap-inactive' not in {r.recipient_user_id for r in rows}


def test_approval_push_subject_excluded_and_retry_deduped(approval_db):
    db = approval_db
    actor = db.get(User, 'gold-admin-a')
    made = chain(db, identity='pushself', hint='ADMIN', subject='gold-admin-a')
    create_request(db, actor, made['decision']['decisionId'])
    db.commit()
    rows = outbox(db)
    assert {r.recipient_user_id for r in rows} == {'ap-other'}  # subject (admin) excluded
    # Retry of the same decision id conflicts — no duplicate rows appear.
    result = create_request(db, actor, made['decision']['decisionId'])
    db.commit()
    assert len(outbox(db)) == len(rows)


def test_outbound_is_tenant_isolated(approval_db):
    db = approval_db
    actor = db.get(User, 'gold-admin-a')
    appreciation.create(db, actor, 'recognition',
                        dict(recipientUserId='ap-employee', message='Great work', submissionId='push-tenant'))
    db.commit()
    assert {r.company_id for r in outbox(db)} == {'gold-a'}


def test_outbound_staging_rolls_back_with_the_business_transaction(approval_db):
    db = approval_db
    actor = db.get(User, 'gold-admin-a')
    appreciation.create(db, actor, 'recognition',
                        dict(recipientUserId='ap-employee', message='Great work', submissionId='push-rollback'))
    # Simulated failure after enqueue: the caller's transaction rolls back.
    db.rollback()
    assert outbox(db) == []
    assert db.scalar(sa.select(sa.func.count()).select_from(Notification)) == 0
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction)) == 0


def test_stale_authority_cannot_decide_after_push(approval_db):
    """The push reflects authority at send time; the decision re-checks it live.
    A manager deactivated or demoted AFTER the push cannot act on the request."""
    import pytest
    from app.approvals.service import decide
    from app.domain import DomainError
    db = approval_db
    actor = db.get(User, 'gold-admin-a')
    made = chain(db, identity='stale', hint='MANAGER', subject='ap-employee')
    request = create_request(db, actor, made['decision']['decisionId'])
    db.commit()
    assert 'ap-manager' in {r.recipient_user_id for r in outbox(db)}
    # Deactivation after the push closes the door.
    db.execute(sa.update(User).where(User.id == 'ap-manager').values(active=False))
    db.commit()
    manager = db.get(User, 'ap-manager')
    with pytest.raises(DomainError) as exc:
        decide(db, manager, request['id'], dict(decision='APPROVED', reasonCode='OK', note=None))
    assert exc.value.code == 'APPROVER_INACTIVE'
    # Demotion after the push closes it too.
    db.execute(sa.update(User).where(User.id == 'ap-manager').values(active=True, role='EMPLOYEE'))
    db.commit()
    with pytest.raises(DomainError) as exc:
        decide(db, manager, request['id'], dict(decision='APPROVED', reasonCode='OK', note=None))
    assert exc.value.code == 'APPROVAL_FORBIDDEN'
    # The request stays undecided — no economic effect from stale authority.
    assert db.scalar(sa.select(sa.func.count()).select_from(LedgerTransaction)) == 0
