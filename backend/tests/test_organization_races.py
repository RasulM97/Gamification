"""Organization lifecycle races use real PostgreSQL transactions and services."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import pytest
import sqlalchemy as sa
from app.db import SessionLocal
from app.domain import DomainError
from app.models import User
from app.organization import service as org
from app.organization.model import ProjectMembership
from app.collaboration import appreciation
from app.rules.service import create_rule, evaluate_event
from app.task_services import create_task
from app.task_access import can_view
from tests.approval_helpers import approval_db, golden_db
from tests.test_organization import actor, context, thanks
from tests.test_rule_evaluator import rule


def test_project_closure_serializes_with_new_event(approval_db):
    db=approval_db; scope=context(db); started=Event()
    with SessionLocal() as writer:
        org.close(writer,actor(writer),scope)
        def emit():
            with SessionLocal() as worker:
                sender=actor(worker,'ap-manager'); started.set()
                try:
                    appreciation.create(worker,sender,'thanks',dict(recipientUserId='ap-employee',
                        message='After closure',submissionId='closure-race',scope=scope))
                    worker.commit();return 'accepted'
                except DomainError as exc:worker.rollback();return exc.code
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(emit);assert started.wait(10)
            assert not future.done();writer.commit()
            assert future.result(timeout=20)=='BAD_STATE'


def test_competing_membership_and_manager_changes_keep_intervals(approval_db):
    db=approval_db;scope=context(db);barrier=Barrier(12)
    def change(n):
        barrier.wait(timeout=20)
        with SessionLocal() as worker:
            org.membership(worker,actor(worker),scope,'org-manager',
                           {'active':n%3!=0,'manager':n%2==0})
            worker.commit()
    with ThreadPoolExecutor(12) as pool:list(pool.map(change,range(12)))
    rows=list(db.scalars(sa.select(ProjectMembership).where(ProjectMembership.user_id=='org-manager')
                        .order_by(ProjectMembership.joined_at)))
    assert sum(r.left_at is None for r in rows)<=1
    for previous,current in zip(rows,rows[1:]):
        assert previous.left_at is not None and previous.left_at<=current.joined_at


def test_rule_retry_during_membership_change_retains_event_context(approval_db):
    db=approval_db;scope=context(db);event=thanks(db,scope)
    create_rule(db,actor(db),rule(eventType=event.type,conditions=[],scope=scope));db.commit()
    expected=evaluate_event(db,actor(db),event.id)['candidateIds'];db.commit()
    barrier=Barrier(2)
    def change():
        with SessionLocal() as worker:
            barrier.wait(timeout=10)
            org.membership(worker,actor(worker),scope,'ap-employee',{'active':False,'manager':False});worker.commit()
    def retry():
        with SessionLocal() as worker:
            barrier.wait(timeout=10)
            value=evaluate_event(worker,actor(worker),event.id)['candidateIds'];worker.commit();return value
    with ThreadPoolExecutor(2) as pool:
        changed=pool.submit(change);retried=pool.submit(retry)
        changed.result(timeout=20);assert retried.result(timeout=20)==expected
    assert org.event_scope(db,'gold-a',event.id)==scope


def test_team_shared_peer_visibility_preserves_private_contract(approval_db):
    db=approval_db;scope=context(db,'TEAM');admin=actor(db)
    db.add(User(id='org-peer',company_id=admin.company_id,name='Peer',email='peer@org.invalid',
                role='EMPLOYEE',active=True,password_hash='disabled'));db.commit()
    org.membership(db,admin,scope,'org-peer',{'active':True,'manager':False});db.commit()
    values=dict(title='Scoped collaboration',description='',priority='NORMAL',deadline=None,reward=0,
                assign_mode='SPECIFIC_EMPLOYEE',assignee_id='ap-employee',context=scope)
    shared=create_task(db,admin,audience='EMPLOYEES',**values)
    private=create_task(db,admin,audience='PRIVATE',**values);db.commit()
    assert can_view(shared,actor(db,'org-peer'))
    assert not can_view(private,actor(db,'org-peer'))
