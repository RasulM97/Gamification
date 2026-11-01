"""Task-scoped recommendations; never decisions, payout authorizations or ledger writes."""
from sqlalchemy import select
from .models import Submission, TaskRecommendation, User
from .domain import DomainError
from .capabilities.service import requires
from .organization.service import exclusive_guarded, capture
from .organization.columns import scope
from .task_access import require_view, require_review, admit_review, require_payout_authority
from .service_common import get_task, act, notes, snap, managers
from .canonical_events.contracts import EventInput
from .internal_event_recorder import record_internal_event


def current_submission(db, task):
    return db.scalar(select(Submission).where(Submission.company_id == task.company_id,
        Submission.task_id == task.id, Submission.cycle == task.cycle,
        Submission.user_id == task.owner_id, Submission.outcome == 'PENDING')
        .order_by(Submission.at.desc(), Submission.id.desc()).limit(1))


def recommendation_status(row, task, submission, current_id):
    if submission.outcome in ('APPROVED', 'REJECTED'):
        return 'RESOLVED'
    if (task.status == 'SUBMITTED' and row.cycle == task.cycle
            and row.submission_id == current_id and submission.outcome == 'PENDING'):
        return 'PENDING'
    return 'SUPERSEDED'


def for_task(db, task):
    current = current_submission(db, task)
    rows = db.execute(select(TaskRecommendation, Submission).join(Submission,
        (Submission.id == TaskRecommendation.submission_id) &
        (Submission.company_id == TaskRecommendation.company_id)).where(
        TaskRecommendation.company_id == task.company_id, TaskRecommendation.task_id == task.id)
        .order_by(TaskRecommendation.created_at, TaskRecommendation.id))
    return [dict(id=r.id, companyId=r.company_id, taskId=r.task_id, cycle=r.cycle,
        submissionId=r.submission_id, authorId=r.author_id, authorName=r.author_name,
        note=r.note, at=r.created_at, status=recommendation_status(r, task, sub, current.id if current else None))
        for r, sub in rows]


@exclusive_guarded
@requires('TASK_LITE')
def recommend(db, actor, task_id, *, submission_id, cycle, note_text):
    if actor.role != 'MANAGER' or actor.active is False or actor.activation_hash:
        raise DomainError('FORBIDDEN', 'Active manager required')
    task = get_task(db, actor.company_id, task_id)
    require_view(task, actor)
    admit_review(db, task, actor)
    require_review(db, task, actor)
    if not isinstance(note_text, str) or not 1 <= len(note_text.strip()) <= 2000:
        raise DomainError('VALIDATION', 'Recommendation note must contain 1 to 2000 characters')
    pending = current_submission(db, task)
    if (task.status != 'SUBMITTED' or type(cycle) is not int or task.cycle != cycle
            or pending is None or pending.id != submission_id):
        raise DomainError('STALE_SUBMISSION', 'The current submission changed; refresh before recommending')
    try:
        require_payout_authority(db, task, actor, max(0, task.reward - task.paid))
    except DomainError as exc:
        if exc.code != 'ECONOMIC_AUTHORITY_REQUIRED':
            raise
    else:
        raise DomainError('RECOMMENDATION_NOT_REQUIRED', 'Use the existing authorized review action')
    existing = db.scalar(select(TaskRecommendation).where(
        TaskRecommendation.company_id == actor.company_id, TaskRecommendation.submission_id == submission_id))
    if existing:
        if existing.author_id == actor.id and existing.note == note_text.strip():
            return existing
        raise DomainError('RECOMMENDATION_EXISTS', 'This submission already has an immutable recommendation')
    row = TaskRecommendation(company_id=actor.company_id, task_id=task.id, cycle=cycle,
        submission_id=submission_id, author_id=actor.id, author_name=actor.name, note=note_text.strip())
    db.add(row)
    db.flush()
    params = snap(db, actor, task, recommendationId=row.id, submissionId=submission_id)
    act(db, actor.company_id, actor.id, 'TASK_APPROVAL_RECOMMENDED', params)
    notes(db, actor.company_id, [u.id for u in managers(db, actor.company_id) if u.role == 'ADMIN'],
          'ACTION_REQUIRED', 'Reviews', 'TASK_APPROVAL_RECOMMENDED', params)
    event = record_internal_event(db, actor.company_id, lambda: EventInput(
        type='internal.task.approval_recommended', schema_version=1, source_kind='TASK_LITE',
        source_id=task.id, source_event_id=row.id, actor_id=actor.id, subject_id=task.owner_id,
        occurred_at=row.created_at, payload=dict(taskId=task.id, cycle=cycle,
            submissionId=submission_id, recommendationId=row.id),
        correlation_id=f'task:{task.id}:cycle:{cycle}'))
    capture(db, actor.company_id, event.id, scope(task))
    return row
