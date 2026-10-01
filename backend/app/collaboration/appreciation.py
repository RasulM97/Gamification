"""Thanks and manager recognition; no economic authority or orchestration."""
from ..capabilities.service import require
from sqlalchemy import select
from ..domain import DomainError
from .model import PeerThanks,ManagerRecognition
from .common import command,members,retry_lock,history,emit

KINDS={'thanks':(PeerThanks,'internal.peer.thanks','PEER_THANKS'),
       'recognition':(ManagerRecognition,'internal.manager.recognition','MANAGER_RECOGNITION')}


def view(row):
    sender='issuerUserId' if isinstance(row,ManagerRecognition) else 'senderUserId'
    return dict(id=row.id,companyId=row.company_id,**{sender:row.sender_user_id},
                recipientUserId=row.recipient_user_id,message=row.message,createdAt=row.created_at)


def create(db,actor,kind,body):
    require(db,actor.company_id,{'thanks':'THANKS','recognition':'RECOGNITION'}[kind])
    data=command(body,{'recipientUserId':40,'message':1000,'submissionId':100})
    model,event_type,code=KINDS[kind]
    retry_lock(db,actor.company_id,actor.id,kind,data['submissionId'])
    people=members(db,actor.company_id,{actor.id,data['recipientUserId']})
    actor=people[actor.id]; target=people[data['recipientUserId']]
    if actor.id==target.id: raise DomainError('FORBIDDEN','Self recognition is not permitted')
    if kind=='recognition' and (actor.role not in ('ADMIN','MANAGER') or target.role not in ('EMPLOYEE','MANAGER')):
        raise DomainError('FORBIDDEN','Manager authority and a participant recipient required')
    row=db.scalar(select(model).where(model.company_id==actor.company_id,
        model.sender_user_id==actor.id,model.submission_id==data['submissionId']))
    if row:
        if row.recipient_user_id!=target.id or row.message!=data['message']:
            raise DomainError('BAD_STATE','Submission identity already used with different content')
        return view(row)
    row=model(company_id=actor.company_id,sender_user_id=actor.id,recipient_user_id=target.id,
              message=data['message'],submission_id=data['submissionId'])
    db.add(row); db.flush()
    emit(db,actor.company_id,'collaboration.'+kind,event_type,row.id,actor.id,target.id,row.created_at,
         {'recordId':row.id,'messageLength':len(row.message)})
    history(db,actor,code,{'targetUserId':target.id,'target':target.name,'recordId':row.id,'reason':row.message},target.id)
    return view(row)


def received(db,actor,kind):
    members(db,actor.company_id,{actor.id})
    model=KINDS[kind][0]
    return [view(row) for row in db.scalars(select(model).where(model.company_id==actor.company_id,
        (model.sender_user_id==actor.id)|(model.recipient_user_id==actor.id))
        .order_by(model.created_at.desc(),model.id).limit(100))]
