"""Add server-authoritative auth sessions (UAT-blocker security fix).

Revision ID: ee03b2c4d503
Revises: ee02a1b3c402

A JWT becomes insufficient authority on its own: it must reference an
auth_sessions row that exists, matches the user+company, and is neither
revoked nor expired. Sessions are tenant-scoped (company_id) so tenant
disposal (UAT reset / dev reseed) takes them with the tenant.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ee03b2c4d503'
down_revision = 'ee02a1b3c402'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'auth_sessions',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(40), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('company_id', sa.String(40), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False),
        sa.Column('revoked_at', sa.Float(), nullable=True),
    )
    op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])
    op.create_index('ix_auth_sessions_company_id', 'auth_sessions', ['company_id'])


def downgrade():
    op.drop_index('ix_auth_sessions_company_id', table_name='auth_sessions')
    op.drop_index('ix_auth_sessions_user_id', table_name='auth_sessions')
    op.drop_table('auth_sessions')
