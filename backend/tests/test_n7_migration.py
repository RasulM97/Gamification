import subprocess
import sys
import json
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic import command
from tests.test_n23_migration import mig_url, _alembic
from app.models import Company
from app.serializers import bootstrap


def test_fresh_migrations_cli_provision_no_seed(mig_url):
    command.upgrade(_alembic(mig_url), 'head')
    engine = sa.create_engine(mig_url)
    with engine.connect() as c:
        assert c.scalar(sa.text('SELECT count(*) FROM companies')) == 0
    args = [sys.executable, '-m', 'app.provision_company', '--company', 'Fresh pilot', '--admin-name', 'Fresh Admin', '--admin-email', 'fresh@pilot.test', '--password-stdin']
    for created in (True, False):
        result = subprocess.run(args, input='Unique-fresh-pilot-secret-31\n', text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        output = json.loads(result.stdout)
        assert output['created'] is created and 'secret' not in result.stdout
    with Session(engine) as db:
        state = bootstrap(db, db.scalar(sa.select(Company)))
        assert state['onboarding']['status'] == 'NOT_STARTED'
        assert len(state['users']) == 1
        assert all(state[k] == [] for k in ('tasks', 'ledger', 'notices', 'activity', 'rewards', 'redemptions', 'rewardCategories'))
    command.upgrade(_alembic(mig_url), 'head')
    engine.dispose()


def test_existing_company_not_restarted_by_migration(mig_url):
    cfg = _alembic(mig_url); command.upgrade(cfg, 'a41b7c9d2601')
    engine = sa.create_engine(mig_url)
    with engine.begin() as c:
        c.execute(sa.text("INSERT INTO companies(id,name,seq) VALUES ('old','Existing',123)"))
    command.upgrade(cfg, 'head')
    with engine.begin() as c:
        assert c.execute(sa.text('SELECT id,name,seq,onboarding_status,onboarding_completed_at FROM companies')).one() == ('old', 'Existing', 123, 'COMPLETED', None)
        c.execute(sa.text("INSERT INTO companies(id,name,seq) VALUES ('new','New',0)"))
        assert c.scalar(sa.text("SELECT onboarding_status FROM companies WHERE id='new'")) == 'NOT_STARTED'
    engine.dispose()
