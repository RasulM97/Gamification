"""Company/source/numeric resource attribution, independent of canonical payload."""
from sqlalchemy import select
from ..domain import DomainError
from ..capabilities.service import require
from ..models import now_ms
from ..organization import service as organization
from .model import GithubProjectAttribution
from .management import owned, external_id, exact


def assign(db,actor,source_id,kind,resource_id,body):
    organization.lock(db,actor.company_id,exclusive=True)
    require(db,actor.company_id,'GITHUB_CONNECTOR')
    source=owned(db,actor,source_id)
    if kind not in ('issue','pull_request'):raise DomainError('VALIDATION','Unsupported GitHub resource')
    resource_id=external_id(resource_id);exact(body,('projectId',))
    project=body['projectId']
    if project is not None:organization.unit(db,actor.company_id,{'kind':'PROJECT','id':project},active=True)
    row=db.scalar(select(GithubProjectAttribution).where(GithubProjectAttribution.company_id==actor.company_id,
        GithubProjectAttribution.source_id==source.id,GithubProjectAttribution.resource_kind==kind,
        GithubProjectAttribution.resource_id==resource_id,GithubProjectAttribution.left_at.is_(None)))
    if (row.project_id if row else None)==project:
        return {'projectId':project,'resourceId':resource_id,'resourceKind':kind}
    stamp=now_ms()
    if row:row.left_at=max(stamp,row.joined_at)
    db.flush()
    if project is not None:
        db.add(GithubProjectAttribution(company_id=actor.company_id,source_id=source.id,resource_kind=kind,
            resource_id=resource_id,project_id=project,joined_at=stamp))
    organization.audit(db,actor,'GITHUB_ATTRIBUTION',dict(sourceId=source.id,resourceKind=kind,
        resourceId=resource_id,previousProjectId=row.project_id if row else None,projectId=project,effectiveAt=stamp))
    db.flush()
    return {'projectId':project,'resourceId':resource_id,'resourceKind':kind}


def resolve(db,source,event):
    kind=event.type.split('.')[1]
    row=db.scalar(select(GithubProjectAttribution).where(GithubProjectAttribution.company_id==source.company_id,
        GithubProjectAttribution.source_id==source.id,GithubProjectAttribution.resource_kind==kind,
        GithubProjectAttribution.resource_id==event.payload['resourceId'],GithubProjectAttribution.joined_at<=event.occurred_at,
        (GithubProjectAttribution.left_at.is_(None))|(GithubProjectAttribution.left_at>event.occurred_at)))
    value={'kind':'PROJECT','id':row.project_id} if row else {'kind':'COMPANY'}
    organization.unit(db,source.company_id,value,at=event.occurred_at)
    return value,{'origin':'GITHUB_RESOURCE','attributionId':row.id if row else None}


def history(db,actor,source_id):
    organization.lock(db,actor.company_id)
    source=owned(db,actor,source_id)
    return {'attributions':[dict(id=r.id,resourceKind=r.resource_kind,resourceId=r.resource_id,
        projectId=r.project_id,effectiveFrom=r.joined_at,effectiveUntil=r.left_at)
        for r in db.scalars(select(GithubProjectAttribution).where(GithubProjectAttribution.company_id==actor.company_id,
            GithubProjectAttribution.source_id==source.id).order_by(GithubProjectAttribution.joined_at,GithubProjectAttribution.id))]}
