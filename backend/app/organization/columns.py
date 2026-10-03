"""Fixed optional work context; no hierarchy or polymorphic ACL."""
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column


class ScopeColumns:
    team_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True)


def constraints(name):
    return (
        CheckConstraint('team_id IS NULL OR project_id IS NULL', name='ck_'+name+'_scope'),
        ForeignKeyConstraint(['company_id', 'team_id'], ['teams.company_id', 'teams.id'], name='fk_'+name+'_team'),
        ForeignKeyConstraint(['company_id', 'project_id'], ['projects.company_id', 'projects.id'], name='fk_'+name+'_project'),
    )


def scope(value):
    if getattr(value, 'team_id', None): return {'kind': 'TEAM', 'id': value.team_id}
    if getattr(value, 'project_id', None): return {'kind': 'PROJECT', 'id': value.project_id}
    return {'kind': 'COMPANY'}


def fields(value):
    return {'team_id': value.get('id') if value['kind']=='TEAM' else None,
            'project_id': value.get('id') if value['kind']=='PROJECT' else None}
