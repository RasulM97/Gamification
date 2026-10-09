"""Server-side session revocation — UAT-blocker security contract.

Pins the server-authoritative session model: every login creates a distinct
AuthSession; a JWT is only valid while its session row exists, matches
user+company, and is neither revoked nor expired; logout revokes the current
session immediately and globally (every copy of the token, any context);
independent sessions never kill each other.

Covers required cases A–M from the blocker specification.
"""
import time

import jwt as pyjwt
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app import uat_seed
from app.config import settings
from app.main import app
from app.models import AuthSession, User
from app.security import issue_token, make_token
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db  # noqa: F401  (registers the fixture)


@pytest.fixture()
def uat(approval_db):
    summary = uat_seed.seed(approval_db)
    return approval_db, summary


def login(email, password):
    return TestClient(app).post('/api/auth/login', json={'email': email, 'password': password})


def hdr(token):
    return {'Authorization': 'Bearer ' + token}


def dana_token(summary):
    r = login('dana@aster.uat.test', summary['passwords']['uat-dana'])
    assert r.status_code == 200, r.text
    return r.json()['token']


def sid_of(token):
    return pyjwt.decode(token, settings.jwt_secret, algorithms=['HS256'])['sid']


def session_row(db, token):
    return db.get(AuthSession, sid_of(token))


def test_a_login_creates_distinct_server_sessions(uat):
    db, summary = uat
    t1, t2 = dana_token(summary), dana_token(summary)
    assert sid_of(t1) != sid_of(t2)  # never reuse another login's session
    rows = db.scalars(sa.select(AuthSession).where(AuthSession.user_id == 'uat-dana')).all()
    assert {s.id for s in rows} == {sid_of(t1), sid_of(t2)}
    assert all(s.company_id == 'co-uat-aster' and s.revoked_at is None for s in rows)


def test_b_active_session_authenticates(uat):
    _, summary = uat
    token = dana_token(summary)
    r = TestClient(app).get('/api/auth/me', headers=hdr(token))
    assert r.status_code == 200 and r.json()['id'] == 'uat-dana'


def test_c_logout_revokes_current_session(uat):
    db, summary = uat
    token = dana_token(summary)
    r = TestClient(app).post('/api/auth/logout', headers=hdr(token))
    assert r.status_code == 200
    db.expire_all()
    assert session_row(db, token).revoked_at is not None


def test_d_copied_token_in_second_client_dies_on_logout(uat):
    _, summary = uat
    token = dana_token(summary)
    window_a, window_b = TestClient(app), TestClient(app)  # same token, two contexts
    assert window_a.get('/api/auth/me', headers=hdr(token)).status_code == 200
    assert window_b.get('/api/bootstrap', headers=hdr(token)).status_code == 200
    assert window_a.post('/api/auth/logout', headers=hdr(token)).status_code == 200
    assert window_b.get('/api/auth/me', headers=hdr(token)).status_code == 401
    assert window_b.get('/api/bootstrap', headers=hdr(token)).status_code == 401


def test_e_revoked_token_cannot_read_or_mutate(uat):
    _, summary = uat
    token = dana_token(summary)
    c = TestClient(app)
    assert c.post('/api/auth/logout', headers=hdr(token)).status_code == 200
    assert c.get('/api/auth/me', headers=hdr(token)).status_code == 401
    assert c.get('/api/bootstrap', headers=hdr(token)).status_code == 401
    # representative admin mutation
    assert c.patch('/api/company', headers=hdr(token), json={'name': 'Hijack Co'}).status_code == 401


def test_f_independent_second_login_survives_first_logout(uat):
    _, summary = uat
    session_a, session_b = dana_token(summary), dana_token(summary)  # e.g. two devices
    c = TestClient(app)
    assert c.post('/api/auth/logout', headers=hdr(session_a)).status_code == 200
    assert c.get('/api/auth/me', headers=hdr(session_a)).status_code == 401
    r = c.get('/api/auth/me', headers=hdr(session_b))
    assert r.status_code == 200 and r.json()['id'] == 'uat-dana'


