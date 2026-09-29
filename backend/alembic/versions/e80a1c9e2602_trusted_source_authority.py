"""Generic trusted source receipts; preserve E7 history and economic identity."""
from alembic import op
import sqlalchemy as sa
from app.source_authority.schema import INSTALL_SQL, UNINSTALL_SQL

revision='e80a1c9e2602'
down_revision='e70a1c9e2601'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('trusted_producers',
        sa.Column('company_id',sa.String(40),primary_key=True),
        sa.Column('source_kind',sa.String(64),primary_key=True),
        sa.Column('source_id',sa.String(200),primary_key=True),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.ForeignKeyConstraint(['company_id'],['companies.id']),
        sa.CheckConstraint("source_kind ~ '^TRUSTED_[A-Z][A-Z0-9_]*$'",name='ck_trusted_producer_namespace'))
    op.create_table('source_receipts',
        sa.Column('company_id',sa.String(40),primary_key=True),
        sa.Column('event_id',sa.String(40),primary_key=True),
        sa.Column('source_kind',sa.String(64),nullable=False),
        sa.Column('source_id',sa.String(200),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.ForeignKeyConstraint(['company_id','event_id'],['canonical_events.company_id','canonical_events.id']),
        sa.ForeignKeyConstraint(['company_id','source_kind','source_id'],
                               ['trusted_producers.company_id','trusted_producers.source_kind','trusted_producers.source_id']),
        sa.UniqueConstraint('event_id',name='uq_source_receipt_event'))
    op.execute(INSTALL_SQL)


def downgrade():
    if op.get_bind().scalar(sa.text('''SELECT EXISTS (SELECT 1 FROM economic_effects x
        JOIN rule_candidates c ON c.id=x.candidate_id
        JOIN source_receipts r ON r.company_id=x.company_id AND r.event_id=c.canonical_event_id)''')):
        raise RuntimeError('Cannot discard issued trusted source provenance')
    op.execute(UNINSTALL_SQL)
    op.drop_table('source_receipts')
    op.drop_table('trusted_producers')
