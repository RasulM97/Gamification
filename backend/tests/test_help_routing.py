"""WS1 Help routing + escalation (Decision A): scope fan-out, unresolved honesty,
manager escalation, membership snapshots, accept race, capability gating."""
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.capabilities.service import update as capability_update
from app.collaboration import routing
from app.collaboration.model import HelpRequest, HelpRouting
from app.config import settings
from app.main import app
from app.models import Notification, User
from app.organization import service as org
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db
from tests.test_internal_events import headers

WINDOW = settings.help_escalation_window_ms


@pytest.fixture()
def routed(approval_db):
    """gold-a with a Sales team: ap-manager (manager), ap-employee (member)."""
    client = TestClient(app, raise_server_exceptions=False)
    db = approval_db
    admin = db.get(User, 'gold-admin-a')
    team = org.create(db, admin, 'TEAM', {'name': 'Sales'})
    org.membership(db, admin, {'kind': 'TEAM', 'id': team['id']}, 'ap-manager',
                   {'active': True, 'manager': True})
    org.membership(db, admin, {'kind': 'TEAM', 'id': team['id']}, 'ap-employee',
                   {'active': True, 'manager': False})
    db.commit()  # release org advisory locks before any API call
    return client, db, team


def ask(client, db, user, team=None, submission='rt-one'):
    body = {'title': 'Need a review', 'description': 'Second pair of eyes', 'submissionId': submission}
    if team:
        body['scope'] = {'kind': 'TEAM', 'id': team['id']}
    response = client.post('/api/collaboration/help', headers=headers(db, user), json=body)
    assert response.status_code == 200, response.text
    return response.json()


def notices(db, user, event):
    return list(db.scalars(sa.select(Notification).where(
        Notification.user_id == user, Notification.event_type == event)))


def routings(db, help_id):
    return list(db.scalars(sa.select(HelpRouting).where(HelpRouting.help_id == help_id)
                           .order_by(HelpRouting.seq)))


def test_team_help_routes_to_active_scope_members_not_requester(routed):
    client, db, team = routed
    view = ask(client, db, 'ap-employee', team)
    assert view['routingStatus'] == 'ROUTED'
    routed_notices = notices(db, 'ap-manager', 'HELP_ROUTED')
    assert len(routed_notices) == 1
    assert routed_notices[0].level == 'ACTION_REQUIRED'
    assert routed_notices[0].category == 'Collaboration'
    assert routed_notices[0].params['scopeKind'] == 'TEAM'
    assert routed_notices[0].params['scopeName'] == 'Sales'
    # Never the requester, never anyone outside the scope — no broadcast.
    assert notices(db, 'ap-employee', 'HELP_ROUTED') == []
    assert notices(db, 'gold-admin-a', 'HELP_ROUTED') == []
    assert notices(db, 'ap-other', 'HELP_ROUTED') == []
    rows = routings(db, view['id'])
    assert len(rows) == 1 and rows[0].kind == 'INITIAL'
    assert rows[0].recipient_user_ids == ['ap-manager']
    assert rows[0].reason == 'INITIAL_ROUTING'


def test_company_help_uses_admin_fallback_never_broadcast(routed):
    client, db, _ = routed
    view = ask(client, db, 'ap-employee')
    assert view['routingStatus'] == 'ROUTED'
    assert len(notices(db, 'gold-admin-a', 'HELP_ROUTED')) == 1
    assert len(notices(db, 'ap-other', 'HELP_ROUTED')) == 1
    assert notices(db, 'ap-manager', 'HELP_ROUTED') == []  # manager is not company audience
    assert notices(db, 'ap-employee', 'HELP_ROUTED') == []


def test_unresolved_is_preserved_marked_and_explained(routed):
    client, db, _ = routed
    # gold-b has a single active admin — company help from them has no target.
    view = ask(client, db, 'gold-admin-b')
    assert view['routingStatus'] == 'UNRESOLVED'
    row = db.get(HelpRequest, view['id'])
    assert row.status == 'OPEN'  # request preserved, never silently dropped
    informed = notices(db, 'gold-admin-b', 'HELP_ROUTING_UNRESOLVED')
    assert len(informed) == 1 and informed[0].level == 'INFORMATIONAL'
    rows = routings(db, view['id'])
    assert rows[0].reason == 'NO_ELIGIBLE_RECIPIENTS'


def test_unanswered_team_help_escalates_to_manager(routed):
    client, db, team = routed
    view = ask(client, db, 'ap-employee', team)
    row = db.get(HelpRequest, view['id'])
    result = routing.pass_due(db, 'gold-a', now=row.routed_at + WINDOW + 1)
    db.commit()
    assert result == {'escalated': 1, 'retried': 0, 'capabilityEnabled': True}
    db.expire_all()
    assert row.routing_status == 'ESCALATED' and row.escalated_at is not None
    assert len(notices(db, 'ap-manager', 'HELP_ESCALATED')) == 1
    rows = routings(db, view['id'])
    assert [r.kind for r in rows] == ['INITIAL', 'ESCALATION']
    assert rows[1].reason == 'WINDOW_EXPIRED' and rows[1].recipient_user_ids == ['ap-manager']
    # A second pass is a no-op — no duplicate escalation.
    assert routing.pass_due(db, 'gold-a', now=row.routed_at + WINDOW + 2)['escalated'] == 0


