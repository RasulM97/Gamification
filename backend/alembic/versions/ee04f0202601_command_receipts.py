"""F02: atomic command retry receipts; no economic data rewrite."""
from alembic import op
import sqlalchemy as sa

revision = 'ee04f0202601'
down_revision = 'ee03b2c4d503'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'command_receipts',
        sa.Column('company_id', sa.String(40), primary_key=True),
        sa.Column('actor_id', sa.String(40), primary_key=True),
        sa.Column('key', sa.String(80), primary_key=True),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(['company_id', 'actor_id'], ['users.company_id', 'users.id'],
                                name='fk_command_receipt_actor'))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM command_receipts')):
        raise RuntimeError('Cannot discard committed retry identities; retain command_receipts')
    op.drop_table('command_receipts')
