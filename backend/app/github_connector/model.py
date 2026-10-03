"""Company-bound repository configuration, explicit identities and immutable delivery facts."""
from sqlalchemy import Boolean,CheckConstraint,Float,ForeignKeyConstraint,String,UniqueConstraint,event,DDL
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from ..models import Base,new_id,now_ms


class GithubSource(Base):
    __tablename__='github_sources'
    __table_args__=(ForeignKeyConstraint(['company_id'],['companies.id']),
        UniqueConstraint('company_id','id',name='uq_github_source_tenant'),
        CheckConstraint("repository_id ~ '^[1-9][0-9]{0,19}$'",name='ck_github_repository'),
        CheckConstraint("source_key ~ '^[A-Za-z0-9_-]{32}$'",name='ck_github_source_key'),
        CheckConstraint("secret_nonce ~ '^[0-9a-f]{64}$'",name='ck_github_nonce'))
    id:Mapped[str]=mapped_column(String(40),primary_key=True,default=lambda:new_id('gh'))
    company_id:Mapped[str]=mapped_column(String(40),index=True)
    name:Mapped[str]=mapped_column(String(120))
    repository_id:Mapped[str]=mapped_column(String(20))
    source_key:Mapped[str]=mapped_column(String(32),unique=True)
    secret_nonce:Mapped[str]=mapped_column(String(64))
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    created_at:Mapped[float]=mapped_column(Float,default=now_ms)
    updated_at:Mapped[float]=mapped_column(Float,default=now_ms)


class GithubIdentity(Base):
    __tablename__='github_identities'
    __table_args__=(
        ForeignKeyConstraint(['company_id','source_id'],['github_sources.company_id','github_sources.id']),
        ForeignKeyConstraint(['company_id','user_id'],['users.company_id','users.id']),
        CheckConstraint("external_user_id ~ '^[1-9][0-9]{0,19}$'",name='ck_github_identity'))
    company_id:Mapped[str]=mapped_column(String(40),primary_key=True)
    source_id:Mapped[str]=mapped_column(String(40),primary_key=True)
    external_user_id:Mapped[str]=mapped_column(String(20),primary_key=True)
    user_id:Mapped[str]=mapped_column(String(40))
    created_at:Mapped[float]=mapped_column(Float,default=now_ms)


class GithubDelivery(Base):
    __tablename__='github_deliveries'
    __table_args__=(
        ForeignKeyConstraint(['company_id','source_id'],['github_sources.company_id','github_sources.id']),
        UniqueConstraint('company_id','source_id','delivery_id',name='uq_github_delivery'),
        UniqueConstraint('company_id','source_id','body_sha256',name='uq_github_body'),
        CheckConstraint("body_sha256 ~ '^[0-9a-f]{64}$'",name='ck_github_body_hash'))
    id:Mapped[str]=mapped_column(String(40),primary_key=True,default=lambda:new_id('ghraw'))
    company_id:Mapped[str]=mapped_column(String(40),index=True)
    source_id:Mapped[str]=mapped_column(String(40))
    delivery_id:Mapped[str]=mapped_column(String(36))
    body_sha256:Mapped[str]=mapped_column(String(64))
    event_name:Mapped[str]=mapped_column(String(64))
    payload:Mapped[dict]=mapped_column(JSONB)
    received_at:Mapped[float]=mapped_column(Float,default=now_ms)


class GithubProjectAttribution(Base):
    """Admin-authored resource intervals; no provider text inference."""
    __tablename__='github_project_attributions'
    id:Mapped[str]=mapped_column(String(40),primary_key=True,default=lambda:new_id('ghscope'))
    company_id:Mapped[str]=mapped_column(String(40))
    source_id:Mapped[str]=mapped_column(String(40))
    resource_kind:Mapped[str]=mapped_column(String(20))
    resource_id:Mapped[str]=mapped_column(String(20))
    project_id:Mapped[str]=mapped_column(String(40))
    joined_at:Mapped[float]=mapped_column(Float,default=now_ms)
    left_at:Mapped[float|None]=mapped_column(Float,nullable=True)
    __table_args__=(
        ForeignKeyConstraint(['company_id','source_id'],['github_sources.company_id','github_sources.id']),
        ForeignKeyConstraint(['company_id','project_id'],['projects.company_id','projects.id']),
        CheckConstraint("resource_kind IN ('issue','pull_request')",name='ck_github_attribution_kind'),
        CheckConstraint("resource_id ~ '^[1-9][0-9]{0,19}$'",name='ck_github_attribution_resource'),
        CheckConstraint('left_at IS NULL OR left_at >= joined_at',name='ck_github_attribution_time'))


INSTALL_SQL="""
CREATE FUNCTION reject_github_delivery_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'GitHub delivery history is immutable' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER github_deliveries_immutable BEFORE UPDATE OR DELETE ON github_deliveries
FOR EACH ROW EXECUTE FUNCTION reject_github_delivery_mutation();
"""
UNINSTALL_SQL="""
DROP TRIGGER IF EXISTS github_deliveries_immutable ON github_deliveries;
DROP FUNCTION IF EXISTS reject_github_delivery_mutation();
"""
event.listen(GithubDelivery.__table__,'after_create',DDL(INSTALL_SQL).execute_if(dialect='postgresql'))
event.listen(GithubDelivery.__table__,'before_drop',DDL(UNINSTALL_SQL).execute_if(dialect='postgresql'))
