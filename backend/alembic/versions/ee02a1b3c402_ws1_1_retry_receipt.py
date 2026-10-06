"""WS1.1: channel_deliveries.receipt_text — preserved retry confirmation (F-5)."""
from alembic import op
import sqlalchemy as sa

revision = 'ee02a1b3c402'
down_revision = 'ee01c9e2601'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('channel_deliveries',
                  sa.Column('receipt_text', sa.String(200), nullable=True))


def downgrade():
    op.drop_column('channel_deliveries', 'receipt_text')
