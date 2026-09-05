"""N2.1-A2 — reward ownership

Adds rewards.created_by (user id of the creator). Canonical rule: the admin
manages every reward; a manager manages only rewards they created.

Existing rows are backfilled to the company's ADMIN user — every pre-N2.1
reward was admin-created, so the backfill is behavior-preserving and a
manager does not suddenly gain edit authority over the existing catalog.
The column is NOT NULL with a server default so inserts are always
well-defined; the application always writes the actor's id explicitly.

Revision ID: d4e5b8c10f92
Revises: c3f1a2d9e847
Create Date: 2026-09-05

NOTE (sandbox): prepared but NOT executed here — the migration gate is
founder-side against the real PostgreSQL instance (see
docs/EXTERNAL_POSTGRESQL_RUN.md).
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5b8c10f92'
down_revision = 'c3f1a2d9e847'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('rewards', sa.Column(
        'created_by', sa.String(length=40), nullable=False,
        server_default=''))
    # Backfill: every pre-N2.1 reward was admin-created → attribute to the
    # company's admin so ownership is truthful and managers gain nothing.
    op.execute("""
        UPDATE rewards
        SET created_by = (
            SELECT u.id FROM users u
            WHERE u.company_id = rewards.company_id AND u.role = 'ADMIN'
            LIMIT 1)
        WHERE created_by = ''
    """)


def downgrade() -> None:
    op.drop_column('rewards', 'created_by')
