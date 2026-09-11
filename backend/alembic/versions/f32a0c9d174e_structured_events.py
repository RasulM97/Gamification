"""Add language-neutral events without rewriting legacy history.

Revision ID: f32a0c9d174e
Revises: e7f2a4c61d83
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'f32a0c9d174e'
down_revision = 'e7f2a4c61d83'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('activity', 'notifications', 'ledger'):
        op.add_column(table, sa.Column('event_type', sa.String(64), nullable=True))
        op.add_column(table, sa.Column('params', postgresql.JSONB(), nullable=True))


def downgrade():
    for table in ('ledger', 'notifications', 'activity'):
        op.drop_column(table, 'params')
        op.drop_column(table, 'event_type')
