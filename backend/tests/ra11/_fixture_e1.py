"""E1 fixture subprocess: create one team, memberships, and N team-scoped
OPEN tasks so bootstrap's can_view path exercises the organization SHARED
advisory lock. Test-only data setup; no application code change."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db import session_scope  # noqa: E402
from app.models import Task, now_ms  # noqa: E402
from app.organization.model import Team, TeamMembership  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 400

with session_scope() as db:
    team = Team(company_id='co-aster', name='E1 Scope Team')
    db.add(team)
    db.flush()
    for uid in ('u-dana', 'u-marcus', 'u-priya', 'u-jonas', 'u-aisha'):
        db.add(TeamMembership(company_id='co-aster', team_id=team.id,
                              user_id=uid, manager=uid == 'u-marcus'))
    now = now_ms()
    for i in range(N):
        db.add(Task(id=f't-e1-{i:04d}', company_id='co-aster',
                    title=f'E1 scoped task {i}', description='',
                    priority='NORMAL', deadline=None, reward=1,
                    audience='EMPLOYEES', assign_mode='ALL_EMPLOYEES',
                    assignee_id=None, status='OPEN', owner_id=None,
                    cycle=1, verified=0, reported=0, paid=0,
                    created_at=now, updated_at=now, created_by='u-marcus',
                    team_id=team.id))
print(f'fixture: team + {N} scoped tasks')
