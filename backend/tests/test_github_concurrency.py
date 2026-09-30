"""Physical duplicate workers and source lifecycle locking, without mocked database outcomes."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier,Event
import pytest
import sqlalchemy as sa
from app.db import engine
from app.canonical_events.model import CanonicalEvent
from app.github_connector.model import GithubDelivery
from app.github_connector.security import verify
from tests.github_helpers import github,deliver,specimen
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db


def test_twenty_workers_same_delivery(github):
    client,db,source,_=github;barrier=Barrier(20)
    def send(i):
        barrier.wait(timeout=20)
        return deliver(client,source,number=1)
    with ThreadPoolExecutor(20) as pool:results=list(pool.map(send,range(20)))
    assert all(r.status_code==200 for r in results),[(r.status_code,r.text) for r in results]
    assert len({r.json()['eventId'] for r in results})==1
    assert sum(r.json()['category']=='DUPLICATE_DELIVERY' for r in results)==19
    assert db.scalar(sa.select(sa.func.count()).select_from(GithubDelivery))==1
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent))==1


@pytest.mark.parametrize('operation',['rotate','disable'])
def test_source_change_serializes_after_verified_inflight_delivery(github,monkeypatch,operation):
    client,db,source,auth=github;verified=Event();release=Event();changing=Event()
    def paused_verify(*args):
        verify(*args);verified.set();assert release.wait(timeout=20)
    monkeypatch.setattr('app.github_connector.delivery.verify',paused_verify)
    def change():
        changing.set()
        path='/api/integrations/github/'+source['id']
        return client.post(path+'/rotate-secret',headers=auth) if operation=='rotate' else client.patch(path,headers=auth,json={'status':'DISABLED'})
    with ThreadPoolExecutor(2) as pool:
        delivery=pool.submit(deliver,client,source)
        assert verified.wait(timeout=20)
        mutation=pool.submit(change);assert changing.wait(timeout=20)
        assert not mutation.done()
        release.set()
        assert delivery.result(timeout=20).status_code==200
        updated=mutation.result(timeout=20);assert updated.status_code==200
    assert deliver(client,source,specimen(number=2),number=2).status_code==401
    if operation=='rotate':assert deliver(client,updated.json(),specimen(number=2),number=2).status_code==200


def test_raw_and_canonical_rollback_together_on_event_failure(github):
    client,db,source,_=github
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE FUNCTION e9_reject_event() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private fault'; END; $$"))
        conn.execute(sa.text('CREATE TRIGGER e9_reject_event BEFORE INSERT ON canonical_events FOR EACH ROW EXECUTE FUNCTION e9_reject_event()'))
    try:
        result=deliver(client,source)
        assert result.status_code==503 and 'private fault' not in result.text
        assert db.scalar(sa.select(sa.func.count()).select_from(GithubDelivery))==0
        assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent))==0
        db.rollback()
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text('DROP TRIGGER e9_reject_event ON canonical_events'))
            conn.execute(sa.text('DROP FUNCTION e9_reject_event()'))
    assert deliver(client,source).status_code==200


def test_closed_before_open_is_independent_observation(github):
    client,db,source,_=github
    assert deliver(client,source,specimen('merged'),1).status_code==200
    assert deliver(client,source,specimen('pr_opened'),2).status_code==200
    assert db.scalar(sa.select(sa.func.count()).select_from(CanonicalEvent))==2
