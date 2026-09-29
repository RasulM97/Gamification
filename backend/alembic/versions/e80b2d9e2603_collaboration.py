"""Explicit Thanks, Recognition and Help facts; no economic columns."""
from alembic import op
import sqlalchemy as sa

revision='e80b2d9e2603'
down_revision='e80a1c9e2602'
branch_labels=None
depends_on=None


def upgrade():
    for table,short in [('peer_thanks','thanks'),('manager_recognitions','recognition')]:
        op.create_table(table,
            sa.Column('id',sa.String(40),primary_key=True),
            sa.Column('company_id',sa.String(40),nullable=False),
            sa.Column('sender_user_id',sa.String(40),nullable=False),
            sa.Column('recipient_user_id',sa.String(40),nullable=False),
            sa.Column('message',sa.String(1000),nullable=False),
            sa.Column('submission_id',sa.String(100),nullable=False),
            sa.Column('created_at',sa.Float(),nullable=False),
            sa.ForeignKeyConstraint(['company_id','sender_user_id'],['users.company_id','users.id']),
            sa.ForeignKeyConstraint(['company_id','recipient_user_id'],['users.company_id','users.id']),
            sa.UniqueConstraint('company_id','sender_user_id','submission_id',name='uq_'+short+'_submission'),
            sa.CheckConstraint('sender_user_id <> recipient_user_id',name='ck_'+short+'_self'))
        op.create_index('ix_'+table+'_company_id',table,['company_id'])
    op.create_table('help_requests',
        sa.Column('id',sa.String(40),primary_key=True),
        sa.Column('company_id',sa.String(40),nullable=False),
        sa.Column('requester_user_id',sa.String(40),nullable=False),
        sa.Column('title',sa.String(200),nullable=False),
        sa.Column('description',sa.String(1000),nullable=False),
        sa.Column('submission_id',sa.String(100),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.Column('accepted_by_user_id',sa.String(40),nullable=True),
        sa.Column('accepted_at',sa.Float(),nullable=True),
        sa.Column('finished_at',sa.Float(),nullable=True),
        sa.Column('confirmed_at',sa.Float(),nullable=True),
        sa.ForeignKeyConstraint(['company_id','requester_user_id'],['users.company_id','users.id']),
        sa.ForeignKeyConstraint(['company_id','accepted_by_user_id'],['users.company_id','users.id']),
        sa.UniqueConstraint('company_id','requester_user_id','submission_id',name='uq_help_submission'),
        sa.CheckConstraint('requester_user_id <> accepted_by_user_id',name='ck_help_self'),
        sa.CheckConstraint("(status='OPEN' AND accepted_by_user_id IS NULL AND accepted_at IS NULL AND finished_at IS NULL AND confirmed_at IS NULL) OR "
                        "(status='ACCEPTED' AND accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL AND finished_at IS NULL AND confirmed_at IS NULL) OR "
                        "(status='FINISHED' AND accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL AND finished_at IS NOT NULL AND confirmed_at IS NULL) OR "
                        "(status='CONFIRMED' AND accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL AND finished_at IS NOT NULL AND confirmed_at IS NOT NULL)",name='ck_help_state'))
    op.create_index('ix_help_requests_company_id','help_requests',['company_id'])


def downgrade():
    # Removing populated product facts would orphan their immutable event/history references.
    for table in ('help_requests','manager_recognitions','peer_thanks'):
        if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM '+table+')')):
            raise RuntimeError('Cannot discard collaboration history')
    for table in ('help_requests','manager_recognitions','peer_thanks'):
        op.drop_table(table)
