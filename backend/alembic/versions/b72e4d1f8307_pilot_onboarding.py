"""Minimal company onboarding state and one-time account activation."""
from alembic import op
import sqlalchemy as sa

revision = 'b72e4d1f8307'
down_revision = 'a41b7c9d2601'
branch_labels = None
depends_on = None


def upgrade():
    # Existing companies remain operational; new companies start setup explicitly.
    op.add_column('companies', sa.Column('onboarding_status', sa.String(20), nullable=False, server_default='COMPLETED'))
    op.alter_column('companies', 'onboarding_status', server_default='NOT_STARTED')
    op.add_column('companies', sa.Column('onboarding_completed_at', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('activation_hash', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('activation_expires_at', sa.Float(), nullable=True))
    op.create_unique_constraint('uq_users_activation_hash', 'users', ['activation_hash'])


def downgrade():
    op.drop_constraint('uq_users_activation_hash', 'users', type_='unique')
    op.drop_column('users', 'activation_expires_at')
    op.drop_column('users', 'activation_hash')
    op.drop_column('companies', 'onboarding_completed_at')
    op.drop_column('companies', 'onboarding_status')
