"""N2.2 — reward operations & fulfillment

Adds:
- users.can_fulfill_rewards (REWARD_FULFILL capability, §6) — boolean,
  default false; admins fulfill by office and never carry the flag.
- rewards.per_user_limit (§2, NULL = unlimited), rewards.available_from /
  rewards.available_until (§3, UTC ms epoch, NULL = open-ended),
  rewards.archived (§4, default false).
- reward_categories (§1): one flat admin-managed category level. Existing
  installations get the canonical six seeded per company; historical reward
  category strings are preserved verbatim (archiving never invalidates).
- reward_executors (§7): join table for admin-assigned executor seats.
- redemptions.approved_by / approved_at / fulfilled_by / fulfilled_at /
  fulfillment_reference / fulfillment_note (§5, §10).

Status semantics change (§9): redemptions.status gains 'APPROVED'
(PENDING → APPROVED → FULFILLED | CANCELLED). No data rewrite needed —
existing PENDING rows stay pending approval; existing FULFILLED rows stay
fulfilled.

All columns are nullable or carry server defaults — the migration is safe
against live pilot data and preserves every existing row.

Revision ID: e7f2a4c61d83
Revises: d4e5b8c10f92
Create Date: 2026-09-08

NOTE (sandbox): prepared but NOT executed here — the migration gate is
founder-side against the real PostgreSQL instance (see
docs/EXTERNAL_POSTGRESQL_RUN.md).
"""
from alembic import op
import sqlalchemy as sa

revision = 'e7f2a4c61d83'
down_revision = 'd4e5b8c10f92'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column(
        'can_fulfill_rewards', sa.Boolean(), nullable=False,
        server_default=sa.text('false')))

    op.add_column('rewards', sa.Column('per_user_limit', sa.Integer(), nullable=True))
    op.add_column('rewards', sa.Column('available_from', sa.Float(), nullable=True))
    op.add_column('rewards', sa.Column('available_until', sa.Float(), nullable=True))
    op.add_column('rewards', sa.Column(
        'archived', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    op.create_table(
        'reward_categories',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )

    op.create_table(
        'reward_executors',
        sa.Column('reward_id', sa.String(40),
                  sa.ForeignKey('rewards.id'), primary_key=True),
        sa.Column('user_id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40),
                  sa.ForeignKey('companies.id'), nullable=False, index=True),
    )

    op.add_column('redemptions', sa.Column('approved_by', sa.String(40), nullable=True))
    op.add_column('redemptions', sa.Column('approved_at', sa.Float(), nullable=True))
    op.add_column('redemptions', sa.Column('fulfilled_by', sa.String(40), nullable=True))
    op.add_column('redemptions', sa.Column('fulfilled_at', sa.Float(), nullable=True))
    op.add_column('redemptions', sa.Column('fulfillment_reference', sa.String(200), nullable=True))
    op.add_column('redemptions', sa.Column('fulfillment_note', sa.Text(), nullable=True))

    # Seed the canonical flat categories for every existing company.
    op.execute("""
        INSERT INTO reward_categories (id, company_id, name, active)
        SELECT 'rc-' || lower(replace(name, ' ', '')) || '-' || c.id, c.id, name, true
        FROM companies c
        CROSS JOIN (VALUES ('Food'), ('Entertainment'), ('Transportation'),
                           ('Wellness'), ('Merchandise'), ('Company Perks')) AS v(name)
    """)


def downgrade() -> None:
    op.drop_column('redemptions', 'fulfillment_note')
    op.drop_column('redemptions', 'fulfillment_reference')
    op.drop_column('redemptions', 'fulfilled_at')
    op.drop_column('redemptions', 'fulfilled_by')
    op.drop_column('redemptions', 'approved_at')
    op.drop_column('redemptions', 'approved_by')
    op.drop_table('reward_executors')
    op.drop_table('reward_categories')
    op.drop_column('rewards', 'archived')
    op.drop_column('rewards', 'available_until')
    op.drop_column('rewards', 'available_from')
    op.drop_column('rewards', 'per_user_limit')
    op.drop_column('users', 'can_fulfill_rewards')
