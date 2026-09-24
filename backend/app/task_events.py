"""Task-owned review facts; never copy descriptions, reasons or file content."""
from typing import Literal
from sqlalchemy.orm import Session
from .canonical_events.contracts import EventInput, StoredEvent
from .internal_event_recorder import record_internal_event
from .models import Activity, Task, User


def record_task_review(db: Session, actor: User, task: Task, audit: Activity,
                       outcome: Literal['approved', 'rejected']) -> StoredEvent:
    def build():
        if outcome not in ('approved', 'rejected'):
            raise ValueError('Unsupported task observation')
        payload = dict(taskId=task.id, cycle=task.cycle, ownerId=task.owner_id,
                       reviewerId=actor.id, verifiedProgress=task.verified,
                       priority=task.priority, audience=task.audience)
        if outcome == 'approved':
            payload.update(reward=task.reward, paid=task.paid)
        else:
            payload.update(reportedProgress=task.reported, reasonReference=audit.id)
        return EventInput(type=f'internal.task.{outcome}', schema_version=1,
                          source_kind='TASK_LITE', source_id=task.id,
                          source_event_id=f'{outcome}:{audit.id}',
                          actor_id=actor.id, subject_id=task.owner_id,
                          occurred_at=task.updated_at, payload=payload,
                          correlation_id=f'task:{task.id}:cycle:{task.cycle}')
    return record_internal_event(db, actor.company_id, build)
