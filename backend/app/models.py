"""SQLAlchemy 2 persistent models (M1).

Scope = frozen domain only. Every company-scoped table carries company_id
(tenant boundary). History tables (Submission, Contribution, TaskCycle,
LedgerTransaction) are append-only by convention enforced in services —
no update/delete paths exist.

AI-readiness: stable string ids, explicit lifecycle timestamps, structured
columns for every business fact (priority, pcts, payouts, outcomes), and
actor/reason/cycle traceability on decisions.
"""
from __future__ import annotations

import time
import uuid

from sqlalchemy import (Boolean, Float, ForeignKey, Integer, String, Text, Date,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id(prefix: str) -> str:
    return f'{prefix}-{uuid.uuid4().hex[:12]}'


def now_ms() -> float:
    return time.time() * 1000


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = 'companies'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('co'))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, default=100)  # legacy id counter, unused for uuids


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('u'))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20))          # ADMIN | MANAGER | EMPLOYEE
    position: Mapped[str] = mapped_column(String(120), default='')
    password_hash: Mapped[str] = mapped_column(String(200))
    notif_muted: Mapped[list] = mapped_column(JSONB, default=list)  # muted NotifLevels


class CompanySettings(Base):
    __tablename__ = 'company_settings'
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), primary_key=True)
    max_file_size_mb: Mapped[int] = mapped_column(Integer, default=10)
    max_submission_total_mb: Mapped[int] = mapped_column(Integer, default=25)


class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('t'))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default='')
    priority: Mapped[str] = mapped_column(String(12))
    deadline: Mapped[Date | None] = mapped_column(Date, nullable=True)  # canonical date-only
    reward: Mapped[float] = mapped_column(Float)
    audience: Mapped[str] = mapped_column(String(12))       # EMPLOYEES | MANAGEMENT | PRIVATE
    assign_mode: Mapped[str] = mapped_column(String(20))
    assignee_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(14), index=True)
    owner_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cycle: Mapped[int] = mapped_column(Integer, default=1)
    verified: Mapped[float] = mapped_column(Float, default=0)
    reported: Mapped[float] = mapped_column(Float, default=0)
    paid: Mapped[float] = mapped_column(Float, default=0)
    submission_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ms)
    created_by: Mapped[str] = mapped_column(String(40))

    brief_files: Mapped[list['Attachment']] = relationship(
        primaryjoin="and_(Task.id==Attachment.task_id, Attachment.kind=='brief')")
    submissions: Mapped[list['Submission']] = relationship(back_populates='task')
    contributions: Mapped[list['Contribution']] = relationship(back_populates='task')
    cycles: Mapped[list['TaskCycle']] = relationship(back_populates='task')


class TaskCycle(Base):
    __tablename__ = 'task_cycles'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('cy'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'), index=True)
    cycle: Mapped[int] = mapped_column(Integer)
    opened_at: Mapped[float] = mapped_column(Float, default=now_ms)
    closed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(14), nullable=True)
    paid: Mapped[float] = mapped_column(Float, default=0)
    verified: Mapped[float] = mapped_column(Float, default=0)
    task: Mapped[Task] = relationship(back_populates='cycles')


class Submission(Base):
    """Immutable per-owner submission history. Outcome closes in place once;
    note/attachments/reported_pct never change after insert."""
    __tablename__ = 'submissions'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('s'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'), index=True)
    cycle: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text, default='')
    reported_pct: Mapped[float] = mapped_column(Float, default=0)
    at: Mapped[float] = mapped_column(Float, default=now_ms)          # submitted_at
    outcome: Mapped[str] = mapped_column(String(12), default='PENDING')
    reviewer_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    task: Mapped[Task] = relationship(back_populates='submissions')
    attachments: Mapped[list['Attachment']] = relationship(back_populates='submission')


class Attachment(Base):
    """Metadata row; bytes live in the storage backend (storage.py).
    kind: 'brief' (task reference files) or 'submission' (evidence)."""
    __tablename__ = 'attachments'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('f'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey('tasks.id'), nullable=True, index=True)
    submission_id: Mapped[str | None] = mapped_column(ForeignKey('submissions.id'), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(12))           # brief | submission
    name: Mapped[str] = mapped_column(String(300))
    size: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(120), default='')
    storage_path: Mapped[str] = mapped_column(String(500))  # tenant-scoped relative path
    created_at: Mapped[float] = mapped_column(Float, default=now_ms)
    submission: Mapped[Submission | None] = relationship(back_populates='attachments')


class Contribution(Base):
    """Immutable contributor history — one row per verified decision."""
    __tablename__ = 'contributions'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('c'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'), index=True)
    cycle: Mapped[int] = mapped_column(Integer)
    employee_id: Mapped[str] = mapped_column(String(40))
    reported_pct: Mapped[float] = mapped_column(Float)
    accepted_pct: Mapped[float] = mapped_column(Float)
    payout: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(12))       # HANDOFF | APPROVED | CANCELLED
    reason: Mapped[str] = mapped_column(Text, default='')
    at: Mapped[float] = mapped_column(Float, default=now_ms)
    task: Mapped[Task] = relationship(back_populates='contributions')


class LedgerTransaction(Base):
    """Append-only. No update/delete anywhere in the codebase."""
    __tablename__ = 'ledger'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('l'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    type: Mapped[str] = mapped_column(String(24))
    amount: Mapped[float] = mapped_column(Float)
    ref: Mapped[str] = mapped_column(String(400))
    task_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cycle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[float] = mapped_column(Float, default=now_ms)


class Reward(Base):
    __tablename__ = 'rewards'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('rw'))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    cost: Mapped[float] = mapped_column(Float)
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str] = mapped_column(String(80), default='Perks')
    # N2-A: EMPLOYEES | MANAGERS | BOTH — never ADMIN. Existing rows default
    # to EMPLOYEES (the historical effective behavior).
    eligibility: Mapped[str] = mapped_column(String(12), default='EMPLOYEES',
                                             server_default='EMPLOYEES')
    # N2.1-A2 / N2.1-R2: creator identity for history/audit. Management
    # authority follows the canonical governance matrix (audience-based), NOT
    # this field. Existing rows backfilled to the company admin by migration.
    created_by: Mapped[str] = mapped_column(String(40), default='',
                                            server_default='')


class Redemption(Base):
    __tablename__ = 'redemptions'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('r'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    reward_id: Mapped[str] = mapped_column(String(40))
    cost: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), default='PENDING')  # PENDING|FULFILLED|CANCELLED
    at: Mapped[float] = mapped_column(Float, default=now_ms)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('n'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    level: Mapped[str] = mapped_column(String(18))
    category: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    task_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pri: Mapped[str | None] = mapped_column(String(12), nullable=True)
    redemption_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    at: Mapped[float] = mapped_column(Float, default=now_ms)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Activity(Base):
    """Canonical business history (product audit). Separate from technical logs."""
    __tablename__ = 'activity'
    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id('a'))
    company_id: Mapped[str] = mapped_column(String(40), index=True)
    actor_id: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(60))
    object: Mapped[str] = mapped_column(String(400))
    task_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    econ: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cycle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[float] = mapped_column(Float, default=now_ms)
