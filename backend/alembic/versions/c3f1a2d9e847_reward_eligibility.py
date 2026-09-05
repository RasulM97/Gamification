"""N2 — reward eligibility

Adds rewards.eligibility (EMPLOYEES | MANAGERS | BOTH). Existing rows are
backfilled with EMPLOYEES — the historical effective behavior before N2 —
so the migration is behavior-preserving. The column is NOT NULL with a
server default so new inserts are always well-defined.

Revision ID: c3f1a2d9e847
Revises: bce2aa82978d
Create Date: 2026-09-05

NOTE (sandbox): prepared but NOT executed here — the compile/migration gate
is founder-side against the real PostgreSQL instance (see
docs/EXTERNAL_POSTGRESQL_RUN.md).
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3f1a2d9e847'
down_revision = 'bce2aa82978d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('rewards', sa.Column(
        'eligibility', sa.String(length=12), nullable=False,
        server_default='EMPLOYEES'))


def downgrade() -> None:
    op.drop_column('rewards', 'eligibility')