def test_g_nonexistent_or_missing_session_id_is_401(uat):
    db, _ = uat
    user = db.get(User, 'uat-dana')
    forged = make_token(user, 'sid-does-not-exist')
    assert TestClient(app).get('/api/auth/me', headers=hdr(forged)).status_code == 401
    # legacy sid-less token (pre-fix format) must never be sufficient authority
    legacy = pyjwt.encode({'sub': user.id, 'cid': user.company_id, 'role': user.role,
                           'iat': int(time.time()), 'exp': int(time.time()) + 3600},
                          settings.jwt_secret, algorithm='HS256')
    assert TestClient(app).get('/api/auth/me', headers=hdr(legacy)).status_code == 401


def test_h_session_user_or_tenant_mismatch_is_401(uat):
    db, summary = uat
    marcus_token = login('marcus@aster.uat.test', summary['passwords']['uat-marcus']).json()['token']
    dana = db.get(User, 'uat-dana')
    # a token naming Dana but pointing at Marcus's session
    forged = make_token(dana, sid_of(marcus_token))
    assert TestClient(app).get('/api/auth/me', headers=hdr(forged)).status_code == 401
    # a foreign-tenant session id is equally useless
    orbit_token = login('orbit.admin@orbit.uat.test', summary['passwords']['uat-orbit-admin']).json()['token']
    forged_cross = make_token(dana, sid_of(orbit_token))
    assert TestClient(app).get('/api/auth/me', headers=hdr(forged_cross)).status_code == 401


def test_i_expired_session_is_401_even_with_valid_jwt(uat):
    db, summary = uat
    token = dana_token(summary)
    s = session_row(db, token)
    s.expires_at = time.time() - 1  # JWT exp still valid; server session expired
    db.commit()
    assert TestClient(app).get('/api/auth/me', headers=hdr(token)).status_code == 401


def test_j_revoked_session_is_401(uat):
    db, summary = uat
    token = dana_token(summary)
    s = session_row(db, token)
    s.revoked_at = time.time()
    db.commit()
    assert TestClient(app).get('/api/auth/me', headers=hdr(token)).status_code == 401


def test_k_inactive_user_fails_closed_with_live_session(uat):
    db, summary = uat
    token = dana_token(summary)
    db.get(User, 'uat-dana').active = False
    db.commit()
    assert TestClient(app).get('/api/auth/me', headers=hdr(token)).status_code == 401


def test_l_logout_cannot_touch_another_users_session(uat):
    db, summary = uat
    dana = dana_token(summary)
    marcus = login('marcus@aster.uat.test', summary['passwords']['uat-marcus']).json()['token']
    assert TestClient(app).post('/api/auth/logout', headers=hdr(dana)).status_code == 200
    db.expire_all()
    assert session_row(db, marcus).revoked_at is None
    assert TestClient(app).get('/api/auth/me', headers=hdr(marcus)).status_code == 200


def test_m_repeated_logout_is_safe(uat):
    _, summary = uat
    token = dana_token(summary)
    c = TestClient(app)
    assert c.post('/api/auth/logout', headers=hdr(token)).status_code == 200
    second = c.post('/api/auth/logout', headers=hdr(token))  # fail-closed, no 5xx
    assert second.status_code == 401 and second.json()['detail']['code'] == 'AUTH_INVALID'


def test_old_jwt_never_survives_without_its_session_row(uat):
    """DB restore / stale token contract: deleting the session row (as a UAT
    snapshot rollback to a pre-login state does) kills the token."""
    db, summary = uat
    token = dana_token(summary)
    db.delete(session_row(db, token))
    db.commit()
    assert TestClient(app).get('/api/auth/me', headers=hdr(token)).status_code == 401
    assert TestClient(app).get('/api/bootstrap', headers=hdr(token)).status_code == 401


def test_issue_token_helper_creates_real_sessions(uat):
    db, _ = uat
    token = issue_token(db, db.get(User, 'uat-dana'))
    assert TestClient(app).get('/api/auth/me', headers=hdr(token)).status_code == 200
