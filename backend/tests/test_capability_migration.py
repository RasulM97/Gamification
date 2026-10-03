"""Real E11 upgrade, safe defaults, empty rollback and audit preservation."""
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from app.models import Company,User
from app.capabilities.service import snapshot,update
from tests.test_n23_migration import mig_url,_alembic


def test_capability_migration(mig_url):
    cfg=_alembic(mig_url);engine=sa.create_engine(mig_url)
    try:
        command.upgrade(cfg,'eb01c9e2601')
        with Session(engine) as db:
            db.add(Company(id='existing',name='Existing company'));db.flush()
            db.add(User(id='existing-admin',company_id='existing',name='Admin',email='existing@capability.invalid',role='ADMIN',password_hash='disabled'));db.commit()
        command.upgrade(cfg,'head');command.upgrade(cfg,'head')
        with Session(engine) as db:
            assert all(snapshot(db,'existing').values())
            assert db.scalar(sa.text('SELECT count(*) FROM company_capabilities'))==0
        command.downgrade(cfg,'eb01c9e2601');command.upgrade(cfg,'head')
        with Session(engine) as db:
            update(db,db.get(User,'existing-admin'),'THANKS',{'enabled':False});db.commit()
            assert not snapshot(db,'existing')['THANKS']
            for sql in ["UPDATE capability_changes SET new_enabled=true","DELETE FROM capability_changes"]:
                with pytest.raises(sa.exc.IntegrityError),db.begin_nested():db.execute(sa.text(sql))
        with pytest.raises(RuntimeError,match='Cannot discard capability'):command.downgrade(cfg,'eb01c9e2601')
        with engine.connect() as connection:
            assert connection.scalar(sa.text('SELECT version_num FROM alembic_version'))=='ed01c9e2601'
            assert connection.scalar(sa.text('SELECT count(*) FROM capability_changes'))==1
    finally:engine.dispose()
