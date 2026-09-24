"""Tenant-bound webhook registrations; no canonical or business row changes.

Revision ID: e30a1c9e2601
Revises: e11a0c7e2601
"""
from alembic import op
import sqlalchemy as sa

revision = 'e30a1c9e2601'
down_revision = 'e11a0c7e2601'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('webhook_sources',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('source_key', sa.String(32), nullable=False, unique=True),
        sa.Column('secret_nonce', sa.String(64), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=False),
        sa.CheckConstraint("source_key ~ '^[A-Za-z0-9_-]{32}$'", name='ck_webhook_source_key'),
        sa.CheckConstraint("secret_nonce ~ '^[0-9a-f]{64}$'", name='ck_webhook_secret_nonce'))
    op.create_index('ix_webhook_sources_company_id', 'webhook_sources', ['company_id'])


def downgrade():
    op.drop_table('webhook_sources')
