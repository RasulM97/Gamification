"""Per-user capacity; existing users retain the prior default of two."""
from alembic import op
import sqlalchemy as sa

revision = 'a41b7c9d2601'
down_revision = 'f32a0c9d174e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('max_active_tasks', sa.Integer(),
                                    nullable=False, server_default='2'))
    op.create_check_constraint('ck_users_capacity', 'users',
                               'max_active_tasks BETWEEN 1 AND 100')


def downgrade():
    op.drop_constraint('ck_users_capacity', 'users', type_='check')
    op.drop_column('users', 'max_active_tasks')