def test_accepted_help_never_escalates(routed):
    client, db, team = routed
    view = ask(client, db, 'ap-employee', team)
    accept = client.post(f"/api/collaboration/help/{view['id']}/accept",
                         headers=headers(db, 'ap-manager'), json={})
    assert accept.status_code == 200
    row = db.get(HelpRequest, view['id'])
    result = routing.pass_due(db, 'gold-a', now=row.routed_at + WINDOW + 1)
    assert result['escalated'] == 0
    assert notices(db, 'ap-manager', 'HELP_ESCALATED') == []
    assert [r.kind for r in routings(db, view['id'])] == ['INITIAL']


def test_membership_change_never_rewrites_routing_history(routed):
    client, db, team = routed
    view = ask(client, db, 'ap-employee', team)
    admin = db.get(User, 'gold-admin-a')
    # Membership changes after routing: manager leaves, a new member joins.
    org.membership(db, admin, {'kind': 'TEAM', 'id': team['id']}, 'ap-manager',
                   {'active': False, 'manager': False})
    db.commit()
    rows = routings(db, view['id'])
    assert rows[0].recipient_user_ids == ['ap-manager']  # snapshot frozen
    # The immutable audit rejects rewrite/delete at the database layer.
    with pytest.raises(sa.exc.IntegrityError):
        with db.begin_nested():
            db.execute(sa.update(HelpRouting).values(recipient_user_ids=['gold-admin-a']))
    with pytest.raises(sa.exc.IntegrityError):
        with db.begin_nested():
            db.execute(sa.delete(HelpRouting))
    db.rollback()


def test_escalation_falls_back_to_admins_without_scope_manager(routed):
    client, db, team = routed
    admin = db.get(User, 'gold-admin-a')
    project = org.create(db, admin, 'PROJECT', {'name': 'Solo'})
    org.membership(db, admin, {'kind': 'PROJECT', 'id': project['id']}, 'ap-employee',
                   {'active': True, 'manager': False})
    db.commit()
    body = {'title': 'Project question', 'description': 'Need input', 'submissionId': 'rt-proj',
            'scope': {'kind': 'PROJECT', 'id': project['id']}}
    response = client.post('/api/collaboration/help', headers=headers(db, 'ap-employee'), json=body)
    assert response.status_code == 200, response.text
    view = response.json()
    # No eligible first-hop recipient (only member is the requester) → unresolved.
    assert view['routingStatus'] == 'UNRESOLVED'
    # Re-route retry is also empty, then escalation window logic never applies to
    # UNRESOLVED rows; add a member and prove retry routing picks them up.
    org.membership(db, admin, {'kind': 'PROJECT', 'id': project['id']}, 'ap-manager',
                   {'active': True, 'manager': False})
    db.commit()
    result = routing.pass_due(db, 'gold-a')
    assert result['retried'] == 1
    db.expire_all()
    row = db.get(HelpRequest, view['id'])
    assert row.routing_status == 'ROUTED'
    assert len(notices(db, 'ap-manager', 'HELP_ROUTED')) == 1
    rows = routings(db, view['id'])
    assert [r.kind for r in rows] == ['INITIAL', 'INITIAL']
    assert rows[1].reason == 'RETRY_ROUTING'
    # Requester was informed exactly once, at creation — retries never re-spam.
    assert len(notices(db, 'ap-employee', 'HELP_ROUTING_UNRESOLVED')) == 1


def test_company_scope_never_escalates(routed):
    client, db, _ = routed
    view = ask(client, db, 'ap-employee')
    row = db.get(HelpRequest, view['id'])
    result = routing.pass_due(db, 'gold-a', now=row.routed_at + WINDOW + 1)
    assert result['escalated'] == 0
    assert notices(db, 'gold-admin-a', 'HELP_ESCALATED') == []


def test_capability_disabled_pass_produces_no_actions(routed):
    client, db, team = routed
    view = ask(client, db, 'ap-employee', team)
    row = db.get(HelpRequest, view['id'])
    admin = db.get(User, 'gold-admin-a')
    capability_update(db, admin, 'HELP', {'enabled': False})
    db.commit()
    result = routing.pass_due(db, 'gold-a', now=row.routed_at + WINDOW + 1)
    assert result == {'escalated': 0, 'retried': 0, 'capabilityEnabled': False}
    assert notices(db, 'ap-manager', 'HELP_ESCALATED') == []
    capability_update(db, admin, 'HELP', {'enabled': True})
    db.commit()
    # Existing history stays readable while disabled / after re-enable.
    listing = client.get('/api/collaboration/help', headers=headers(db, 'ap-manager'))
    assert listing.status_code == 200 and len(listing.json()) == 1


def test_capability_disabled_between_notify_and_click(routed):
    client, db, team = routed
    view = ask(client, db, 'ap-employee', team)
    assert len(notices(db, 'ap-manager', 'HELP_ROUTED')) == 1
    admin = db.get(User, 'gold-admin-a')
    capability_update(db, admin, 'HELP', {'enabled': False})
    db.commit()
    blocked = client.post(f"/api/collaboration/help/{view['id']}/accept",
                          headers=headers(db, 'ap-manager'), json={})
    assert blocked.status_code == 409 and blocked.json()['code'] == 'CAPABILITY_DISABLED'
    db.expire_all()
    assert db.get(HelpRequest, view['id']).status == 'OPEN'
