from ..organization.columns import ScopeColumns, constraints as scope_constraints
"""Explicit collaboration facts with tenant-bound participants and retry identity."""
from sqlalchemy import CheckConstraint, Float, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms


class AppreciationColumns(ScopeColumns):
    id: Mapped[str] = mapped_column(String(40),primary_key=True,default=lambda:new_id('app'))
    company_id: Mapped[str] = mapped_column(String(40),index=True)
    sender_user_id: Mapped[str] = mapped_column(String(40))
    recipient_user_id: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(1000))
    submission_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[float] = mapped_column(Float,default=now_ms)


def appreciation_constraints(name):
    return scope_constraints(name)+(ForeignKeyConstraint(['company_id','sender_user_id'],['users.company_id','users.id']),
            ForeignKeyConstraint(['company_id','recipient_user_id'],['users.company_id','users.id']),
            UniqueConstraint('company_id','sender_user_id','submission_id',name='uq_'+name+'_submission'),
            CheckConstraint('sender_user_id <> recipient_user_id',name='ck_'+name+'_self'))


class PeerThanks(AppreciationColumns,Base):
    __tablename__='peer_thanks'
    __table_args__=appreciation_constraints('thanks')


class ManagerRecognition(AppreciationColumns,Base):
    __tablename__='manager_recognitions'
    __table_args__=appreciation_constraints('recognition')


class HelpRequest(ScopeColumns, Base):
    __tablename__='help_requests'
    __table_args__=scope_constraints('help')+(
        ForeignKeyConstraint(['company_id','requester_user_id'],['users.company_id','users.id']),
        ForeignKeyConstraint(['company_id','accepted_by_user_id'],['users.company_id','users.id']),
        UniqueConstraint('company_id','requester_user_id','submission_id',name='uq_help_submission'),
        CheckConstraint('requester_user_id <> accepted_by_user_id',name='ck_help_self'),
        CheckConstraint("(status='OPEN' AND accepted_by_user_id IS NULL AND accepted_at IS NULL AND finished_at IS NULL AND confirmed_at IS NULL) OR "
                        "(status='ACCEPTED' AND accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL AND finished_at IS NULL AND confirmed_at IS NULL) OR "
                        "(status='FINISHED' AND accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL AND finished_at IS NOT NULL AND confirmed_at IS NULL) OR "
                        "(status='CONFIRMED' AND accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL AND finished_at IS NOT NULL AND confirmed_at IS NOT NULL)",name='ck_help_state'),
    )
    id: Mapped[str] = mapped_column(String(40),primary_key=True,default=lambda:new_id('help'))
    company_id: Mapped[str] = mapped_column(String(40),index=True)
    requester_user_id: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000))
    submission_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16),default='OPEN')
    created_at: Mapped[float] = mapped_column(Float,default=now_ms)
    accepted_by_user_id: Mapped[str|None] = mapped_column(String(40),nullable=True)
    accepted_at: Mapped[float|None] = mapped_column(Float,nullable=True)
    finished_at: Mapped[float|None] = mapped_column(Float,nullable=True)
    confirmed_at: Mapped[float|None] = mapped_column(Float,nullable=True)
