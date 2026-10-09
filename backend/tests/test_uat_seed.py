"""UAT Stage A seed/reset infrastructure — focused tests.

Pins: deterministic roster/structure, idempotent reruns, scoped reset that
cannot touch other tenants, regenerated credentials, real login per role,
tenant isolation, and the explicit-dev-mode guard. Uses the shared Golden
database; the UAT tenants are additive synthetic companies."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import app
from app import uat_seed
from app.config import settings
from app.domain import DomainError
from app.models import Company, CompanySettings, User
from app.organization.model import Project, ProjectMembership, Team, TeamMembership
from app.collaboration import appreciation
from app.collaboration.model import PeerThanks
from app.canonical_events.model import CanonicalEvent
from app.provisioning import provision_company
from tests.approval_helpers import approval_db
from tests.golden.conftest import golden_db  # noqa: F401  (registers the fixture)

BACKEND_DIR = Path(__file__).resolve().parents[1]


def count(db, model, company=None):
    q = sa.select(sa.func.count()).select_from(model)
    if company: q = q.where(model.company_id == company)
    return db.scalar(q)


@pytest.fixture()
def uat(approval_db):
    summary = uat_seed.seed(approval_db)
    return approval_db, summary


def login(email, password):
    return TestClient(app).post('/api/auth/login', json={'email': email, 'password': password})


def test_seed_creates_exact_roster_structure_and_settings(uat):
    db, summary = uat
    assert summary['created'] == {'co-uat-aster': True, 'co-uat-orbit': True}
    aster = db.scalars(sa.select(User).where(User.company_id == 'co-uat-aster').order_by(User.id)).all()
    assert len(aster) == 10
    roles = {}
    for u in aster: roles[u.role] = roles.get(u.role, 0) + 1
    assert roles == {'ADMIN': 1, 'MANAGER': 2, 'EMPLOYEE': 7}
    assert all(u.active and u.activation_hash is None for u in aster)  # immediately usable
    assert all(u.email.endswith('@aster.uat.test') for u in aster)
    company = db.get(Company, 'co-uat-aster')
    assert company.name == 'Aster Dynamics UAT' and company.onboarding_status == 'COMPLETED'
    assert db.scalar(sa.select(CompanySettings).where(CompanySettings.company_id == 'co-uat-aster'))

    orbit = db.scalars(sa.select(User).where(User.company_id == 'co-uat-orbit')).all()
    assert sorted(u.role for u in orbit) == ['ADMIN', 'EMPLOYEE']
    assert all(u.email.endswith('@orbit.uat.test') for u in orbit)

    def members(model, column, unit_id):
        return {r.user_id: r.manager for r in db.scalars(
            sa.select(model).where(column == unit_id, model.left_at.is_(None)))}
    ops = members(TeamMembership, TeamMembership.team_id, 'uat-team-operations')
    assert ops == {'uat-elena': True, 'uat-aisha': False, 'uat-leo': False, 'uat-mina': False}
    com = members(TeamMembership, TeamMembership.team_id, 'uat-team-commercial')
    assert com == {'uat-marcus': True, 'uat-priya': False, 'uat-jonas': False, 'uat-sara': False, 'uat-noah': False}
    north = members(ProjectMembership, ProjectMembership.project_id, 'uat-proj-northstar')
    assert north == {'uat-marcus': True, 'uat-priya': False, 'uat-jonas': False, 'uat-aisha': False}
    migr = members(ProjectMembership, ProjectMembership.project_id, 'uat-proj-migration')
    assert migr == {'uat-elena': True, 'uat-sara': False, 'uat-noah': False, 'uat-mina': False}


def test_seed_rerun_is_idempotent_without_duplicates(uat):
    db, _ = uat
    companies, users = count(db, Company), count(db, User)
    again = uat_seed.seed(db)
    assert again['created'] == {'co-uat-aster': False, 'co-uat-orbit': False}
    assert again['passwords'] == {}  # no password churn on rerun
    assert (count(db, Company), count(db, User)) == (companies, users)
    assert count(db, TeamMembership, 'co-uat-aster') == 9  # 4 Operations + 5 Commercial
    assert count(db, ProjectMembership, 'co-uat-aster') == 8  # 4 + 4


def test_login_works_for_each_role_and_scopes_tenant(uat):
    db, summary = uat
    pw = summary['passwords']
    for uid, role in [('uat-dana', 'ADMIN'), ('uat-marcus', 'MANAGER'), ('uat-elena', 'MANAGER'),
                      ('uat-priya', 'EMPLOYEE'), ('uat-mina', 'EMPLOYEE')]:
        r = login(f'{uid.removeprefix("uat-")}@aster.uat.test', pw[uid])
        assert r.status_code == 200, r.text
        me = TestClient(app).get('/api/auth/me', headers={'Authorization': 'Bearer ' + r.json()['token']})
        assert me.json()['role'] == role and me.json()['companyId'] == 'co-uat-aster'
    # Wrong password fails closed with the uniform 401.
    assert login('dana@aster.uat.test', 'wrong-password').status_code == 401


def test_foreign_tenant_is_isolated(uat):
    db, summary = uat
    r = login('orbit.admin@orbit.uat.test', summary['passwords']['uat-orbit-admin'])
    assert r.status_code == 200
    h = {'Authorization': 'Bearer ' + r.json()['token']}
    boot = TestClient(app).get('/api/bootstrap', headers=h)
    assert boot.status_code == 200 and boot.json()['companyId'] == 'co-uat-orbit'
    names = [u['name'] for u in boot.json()['users']]
    assert 'Rhea' in names and 'Theo' in names and 'Priya' not in names


def test_reset_wipes_only_uat_tenants_and_regenerates_credentials(uat):
    db, summary = uat
    # A bystander company that must survive any UAT reset.
    bystander, by_admin, _ = provision_company(db, company_name='Bystander Co',
        admin_name='Bystander Admin', admin_email='bystander@bystander.invalid', password='Bystander-Pass-1')
    db.commit()
    # Real UAT activity creating immutable history (canonical event + thanks).
    actor = db.get(User, 'uat-jonas')
    appreciation.create(db, actor, 'thanks',
        {'recipientUserId': 'uat-priya', 'message': 'Covered the shift', 'submissionId': 'uat-thanks-1'})
    db.commit()
    assert count(db, PeerThanks, 'co-uat-aster') == 1
    assert count(db, CanonicalEvent, 'co-uat-aster') > 0
    companies_before, users_before = count(db, Company), count(db, User)

    fresh = uat_seed.reset(db)
    assert fresh['created'] == {'co-uat-aster': True, 'co-uat-orbit': True}
    # UAT operational AND immutable history is gone; roster is back.
    assert count(db, PeerThanks, 'co-uat-aster') == 0
    assert count(db, CanonicalEvent, 'co-uat-aster') == 0
    assert count(db, User, 'co-uat-aster') == 10
    # Everything outside the two UAT tenants is untouched.
    assert (count(db, Company), count(db, User)) == (companies_before, users_before)
    assert db.get(Company, bystander.id) is not None and db.get(User, by_admin.id) is not None
    assert db.get(Company, 'gold-a') is not None
    # Credentials rotate: the old password dies, the new one works.
    assert login('dana@aster.uat.test', summary['passwords']['uat-dana']).status_code == 401
    assert login('dana@aster.uat.test', fresh['passwords']['uat-dana']).status_code == 200


def test_clean_process_cli_reset_covers_the_complete_schema(uat):
    """Reproduces the REAL CLI path: a fresh Python process running
    `python -m app.uat_seed reset`, WITHOUT the parent pytest process's
    incidental model imports (app.main, CanonicalEvent, PeerThanks…).

    Independent-review regression: the pre-patch harness registered only
    core+organization tables in a clean process, so the CLI reset silently
    orphaned feature-domain history instead of wiping it. This test fails
    against that version and passes once reset covers the full live schema."""
    db, summary = uat
    bystander, by_admin, _ = provision_company(db, company_name='CLI Bystander Co',
        admin_name='CLI Bystander', admin_email='cli-bystander@bystander.invalid',
        password='Bystander-Pass-1')
    db.commit()
    # Feature-domain history in tables uat_seed.py never imported directly.
    actor = db.get(User, 'uat-jonas')
    appreciation.create(db, actor, 'thanks',
        {'recipientUserId': 'uat-priya', 'message': 'CLI reset probe', 'submissionId': 'uat-thanks-cli'})
    db.commit()
    assert count(db, PeerThanks, 'co-uat-aster') == 1
    assert count(db, CanonicalEvent, 'co-uat-aster') > 0

    bind = db.get_bind()
    url = (bind.engine.url if hasattr(bind, 'engine') else bind.url).render_as_string(hide_password=False)
    env = {**os.environ, 'CVE_DATABASE_URL': url, 'CVE_DEV_MODE': 'true'}
    proc = subprocess.run([sys.executable, '-m', 'app.uat_seed', 'reset'],
                          cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload['created'] == {'co-uat-aster': True, 'co-uat-orbit': True}

    db.expire_all()  # see the subprocess's committed state, not the identity map
    # Feature history wiped by the clean process…
    assert count(db, PeerThanks, 'co-uat-aster') == 0
    assert count(db, CanonicalEvent, 'co-uat-aster') == 0
    # …UAT users and org structure reseeded…
    assert count(db, User, 'co-uat-aster') == 10
    assert count(db, TeamMembership, 'co-uat-aster') == 9
    assert count(db, ProjectMembership, 'co-uat-aster') == 8
    assert count(db, User, 'co-uat-orbit') == 2
    # …and every non-UAT company untouched.
    assert db.get(Company, bystander.id) is not None and db.get(User, by_admin.id) is not None
    assert db.get(Company, 'gold-a') is not None
    # The CLI rotated credentials and wrote the git-ignored artifact.
    assert login('dana@aster.uat.test', summary['passwords']['uat-dana']).status_code == 401
    artifact = Path(payload['credentialsFile'])
    assert artifact.exists() and 'uat-out' in str(artifact)
    dana_line = next(l for l in artifact.read_text(encoding='utf-8').splitlines()
                     if l.startswith('Dana'))
    assert login('dana@aster.uat.test', dana_line.split()[-1]).status_code == 200


def test_reset_refuses_when_a_uat_id_no_longer_names_a_uat_tenant(uat):
    db, _ = uat
    db.get(Company, 'co-uat-aster').name = 'Acme Production'  # id reused by someone else
    db.commit()
    with pytest.raises(DomainError) as error:
        uat_seed.reset(db)
    assert error.value.code == 'FORBIDDEN'
    db.rollback()
    assert count(db, User, 'co-uat-aster') == 10  # nothing was deleted


def test_production_mode_refuses_seeding(approval_db, monkeypatch):
    monkeypatch.setattr(settings, 'dev_mode', False)
    with pytest.raises(DomainError) as error:
        uat_seed.seed(approval_db)
    assert error.value.code == 'FORBIDDEN'
    with pytest.raises(DomainError):
        uat_seed.reset(approval_db)
    approval_db.rollback()
    assert approval_db.get(Company, 'co-uat-aster') is None
