"""Upgrade the exact N3 baseline without rewriting existing work/history."""
import sqlalchemy as sa
from alembic import command
from sqlalchemy.orm import Session
from tests.test_n23_migration import mig_url, _alembic
from app.models import Company, User
from app.seed import run
from app.serializers import bootstrap


def test_n4_backfill_current_baseline_and_noop(mig_url):
    cfg=_alembic(mig_url)
    command.upgrade(cfg,'f32a0c9d174e')
    eng=sa.create_engine(mig_url)
    with eng.begin() as c:
        c.execute(sa.text("INSERT INTO companies (id,name,seq) VALUES ('n4-old','Original',100)"))
        for i,role in enumerate(['ADMIN','MANAGER','EMPLOYEE']):
            c.execute(sa.text("INSERT INTO users (id,company_id,name,email,role,position,password_hash,notif_muted) VALUES (:id,'n4-old','Original',:email,:role,'Work','hash','[]')"),dict(id=f'n4-{i}',email=f'{i}@old',role=role))
        before={t:c.execute(sa.text(f'SELECT * FROM {t}')).mappings().all() for t in ['users','companies','tasks','ledger','activity','notifications']}
    command.upgrade(cfg,'head')
    with eng.connect() as c:
        for table,rows in before.items():
            after=[dict(r) for r in c.execute(sa.text(f'SELECT * FROM {table}')).mappings()]
            if table=='users':
                for row in after: assert row.pop('max_active_tasks')==2
            assert after==[dict(r) for r in rows]
        assert c.scalar(sa.text('SELECT version_num FROM alembic_version'))=='a41b7c9d2601'
    command.upgrade(cfg,'head')
    with eng.connect() as c: assert c.scalar(sa.text('SELECT count(*) FROM users WHERE max_active_tasks=2'))==3
    with eng.begin() as c:
        with __import__('pytest').raises(sa.exc.IntegrityError): c.execute(sa.text('UPDATE users SET max_active_tasks=0'))
    eng.dispose()


def test_n4_clean_seed_bootstrap(mig_url):
    command.upgrade(_alembic(mig_url),'head')
    eng=sa.create_engine(mig_url)
    with Session(eng) as db:
        run(db);db.commit()
        company=db.scalar(sa.select(Company))
        s=bootstrap(db,company)
        assert all(u['maxActiveTasks']==(None if u['role']=='ADMIN' else 2) for u in s['users'])
        assert all(u.max_active_tasks==2 for u in db.scalars(sa.select(User)))
    eng.dispose()
