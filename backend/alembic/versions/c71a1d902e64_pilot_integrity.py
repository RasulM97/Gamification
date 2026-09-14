"""N7.1 task grants, account lifecycle and cancellation snapshots.

Revision ID: c71a1d902e64
Revises: b72e4d1f8307
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'c71a1d902e64'
down_revision = 'b72e4d1f8307'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('active', sa.Boolean(), nullable=False, server_default='true'))
    for name in ('viewer_ids', 'reviewer_ids', 'restricted_audiences'):
        op.add_column('tasks', sa.Column(name, JSONB(), nullable=False, server_default='[]'))
    op.add_column('tasks', sa.Column('private_worker_role', sa.String(20), nullable=True))
    op.add_column('redemptions', sa.Column('cancelled_by', JSONB(), nullable=True))
    op.add_column('redemptions', sa.Column('cancelled_at', sa.Float(), nullable=True))
    # Add derived metadata only. Ledger, activity, cycles and authored content
    # remain untouched. Legacy structured events retain earlier restrictions.
    op.execute("""UPDATE tasks t SET restricted_audiences = COALESCE((
        SELECT jsonb_agg(DISTINCT audience) FROM (
          SELECT t.audience AS audience UNION ALL
          SELECT a.params->>'audience' FROM activity a
          WHERE a.company_id=t.company_id AND a.task_id=t.id
        ) h WHERE audience IN ('PRIVATE','MANAGEMENT')), '[]'::jsonb)""")
    op.execute("""UPDATE tasks t SET private_worker_role=u.role FROM users u
        WHERE t.audience='PRIVATE' AND u.company_id=t.company_id
        AND u.id=COALESCE(t.owner_id,t.assignee_id)""")
    op.execute("""UPDATE redemptions r SET cancelled_by=jsonb_build_object(
        'id', a.actor_id, 'name', a.params->>'actor'), cancelled_at=a.at
        FROM activity a WHERE r.status='CANCELLED' AND a.company_id=r.company_id
        AND a.event_type='REDEMPTION_CANCELLED' AND a.params->>'redemptionId'=r.id""")


def downgrade():
    for name in ('cancelled_at', 'cancelled_by'):
        op.drop_column('redemptions', name)
    for name in ('private_worker_role', 'restricted_audiences', 'reviewer_ids', 'viewer_ids'):
        op.drop_column('tasks', name)
    op.drop_column('users', 'active')
