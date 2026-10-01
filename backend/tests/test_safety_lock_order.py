"""Force a live issuance / review retry overlap; neither may deadlock."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from app.db import SessionLocal
from app.models import User
from app.domain import DomainError
from app.incentive_safety.authority import lock as safety_lock
from app.approvals import service as approval_service
from app.economic_effects import service as economic_service
from app.incentive_safety import service as safety_service
from app.incentive_safety import shadow as safety_shadow
from tests.golden.conftest import golden_db
from tests.approval_helpers import approval_db
from tests.economic_helpers import economic_chain
from tests.safety_helpers import safety


@pytest.mark.parametrize('operation',['approval','assessment','shadow'])
def test_review_and_live_issuance_share_lock_order(approval_db,monkeypatch,operation):
    db=approval_db; chain=economic_chain(db); evaluation=safety(db,chain)
    actor=db.get(User,'gold-admin-a')
    request=approval_service.create_request(db,actor,chain['decision']['decisionId'],safety_evaluation_id=evaluation.id)
    db.commit()
    approval_service.decide(db,db.get(User,'ap-other'),request['id'],{'decision':'APPROVED'}); db.commit()
    safety_held=Event(); competing_started=Event()
    original_lock=economic_service.lock_identity
    def pause_issuance(*args,**kwargs):
        safety_held.set()
        assert competing_started.wait(5)
        return original_lock(*args,**kwargs)
    monkeypatch.setattr(economic_service,'lock_identity',pause_issuance)
    module=approval_service if operation=='approval' else safety_service if operation=='assessment' else safety_shadow
    authority_name='management_actor' if operation=='approval' else 'admin'
    original_authority=getattr(module,authority_name)
    def announce_authority(*args,**kwargs):
        result=original_authority(*args,**kwargs)
        competing_started.set()
        return result
    monkeypatch.setattr(module,authority_name,announce_authority)
    def pay():
        with SessionLocal() as worker:
            result=economic_service.issue(worker,worker.get(User,actor.id),chain['decision']['decisionId'])
            worker.commit(); return result
    def review():
        assert safety_held.wait(5)
        with SessionLocal() as worker:
            user=worker.get(User,actor.id)
            if operation=='approval':
                result=approval_service.create_request(worker,user,chain['decision']['decisionId'],safety_evaluation_id=evaluation.id)
            elif operation=='assessment': result=safety_service.evaluate_candidate(worker,user,chain['candidate'])
            else: result=safety_shadow.observe(worker,user,chain['decision']['decisionId'])
            worker.commit(); return result
    with ThreadPoolExecutor(2) as pool:
        issued=pool.submit(pay); inspected=pool.submit(review)
        assert issued.result(timeout=15)['amount']=='10'
        assert inspected.result(timeout=15)['id']


@pytest.mark.parametrize('operation',['approval','assessment','shadow'])
def test_authority_rechecked_after_waiting_for_safety(approval_db,monkeypatch,operation):
    db=approval_db; chain=economic_chain(db); evaluation=safety(db,chain)
    first_read=Event()
    module=approval_service if operation=='approval' else safety_service if operation=='assessment' else safety_shadow
    name='management_actor' if operation=='approval' else 'admin'
    original=getattr(module,name)
    def announce(*args,**kwargs):
        result=original(*args,**kwargs)
        if kwargs.get('lock') is False: first_read.set()
        return result
    monkeypatch.setattr(module,name,announce)
    def request():
        with SessionLocal() as worker:
            actor=worker.get(User,'gold-admin-a')
            if operation=='approval':
                approval_service.create_request(worker,actor,chain['decision']['decisionId'],safety_evaluation_id=evaluation.id)
            elif operation=='assessment': safety_service.evaluate_candidate(worker,actor,chain['candidate'])
            else: safety_shadow.observe(worker,actor,chain['decision']['decisionId'])
            worker.commit()
    with SessionLocal() as holder, ThreadPoolExecutor(1) as pool:
        safety_lock(holder,'gold-a',chain['candidate'])
        future=pool.submit(request)
        try:
            assert first_read.wait(5)
            db.get(User,'gold-admin-a').active=False; db.commit()
        finally:
            holder.commit()
        with pytest.raises(DomainError): future.result(timeout=10)
