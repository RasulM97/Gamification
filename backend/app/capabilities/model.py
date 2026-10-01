"""Company state and immutable, narrowly scoped capability change history."""
from sqlalchemy import Boolean, CheckConstraint, DDL, Float, ForeignKey, ForeignKeyConstraint, Index, String, event
from sqlalchemy.orm import Mapped, mapped_column
from ..models import Base, new_id, now_ms
from .contracts import OPTIONAL

ALLOWED = "capability IN (" + ','.join("'"+key+"'" for key in OPTIONAL) + ")"

class CompanyCapability(Base):
    __tablename__ = 'company_capabilities'
    __table_args__ = (CheckConstraint(ALLOWED, name='ck_capability_name'),
        ForeignKeyConstraint(['company_id','updated_by'],['users.company_id','users.id'],name='fk_capability_actor'))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'),primary_key=True)
    capability: Mapped[str] = mapped_column(String(32),primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean,nullable=False)
    updated_at: Mapped[float] = mapped_column(Float,default=now_ms)
    updated_by: Mapped[str] = mapped_column(String(40))

class CapabilityChange(Base):
    __tablename__ = 'capability_changes'
    __table_args__ = (CheckConstraint(ALLOWED,name='ck_capability_change_name'),
        CheckConstraint('old_enabled <> new_enabled',name='ck_capability_transition'),
        ForeignKeyConstraint(['company_id','actor_id'],['users.company_id','users.id'],name='fk_capability_change_actor'),
        Index('ix_capability_changes_company','company_id','created_at','id'))
    id: Mapped[str] = mapped_column(String(40),primary_key=True,default=lambda:new_id('cap'))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'))
    capability: Mapped[str] = mapped_column(String(32))
    old_enabled: Mapped[bool] = mapped_column(Boolean)
    new_enabled: Mapped[bool] = mapped_column(Boolean)
    actor_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[float] = mapped_column(Float,default=now_ms)

IMMUTABLE_SQL = """
CREATE FUNCTION reject_capability_change_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Capability change history is immutable' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER capability_change_immutable BEFORE UPDATE OR DELETE ON capability_changes
FOR EACH ROW EXECUTE FUNCTION reject_capability_change_mutation();
"""
event.listen(CapabilityChange.__table__,'after_create',DDL(IMMUTABLE_SQL).execute_if(dialect='postgresql'))
event.listen(CapabilityChange.__table__,'after_drop',DDL('DROP FUNCTION IF EXISTS reject_capability_change_mutation()').execute_if(dialect='postgresql'))
