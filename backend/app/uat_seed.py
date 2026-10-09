"""UAT Stage A — deterministic synthetic-company seed/reset. DEVELOPMENT ONLY.

CLI (from backend/):
    python -m app.uat_seed seed     # create the UAT tenants if absent (idempotent)
    python -m app.uat_seed reset    # wipe ONLY the UAT tenants and reseed them

Guards (fail closed, all must hold):
- CVE_DEV_MODE must be explicitly enabled — the same rule the existing
  destructive development reset (workspace_reset) uses;
- CLI only: no HTTP route exists, so this can never become an unauthenticated
  or production API;
- only the two hardcoded UAT company ids below can ever be touched — there is
  no parameter that could target an arbitrary (production) company.

Tenants:
- co-uat-aster  "Aster Dynamics UAT": 1 Admin + 2 Managers + 7 Employees,
  two Teams (Operations, Commercial), two Projects (Northstar Launch,
  Customer Migration);
- co-uat-orbit  "Orbit Labs UAT": one foreign Admin + one foreign Employee,
  existing purely for tenant-isolation probing.

Determinism: company/user/org ids and emails are fixed. Passwords are
generated per (re)creation and written by the CLI to the git-ignored local
artifact uat-out/credentials.txt — never to git, docs, logs or the API.
Rerunning `seed` on an existing UAT set is a no-op (no duplicates, passwords
unchanged). `reset` regenerates passwords and rewrites the artifact.

Reset design (why): tenant history tables are trigger-immutable BY DESIGN
(canonical_events, ledger, memberships, deliveries, decisions…), exactly like
the existing doctrine "use a separate test company" once history exists. A
repeatable UAT reset therefore deletes every row of the two synthetic tenants
inside one transaction under session_replication_role='replica' (which also
defers FK trigger checks while the whole tenant set is removed). This SET
requires superuser: the local pgserver test cluster has it; a production
deployment's application user does not, so the reset aborts there instead of
ever silently succeeding. This mirrors workspace_reset's existing audited
exception philosophy, scoped to whole-tenant disposal of synthetic data.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .config import settings
from .domain import DomainError
from .models import Base, Company, CompanySettings, User
from .organization.model import Project, ProjectMembership, Team, TeamMembership
from .password_policy import validate_password
from .security import hash_password

ASTER_ID = 'co-uat-aster'
ORBIT_ID = 'co-uat-orbit'
UAT_COMPANY_IDS = (ASTER_ID, ORBIT_ID)

# (id, name, role, position) — deterministic roster, fictional .test logins.
ASTER_ROSTER = [
    ('uat-dana', 'Dana', 'ADMIN', 'Operations Director'),
    ('uat-marcus', 'Marcus', 'MANAGER', 'Commercial Team Lead'),
    ('uat-elena', 'Elena', 'MANAGER', 'Operations Team Lead'),
    ('uat-priya', 'Priya', 'EMPLOYEE', 'Account Executive'),
    ('uat-jonas', 'Jonas', 'EMPLOYEE', 'Field Coordinator'),
    ('uat-aisha', 'Aisha', 'EMPLOYEE', 'Business Analyst'),
    ('uat-leo', 'Leo', 'EMPLOYEE', 'Support Specialist'),
    ('uat-sara', 'Sara', 'EMPLOYEE', 'Sales Associate'),
    ('uat-noah', 'Noah', 'EMPLOYEE', 'Implementation Associate'),
    ('uat-mina', 'Mina', 'EMPLOYEE', 'Operations Analyst'),
]
ORBIT_ROSTER = [
    ('uat-orbit-admin', 'Rhea', 'ADMIN', 'Site Administrator'),
    ('uat-orbit-employee', 'Theo', 'EMPLOYEE', 'Technician'),
]

TEAMS = [  # (id, name, manager_user_id, [employee_user_ids])
    ('uat-team-operations', 'Operations', 'uat-elena', ['uat-aisha', 'uat-leo', 'uat-mina']),
    ('uat-team-commercial', 'Commercial', 'uat-marcus', ['uat-priya', 'uat-jonas', 'uat-sara', 'uat-noah']),
]
PROJECTS = [
    ('uat-proj-northstar', 'Northstar Launch', 'uat-marcus', ['uat-priya', 'uat-jonas', 'uat-aisha']),
    ('uat-proj-migration', 'Customer Migration', 'uat-elena', ['uat-sara', 'uat-noah', 'uat-mina']),
]

CREDENTIALS_PATH = Path(__file__).resolve().parents[2] / 'uat-out' / 'credentials.txt'


def _guard():
    # Same explicitness rule as workspace_reset: the historical default of
    # dev_mode is True, so a destructive tool requires CVE_DEV_MODE (or an
    # explicit Settings(dev_mode=...)) to have been supplied.
    if not settings.dev_mode or 'dev_mode' not in settings.model_fields_set:
        raise DomainError('FORBIDDEN', 'UAT seeding requires explicit development mode (CVE_DEV_MODE)')


def _email(user_id: str, company: str) -> str:
    local = user_id.removeprefix('uat-').replace('-', '.')
    return f'{local}@{company}.uat.test'


def _create_company(db: Session, company_id: str, name: str, roster: list[tuple[str, str, str, str]],
                    passwords: dict[str, str]) -> bool:
    """Create one UAT tenant with its roster. Returns False (no-op) if present."""
    if db.get(Company, company_id) is not None:
        return False
    db.add(Company(id=company_id, name=name, seq=0, onboarding_status='COMPLETED'))
    db.add(CompanySettings(company_id=company_id))
    for user_id, user_name, role, position in roster:
        password = secrets.token_urlsafe(9)  # ~12 random chars; local artifact only
        validate_password(password)
        passwords[user_id] = password
        db.add(User(id=user_id, company_id=company_id, name=user_name,
                    email=_email(user_id, 'aster' if company_id == ASTER_ID else 'orbit'),
                    role=role, position=position, password_hash=hash_password(password),
                    notif_muted=[]))
    return True


def _create_org(db: Session) -> None:
    for team_id, name, manager_id, employee_ids in TEAMS:
        db.add(Team(id=team_id, company_id=ASTER_ID, name=name))
        db.flush()
        db.add(TeamMembership(company_id=ASTER_ID, team_id=team_id, user_id=manager_id, manager=True))
        for user_id in employee_ids:
            db.add(TeamMembership(company_id=ASTER_ID, team_id=team_id, user_id=user_id))
    for project_id, name, manager_id, member_ids in PROJECTS:
        db.add(Project(id=project_id, company_id=ASTER_ID, name=name))
        db.flush()
        db.add(ProjectMembership(company_id=ASTER_ID, project_id=project_id, user_id=manager_id, manager=True))
        for user_id in member_ids:
            db.add(ProjectMembership(company_id=ASTER_ID, project_id=project_id, user_id=user_id))


def seed(db: Session) -> dict:
    """Idempotent creation of both UAT tenants. Returns summary + fresh
    credentials (only for tenants actually created this call)."""
    _guard()
    passwords: dict[str, str] = {}
    created = {
        ASTER_ID: _create_company(db, ASTER_ID, 'Aster Dynamics UAT', ASTER_ROSTER, passwords),
        ORBIT_ID: _create_company(db, ORBIT_ID, 'Orbit Labs UAT', ORBIT_ROSTER, passwords),
    }
    if created[ASTER_ID]:
        _create_org(db)
    db.commit()
    return {'created': created, 'passwords': passwords}


def reset(db: Session) -> dict:
    """Wipe ONLY the two UAT tenants (every table, one transaction) and reseed.

    Refuses — before touching anything — if any other company would be
    affected: the delete predicate is the hardcoded UAT id tuple, and the
    superuser-only session flag makes the whole operation impossible on a
    production role."""
    _guard()
    ids = list(UAT_COMPANY_IDS)
    # Fail-closed existence check: never run a destructive pass keyed on ids
    # that do not match the hardcoded UAT tenants by name.
    rows = {c.id: c.name for c in db.scalars(select(Company).where(Company.id.in_(ids)))}
    expected = {ASTER_ID: 'Aster Dynamics UAT', ORBIT_ID: 'Orbit Labs UAT'}
    for company_id, name in rows.items():
        if expected.get(company_id) != name:
            raise DomainError('FORBIDDEN', f'Refusing reset: {company_id} is not the expected UAT tenant')
    # Superuser-only: bypasses the by-design history immutability triggers for
    # this scoped synthetic-tenant disposal. Fails (and aborts the reset) on
    # any deployment whose application role lacks the privilege.
    db.execute(text("SET LOCAL session_replication_role = 'replica'"))
    for table in reversed(Base.metadata.sorted_tables):
        if 'company_id' in table.c:
            db.execute(delete(table).where(table.c.company_id.in_(ids)))
    db.execute(delete(Company).where(Company.id.in_(ids)))
    db.flush()
    return seed(db)


def _write_credentials(summary: dict) -> Path | None:
    passwords = summary['passwords']
    if not passwords:
        return None
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ['CVE UAT credentials — LOCAL OPERATOR ARTIFACT, never commit or share.',
             'Generated by python -m app.uat_seed. Regenerate with: python -m app.uat_seed reset', '']
    for company_id, roster, label in ((ASTER_ID, ASTER_ROSTER, 'Aster Dynamics UAT'),
                                      (ORBIT_ID, ORBIT_ROSTER, 'Orbit Labs UAT')):
        company = 'aster' if company_id == ASTER_ID else 'orbit'
        lines.append(f'[{label}]')
        for user_id, user_name, role, _position in roster:
            if user_id in passwords:
                lines.append(f'{user_name:<10} {role:<9} {_email(user_id, company):<32} {passwords[user_id]}')
        lines.append('')
    CREDENTIALS_PATH.write_text('\n'.join(lines), encoding='utf-8')
    return CREDENTIALS_PATH


def main(argv=None):
    parser = argparse.ArgumentParser(description='UAT synthetic-company seed/reset (development only)')
    parser.add_argument('action', choices=['seed', 'reset'])
    args = parser.parse_args(argv)
    from .db import session_scope
    with session_scope() as db:
        summary = (reset if args.action == 'reset' else seed)(db)
    artifact = _write_credentials(summary)
    out = {'action': args.action, 'created': summary['created'],
           'credentialsFile': str(artifact) if artifact else None,
           'note': 'existing UAT tenants untouched' if not artifact else 'credentials written (git-ignored)'}
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
