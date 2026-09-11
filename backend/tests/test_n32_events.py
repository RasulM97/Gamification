"""N3.2 structured event persistence, snapshots and reducer contract parity."""
import copy
import json
from pathlib import Path

from sqlalchemy import select

from app.events import EVENT_TYPES
from app.models import Activity, Notification, LedgerTransaction, User, Reward

CONTRACT = json.loads((Path(__file__).parent / 'fixtures/n32-parity.json').read_text())


def state(client, auth):
    return client.get('/api/bootstrap', headers=auth['dana']).json()


def matches(actual, expected):
    assert actual['eventType'] == expected['eventType']
    for key, value in expected['params'].items():
        assert actual['params'][key] == value, key


def test_n32_approval_contract(client, auth):
    r = client.post('/api/tasks/t-northstar/approve', headers=auth['marcus'])
    assert r.status_code == 200
    a = next(a for a in r.json()['activity'] if a.get('eventType') == 'TASK_APPROVED' and a.get('taskId') == 't-northstar')
    matches(a, CONTRACT['approval'])
    assert a['action'] == '' and a['object'] == ''
    ledger = next(l for l in r.json()['ledger'] if l.get('taskId') == 't-northstar')
    assert ledger['amount'] == ledger['params']['coins'] == 37
    assert ledger['eventType'] == 'TASK_REWARD'


def test_n32_handoff_preserves_reason(client, auth):
    reason = 'Keep example.com and file.py unchanged — دلیل'
    r = client.post('/api/tasks/t-commission/handoff', headers=auth['marcus'],
                    data={'acceptedPct': 20, 'reason': reason, 'nextKind': 'AVAILABLE'})
    assert r.status_code == 200
    a = next(a for a in r.json()['activity'] if a.get('eventType') == 'TASK_HANDOFF' and a.get('taskId') == 't-commission' and a.get('params', {}).get('reason') == reason)
    assert a['params']['percent'] == 20 and a['params']['coins'] == 6
    assert a['params']['employee'] == 'Jonas Berg'


def test_n32_fulfillment_contract_and_snapshot_immutability(client, auth, db):
    assert client.post('/api/redemptions/r2/approve', headers=auth['marcus']).status_code == 200
    assert client.post('/api/redemptions/r2/fulfill', headers=auth['jonas'],
                       json={'reference': 'track.example.com', 'note': 'Delivered exactly'}).status_code == 200
    before = state(client, auth)
    a = next(a for a in before['activity'] if a.get('eventType') == 'REDEMPTION_FULFILLED')
    matches(a, CONTRACT['fulfillment'])
    db.get(User, 'u-jonas').name = 'Renamed executor'
    db.get(Reward, 'rw-lunch').name = 'Renamed reward'
    db.commit()
    after = state(client, auth)
    assert after['activity'] == before['activity']
    assert after['notices'] == before['notices']
    assert after['ledger'] == before['ledger']
    retry = client.post('/api/redemptions/r2/fulfill', headers=auth['jonas'], json={})
    assert retry.status_code == 409
    assert state(client, auth)['notices'] == before['notices']


def test_n32_seed_uses_valid_structured_records(db):
    for model, prose in [(Activity, 'action'), (Notification, 'text'), (LedgerTransaction, 'ref')]:
        rows = list(db.scalars(select(model)))
        assert rows
        for row in rows:
            assert row.event_type in EVENT_TYPES
            assert row.params['actor']
            assert getattr(row, prose) == ''


def test_n32_legacy_payload_still_bootstraps_without_rewrite(client, auth, db):
    row = Activity(company_id='co-aster', actor_id='u-marcus', action='approved work',
                   object='Legacy title — دلیل', reason='Original human note', at=1)
    db.add(row)
    db.commit()
    a = next(a for a in state(client, auth)['activity'] if a['id'] == row.id)
    assert a['action'] == 'approved work' and a['object'] == 'Legacy title — دلیل'
    assert a['reason'] == 'Original human note' and 'eventType' not in a


def test_n32_activity_appends_and_does_not_rewrite(client, auth):
    before = copy.deepcopy(state(client, auth)['activity'])
    assert client.post('/api/tasks/t-northstar/approve', headers=auth['marcus']).status_code == 200
    after = state(client, auth)['activity']
    assert len(after) == len(before) + 1
    assert {a['id']: a for a in after if a['id'] in {a['id'] for a in before}} == {a['id']: a for a in before}
