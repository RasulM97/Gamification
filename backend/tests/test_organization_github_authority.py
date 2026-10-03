"""Explicit resource attribution rejects inferred authority and preserves history."""
import pytest
import sqlalchemy as sa
from app.domain import DomainError
from app.github_connector import attribution
from app.github_connector.model import GithubProjectAttribution
from app.capabilities.service import update
from app.organization import service as org
from tests.github_helpers import github
from tests.approval_helpers import approval_db, golden_db
from tests.test_organization import actor, context


@pytest.mark.parametrize('attack', ['employee', 'manager', 'foreign_admin', 'foreign_project', 'closed_project', 'disabled'])
def test_attribution_authority(github, attack):
    _, db, source, _ = github
    target = context(db)
    admin = actor(db)
    caller = admin
    if attack in ('employee', 'manager', 'foreign_admin'):
        caller = actor(db, {'employee':'ap-employee', 'manager':'org-manager', 'foreign_admin':'gold-admin-b'}[attack])
    elif attack == 'foreign_project':
        project = org.create(db, actor(db, 'gold-admin-b'), 'PROJECT', {'name':'Foreign'})
        target = {'kind':'PROJECT', 'id':project['id']}
    elif attack == 'closed_project':
        org.close(db, admin, target)
    else:
        update(db, admin, 'GITHUB_CONNECTOR', {'enabled':False})
    db.commit()
    with pytest.raises(DomainError):
        attribution.assign(db, caller, source['id'], 'issue', '1001', {'projectId':target['id']})
    db.rollback()
    assert db.scalar(sa.select(sa.func.count()).select_from(GithubProjectAttribution)) == 0


@pytest.mark.parametrize('kind,resource', [('branch','1001'), ('issue','feature/project-a'), ('issue','01'), ('issue','-1')])
def test_only_supported_numeric_resource_identity(github, kind, resource):
    _, db, source, _ = github
    target = context(db)
    with pytest.raises(DomainError):
        attribution.assign(db, actor(db), source['id'], kind, resource, {'projectId':target['id']})
    db.rollback()


def test_assignment_changes_are_audited_and_intervals_cannot_be_rewritten(github):
    _, db, source, _ = github
    first, second = context(db), context(db)
    admin = actor(db)
    for target in (first, second):
        attribution.assign(db, admin, source['id'], 'issue', '1001', {'projectId':target['id']})
        db.commit()
    history = attribution.history(db, admin, source['id'])['attributions']
    assert [row['projectId'] for row in history] == [first['id'], second['id']]
    assert history[0]['effectiveUntil'] == history[1]['effectiveFrom']
    db.commit()
    with pytest.raises(sa.exc.IntegrityError):
        db.execute(sa.update(GithubProjectAttribution).where(GithubProjectAttribution.id == history[0]['id'])
                   .values(project_id=second['id']))
        db.flush()
    db.rollback()
    assert attribution.history(db, admin, source['id'])['attributions'] == history
