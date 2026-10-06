from ..organization import service as organization
from ..organization.columns import scope, fields
from .common import scoped_command
"""Small, row-locked Help lifecycle. Only requester confirmation emits an event."""
from ..capabilities.service import requires
from sqlalchemy import select
from ..domain import DomainError
from ..models import now_ms
from .model import HelpRequest
from .common import command,members,retry_lock,history,emit
from . import routing


def view(row):
    return dict(**({'scope':scope(row)} if row.team_id or row.project_id else {}),id=row.id,companyId=row.company_id,requesterUserId=row.requester_user_id,
        title=row.title,description=row.description,status=row.status,createdAt=row.created_at,
        acceptedByUserId=row.accepted_by_user_id,acceptedAt=row.accepted_at,
        finishedAt=row.finished_at,confirmedAt=row.confirmed_at,
        routingStatus=row.routing_status,routedAt=row.routed_at,escalatedAt=row.escalated_at)


@organization.guarded
@requires("HELP")
def create(db,actor,body):
    data,context=scoped_command(body,{'title':200,'description':1000,'submissionId':100})
    retry_lock(db,actor.company_id,actor.id,'help',data['submissionId'])
    actor=members(db,actor.company_id,{actor.id})[actor.id]
    row=db.scalar(select(HelpRequest).where(HelpRequest.company_id==actor.company_id,
        HelpRequest.requester_user_id==actor.id,HelpRequest.submission_id==data['submissionId']))
    if row:
        if row.title!=data['title'] or row.description!=data['description'] or scope(row)!=context:
            raise DomainError('BAD_STATE','Submission identity already used with different content')
        return view(row)
    organization.admit(db,actor,context)
    row=HelpRequest(**fields(context),company_id=actor.company_id,requester_user_id=actor.id,title=data['title'],
                    description=data['description'],submission_id=data['submissionId'])
    db.add(row); db.flush()
    history(db,actor,'HELP_REQUESTED',{'helpId':row.id,'title':row.title})
    # WS1: route to the bounded scope audience (never a broadcast). The
    # requester is excluded; recipient snapshots land in help_routings.
    routing.route_initial(db,actor,row,context)
    return view(row)


@organization.guarded
@requires("HELP")
def transition(db,actor,identity,action):
    row=db.scalar(select(HelpRequest).where(HelpRequest.company_id==actor.company_id,HelpRequest.id==identity)
                  .with_for_update().execution_options(populate_existing=True))
    if row is None: raise DomainError('NOT_FOUND','Help request not found')
    ids={actor.id,row.requester_user_id}
    if row.accepted_by_user_id: ids.add(row.accepted_by_user_id)
    actor=members(db,actor.company_id,ids)[actor.id]
    if action=='accept':
        if actor.id==row.requester_user_id: raise DomainError('FORBIDDEN','Requester cannot accept own request')
        if row.accepted_by_user_id==actor.id: return view(row)
        if row.status!='OPEN': raise DomainError('BAD_STATE','Help is already assigned')
        organization.admit(db,actor,scope(row))
        row.accepted_by_user_id=actor.id; row.accepted_at=now_ms(); row.status='ACCEPTED'
        recipient=row.requester_user_id; code='HELP_ACCEPTED'; level='INFORMATIONAL'
    elif action=='finish':
        if actor.id!=row.accepted_by_user_id: raise DomainError('FORBIDDEN','Only the assigned helper may finish')
        if row.status in ('FINISHED','CONFIRMED'): return view(row)
        if row.status!='ACCEPTED': raise DomainError('BAD_STATE','Help must be accepted first')
        organization.admit(db,actor,scope(row))
        row.finished_at=now_ms(); row.status='FINISHED'
        recipient=row.requester_user_id; code='HELP_FINISHED'; level='ACTION_REQUIRED'
    elif action=='confirm':
        if actor.id!=row.requester_user_id: raise DomainError('FORBIDDEN','Only the requester may confirm')
        if row.status=='CONFIRMED': return view(row)
        if row.status!='FINISHED': raise DomainError('BAD_STATE','Help must be finished first')
        organization.admit(db,actor,scope(row),participants=[row.accepted_by_user_id])
        row.confirmed_at=now_ms(); row.status='CONFIRMED'
        emit(db,actor.company_id,'collaboration.help','internal.help.completed',row.id,
             actor.id,row.accepted_by_user_id,row.confirmed_at,{'helpId':row.id},context=scope(row))
        recipient=row.accepted_by_user_id; code='HELP_CONFIRMED'; level='INFORMATIONAL'
    else: raise DomainError('VALIDATION','Unknown Help action')
    history(db,actor,code,{'helpId':row.id,'title':row.title,'status':row.status},recipient,level)
    db.flush()
    return view(row)


@organization.guarded
def listing(db,actor):
    members(db,actor.company_id,{actor.id})
    return [view(row) for row in db.scalars(select(HelpRequest).where(HelpRequest.company_id==actor.company_id)
        .order_by(HelpRequest.created_at.desc(),HelpRequest.id).limit(100))
        if organization.allowed(db,actor,scope(row),manager=actor.role=='MANAGER')]
