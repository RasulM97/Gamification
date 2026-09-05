"""HTTP layer (M1 §5–§8). Domain-oriented endpoints — one per frozen action,
no generic POST /actions. Thin: parse → (stage files) → service → commit →
return the fresh bootstrap payload. All rule enforcement lives in services;
the frontend is never the security boundary.

Every mutating response carries the full refreshed bootstrap state, so the
client simply replaces its store with the authoritative server truth.
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import services as svc
from .config import settings
from .db import get_db, log_action
from .domain import DomainError, UploadCandidate, can_see_task, validate_attachments
from .models import Attachment, Company, Task, User
from .security import check_password, current_user, make_token
from .serializers import bootstrap
from .storage import StoredFile, storage

router = APIRouter(prefix='/api')


def _company(db: Session, actor: User) -> Company:
    return db.get(Company, actor.company_id)


def _state(db: Session, actor: User) -> dict:
    return bootstrap(db, _company(db, actor))


def mutate(db: Session, actor: User, action: str, entity: str, fn,
           staged: list[StoredFile] | None = None) -> dict:
    """Run one service action as one transaction; on any failure roll back
    AND delete staged files so failed submissions leave no orphan bytes."""
    t0 = time.perf_counter()
    try:
        fn()
        db.commit()
    except Exception as e:
        db.rollback()
        for f in staged or []:
            storage.delete(f.storage_path)
        log_action(actor.id, actor.role, actor.company_id, action, entity,
                   'refused' if isinstance(e, DomainError) else 'error',
                   (time.perf_counter() - t0) * 1000,
                   getattr(e, 'code', type(e).__name__))
        raise
    log_action(actor.id, actor.role, actor.company_id, action, entity, 'ok',
               (time.perf_counter() - t0) * 1000)
    return _state(db, actor)


async def stage_files(db: Session, actor: User,
                      uploads: list[UploadFile]) -> list[StoredFile]:
    """Validate against company §18 policy, then stage bytes in storage.
    Validation happens BEFORE anything touches disk."""
    if not uploads:
        return []
    s = svc.settings_of(db, actor.company_id)
    read: list[tuple[str, str, bytes]] = []
    for up in uploads:
        data = await up.read()
        read.append((up.filename or 'file', up.content_type or '', data))
    candidates = [UploadCandidate(name=n, size=len(d), type=t) for n, t, d in read]
    errors = validate_attachments(candidates, s.max_file_size_mb, s.max_submission_total_mb)
    if errors:
        raise DomainError('UPLOAD_REJECTED', ' · '.join(errors))
    return [StoredFile(name=n, size=len(d), type=t,
                       storage_path=storage.save(actor.company_id, n, d))
            for n, t, d in read]


# ── auth ────────────────────────────────────────────────────────────────────


class LoginIn(BaseModel):
    email: str
    password: str


@router.post('/auth/login')
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if u is None or not check_password(body.password, u.password_hash):
        # never log the password; never reveal which half failed
        log_action('-', '-', '-', 'login', body.email, 'denied', 0)
        raise HTTPException(401, {'code': 'AUTH_INVALID', 'message': 'Invalid email or password'})
    log_action(u.id, u.role, u.company_id, 'login', u.email, 'ok', 0)
    return {'token': make_token(u), 'user': _me(u)}


def _me(u: User) -> dict:
    c = u.company_id
    return {'id': u.id, 'name': u.name, 'role': u.role, 'position': u.position,
            'email': u.email, 'companyId': c}


@router.get('/auth/me')
def me(actor: User = Depends(current_user)):
    return _me(actor)


@router.get('/dev/personas')
def dev_personas(db: Session = Depends(get_db)):
    """Demo quick-login list. DEV_MODE only — never in production."""
    if not settings.dev_mode:
        raise HTTPException(404, {'code': 'NOT_FOUND', 'message': 'Not found'})
    users = list(db.scalars(select(User).order_by(User.role, User.name)))
    return {'personas': [
        {'id': u.id, 'name': u.name, 'role': u.role, 'position': u.position,
         'email': u.email, 'password': 'demo1234'} for u in users]}


@router.post('/dev/reseed')
def dev_reseed(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    """Demo control: wipe all tables and re-run the deterministic seed.
    DEV_MODE only, admin role required. Never available in production."""
    if not settings.dev_mode:
        raise HTTPException(404, {'code': 'NOT_FOUND', 'message': 'Not found'})
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admin role required')
    from sqlalchemy import text
    from .models import Base
    from .seed import run as seed_run
    actor_id, actor_role, actor_cid = actor.id, actor.role, actor.company_id
    db.execute(text(f'TRUNCATE {", ".join(Base.metadata.tables.keys())} CASCADE'))
    db.expunge_all()  # drop stale identity-map entries (incl. the actor row)
    seed_run(db)
    db.commit()
    log_action(actor_id, actor_role, actor_cid, 'dev_reseed', 'all', 'ok', 0)
    return _state(db, db.get(User, actor_id))


# ── bootstrap ───────────────────────────────────────────────────────────────


@router.get('/bootstrap')
def get_bootstrap(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return _state(db, actor)


# ── tasks ───────────────────────────────────────────────────────────────────


@router.post('/tasks')
async def create_task(
    title: str = Form(...), description: str = Form(''),
    priority: str = Form('NORMAL'), deadline: Optional[str] = Form(None),
    reward: float = Form(...), audience: str = Form('EMPLOYEES'),
    assignMode: str = Form('ALL_EMPLOYEES'),
    assigneeId: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
    actor: User = Depends(current_user), db: Session = Depends(get_db),
):
    staged = await stage_files(db, actor, files)
    return mutate(db, actor, 'create_task', title, lambda: svc.create_task(
        db, actor, title=title, description=description, priority=priority,
        deadline=deadline, reward=reward, audience=audience,
        assign_mode=assignMode, assignee_id=assigneeId or None, files=staged),
        staged=staged)


@router.post('/tasks/{task_id}/claim')
def claim(task_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return mutate(db, actor, 'claim_task', task_id,
                  lambda: svc.claim_task(db, actor, task_id))


class ReasonIn(BaseModel):
    reason: str


@router.post('/tasks/{task_id}/decline')
def decline(task_id: str, body: ReasonIn, actor: User = Depends(current_user),
            db: Session = Depends(get_db)):
    return mutate(db, actor, 'decline_assignment', task_id,
                  lambda: svc.decline_assignment(db, actor, task_id, body.reason))


@router.post('/tasks/{task_id}/return')
def return_claim(task_id: str, body: ReasonIn, actor: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    return mutate(db, actor, 'return_claim', task_id,
                  lambda: svc.return_claim(db, actor, task_id, body.reason))


class EditTaskIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    deadline: Optional[str] = None
    reward: Optional[float] = None


@router.patch('/tasks/{task_id}')
def edit_task(task_id: str, body: EditTaskIn, actor: User = Depends(current_user),
              db: Session = Depends(get_db)):
    sentinel = ...
    deadline = body.deadline if 'deadline' in body.model_fields_set else sentinel
    return mutate(db, actor, 'edit_task', task_id, lambda: svc.edit_task(
        db, actor, task_id, title=body.title, description=body.description,
        priority=body.priority, deadline=deadline, reward=body.reward))


class ReassignIn(BaseModel):
    assigneeId: Optional[str] = None


@router.post('/tasks/{task_id}/reassign')
def reassign(task_id: str, body: ReassignIn, actor: User = Depends(current_user),
             db: Session = Depends(get_db)):
    return mutate(db, actor, 'reassign', task_id,
                  lambda: svc.reassign(db, actor, task_id, body.assigneeId))


class ProgressIn(BaseModel):
    pct: float


@router.post('/tasks/{task_id}/progress')
def progress(task_id: str, body: ProgressIn, actor: User = Depends(current_user),
             db: Session = Depends(get_db)):
    return mutate(db, actor, 'report_progress', task_id,
                  lambda: svc.report_progress(db, actor, task_id, body.pct))


@router.post('/tasks/{task_id}/submit')
async def submit(task_id: str, note: str = Form(...),
                 pct: Optional[float] = Form(None),
                 files: list[UploadFile] = File(default=[]),
                 actor: User = Depends(current_user), db: Session = Depends(get_db)):
    staged = await stage_files(db, actor, files)
    return mutate(db, actor, 'submit_work', task_id, lambda: svc.submit_work(
        db, actor, task_id, note_text=note, files=staged, pct=pct), staged=staged)


@router.post('/tasks/{task_id}/resume')
def resume(task_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return mutate(db, actor, 'resume_work', task_id,
                  lambda: svc.resume_work(db, actor, task_id))


@router.post('/tasks/{task_id}/approve')
def approve(task_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return mutate(db, actor, 'approve_work', task_id,
                  lambda: svc.approve_work(db, actor, task_id))


@router.post('/tasks/{task_id}/reject')
def reject(task_id: str, body: ReasonIn, actor: User = Depends(current_user),
            db: Session = Depends(get_db)):
    return mutate(db, actor, 'reject_work', task_id,
                  lambda: svc.reject_work(db, actor, task_id, body.reason))


@router.post('/tasks/{task_id}/handoff')
async def handoff(
    task_id: str,
    acceptedPct: float = Form(...), reason: str = Form(...),
    nextKind: str = Form(...), nextId: Optional[str] = Form(None),
    audience: Optional[str] = Form(None), priority: Optional[str] = Form(None),
    deadline: Optional[str] = Form(None),
    remainingReward: Optional[float] = Form(None),
    overrideReason: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
    actor: User = Depends(current_user), db: Session = Depends(get_db),
    request: Request = None,
):
    form = await request.form()
    dl = deadline if 'deadline' in form else ...
    staged = await stage_files(db, actor, files)
    return mutate(db, actor, 'handoff', task_id, lambda: svc.handoff(
        db, actor, task_id, accepted_pct=acceptedPct, reason=reason,
        next_kind=nextKind, next_id=nextId, audience=audience, priority=priority,
        deadline=dl, remaining_reward=remainingReward,
        override_reason=overrideReason, files=staged), staged=staged)


@router.post('/tasks/{task_id}/reopen')
async def reopen(task_id: str, description: Optional[str] = Form(None),
                 audience: Optional[str] = Form(None),
                 assigneeId: Optional[str] = Form(None),
                 files: list[UploadFile] = File(default=[]),
                 actor: User = Depends(current_user), db: Session = Depends(get_db)):
    staged = await stage_files(db, actor, files)
    return mutate(db, actor, 'reopen_task', task_id, lambda: svc.reopen_task(
        db, actor, task_id, description=description, audience=audience,
        assignee_id=assigneeId, files=staged), staged=staged)


class CancelIn(BaseModel):
    reason: str
    acceptedPct: Optional[float] = None


@router.post('/tasks/{task_id}/cancel')
def cancel(task_id: str, body: CancelIn, actor: User = Depends(current_user),
           db: Session = Depends(get_db)):
    return mutate(db, actor, 'cancel_task', task_id, lambda: svc.cancel_task(
        db, actor, task_id, reason=body.reason, accepted_pct=body.acceptedPct))


@router.post('/tasks/{task_id}/reactivate')
async def reactivate(task_id: str, reason: str = Form(...),
                     description: Optional[str] = Form(None),
                     audience: Optional[str] = Form(None),
                     assigneeId: Optional[str] = Form(None),
                     files: list[UploadFile] = File(default=[]),
                     actor: User = Depends(current_user), db: Session = Depends(get_db)):
    staged = await stage_files(db, actor, files)
    return mutate(db, actor, 'reactivate_task', task_id, lambda: svc.reactivate_task(
        db, actor, task_id, reason=reason, description=description,
        audience=audience, assignee_id=assigneeId, files=staged),
        staged=staged)


# ── economy ─────────────────────────────────────────────────────────────────


class RedeemIn(BaseModel):
    rewardId: str


@router.post('/redemptions')
def redeem(body: RedeemIn, actor: User = Depends(current_user),
           db: Session = Depends(get_db)):
    return mutate(db, actor, 'redeem', body.rewardId,
                  lambda: svc.redeem(db, actor, body.rewardId))


@router.post('/redemptions/{redemption_id}/fulfill')
def fulfill(redemption_id: str, actor: User = Depends(current_user),
            db: Session = Depends(get_db)):
    return mutate(db, actor, 'fulfill_redemption', redemption_id,
                  lambda: svc.fulfill_redemption(db, actor, redemption_id))


@router.post('/redemptions/{redemption_id}/cancel')
def cancel_redemption(redemption_id: str, body: ReasonIn,
                      actor: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    return mutate(db, actor, 'cancel_redemption', redemption_id,
                  lambda: svc.cancel_redemption(db, actor, redemption_id, body.reason))


class AdjustIn(BaseModel):
    userId: str
    amount: float
    reason: str


@router.post('/admin/adjust')
def admin_adjust(body: AdjustIn, actor: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    return mutate(db, actor, 'admin_adjust', body.userId, lambda: svc.admin_adjust(
        db, actor, user_id=body.userId, amount=body.amount, reason=body.reason))


class RewardIn(BaseModel):
    id: Optional[str] = None
    name: str
    description: str = ''
    cost: float
    stock: Optional[int] = None
    active: bool = True
    category: str = 'Perks'
    eligibility: str = 'EMPLOYEES'  # N2-A: EMPLOYEES | MANAGERS | BOTH


@router.post('/rewards')
def save_reward(body: RewardIn, actor: User = Depends(current_user),
                db: Session = Depends(get_db)):
    return mutate(db, actor, 'save_reward', body.name, lambda: svc.save_reward(
        db, actor, reward_id=body.id, name=body.name, description=body.description,
        cost=body.cost, stock=body.stock, active=body.active, category=body.category,
        eligibility=body.eligibility))


# ── notices & preferences ───────────────────────────────────────────────────


@router.post('/notices/{notice_id}/read')
def mark_read(notice_id: str, actor: User = Depends(current_user),
              db: Session = Depends(get_db)):
    return mutate(db, actor, 'mark_read', notice_id,
                  lambda: svc.mark_read(db, actor, notice_id))


@router.post('/notices/read-all')
def mark_all_read(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return mutate(db, actor, 'mark_all_read', actor.id,
                  lambda: svc.mark_all_read(db, actor))


@router.post('/notices/{notice_id}/archive')
def archive_notice(notice_id: str, actor: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    return mutate(db, actor, 'archive_notice', notice_id,
                  lambda: svc.archive_notice(db, actor, notice_id))


@router.post('/notices/archive-read')
def archive_all_read(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return mutate(db, actor, 'archive_all_read', actor.id,
                  lambda: svc.archive_all_read(db, actor))


class MuteIn(BaseModel):
    level: str


@router.post('/notif-mute')
def toggle_mute(body: MuteIn, actor: User = Depends(current_user),
                db: Session = Depends(get_db)):
    return mutate(db, actor, 'toggle_notif_mute', body.level,
                  lambda: svc.toggle_notif_mute(db, actor, body.level))


# ── settings ────────────────────────────────────────────────────────────────


class SettingsIn(BaseModel):
    maxFileSizeMb: int
    maxSubmissionTotalMb: int


@router.put('/settings')
def update_settings(body: SettingsIn, actor: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    return mutate(db, actor, 'update_settings', 'company', lambda: svc.update_settings(
        db, actor, max_file_size_mb=body.maxFileSizeMb,
        max_submission_total_mb=body.maxSubmissionTotalMb))


# ── files ───────────────────────────────────────────────────────────────────


@router.get('/files/{attachment_id}')
def get_file(attachment_id: str, actor: User = Depends(current_user),
             db: Session = Depends(get_db)):
    a = db.get(Attachment, attachment_id)
    if a is None or a.company_id != actor.company_id:
        raise HTTPException(404, {'code': 'NOT_FOUND', 'message': 'File not found'})
    t = db.get(Task, a.task_id) if a.task_id else None
    if t is not None and not can_see_task(t.audience, t.assignee_id, t.owner_id,
                                          actor.role, actor.id):
        raise HTTPException(404, {'code': 'NOT_FOUND', 'message': 'File not found'})
    return FileResponse(storage.abspath(a.storage_path),
                        media_type=a.type or 'application/octet-stream',
                        filename=a.name)
