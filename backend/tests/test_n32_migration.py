"""Current N3.1 schema upgrades additively; immutable old prose remains byte-identical."""
import sqlalchemy as sa
from alembic import command
from tests.test_n23_migration import mig_url, _alembic


def test_n32_current_schema_upgrade_and_second_upgrade_noop(mig_url):
    cfg = _alembic(mig_url)
    command.upgrade(cfg, 'e7f2a4c61d83')
    eng = sa.create_engine(mig_url)
    with eng.begin() as c:
        c.execute(sa.text("INSERT INTO activity (id,company_id,actor_id,action,object,reason,at) VALUES ('legacy','old-co','old-user','approved work','Original title','Keep دلیل',1)"))
        c.execute(sa.text("INSERT INTO ledger (id,company_id,user_id,type,amount,ref,at) VALUES ('legacy','old-co','old-user','TASK_REWARD',12,'Original credit',1)"))
        c.execute(sa.text("INSERT INTO notifications (id,company_id,user_id,level,category,text,at,read,archived) VALUES ('legacy','old-co','old-user','IMPORTANT','Tasks','Original notice',1,false,false)"))
    command.upgrade(cfg, 'head')
    before = {}
    with eng.connect() as c:
        for table in ['activity','notifications','ledger']:
            before[table] = dict(c.execute(sa.text(f'SELECT * FROM {table}')).mappings().one())
            assert before[table]['event_type'] is None and before[table]['params'] is None
        assert before['activity']['reason'] == 'Keep دلیل'
        assert before['ledger']['amount'] == 12
        assert before['notifications']['text'] == 'Original notice'
    command.upgrade(cfg, 'head')
    with eng.connect() as c:
        for table in before:
            assert dict(c.execute(sa.text(f'SELECT * FROM {table}')).mappings().one()) == before[table]
    eng.dispose()
