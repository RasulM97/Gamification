"""Immutable manager recommendation, without task/economic state changes."""
from alembic import op
import sqlalchemy as sa

revision = 'ee05d2b22601'
down_revision = 'ee04f0202601'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_submission_identity', 'submissions', ['company_id', 'id', 'task_id', 'cycle'])
    op.create_table('task_recommendations',
        sa.Column('id', sa.String(40), primary_key=True),
        sa.Column('company_id', sa.String(40), nullable=False),
        sa.Column('task_id', sa.String(40), nullable=False),
        sa.Column('cycle', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.String(40), nullable=False),
        sa.Column('author_id', sa.String(40), nullable=False),
        sa.Column('author_name', sa.String(300), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.UniqueConstraint('company_id', 'submission_id', name='uq_task_recommendation_submission'),
        sa.ForeignKeyConstraint(['company_id', 'submission_id', 'task_id', 'cycle'],
            ['submissions.company_id', 'submissions.id', 'submissions.task_id', 'submissions.cycle'],
            name='fk_task_recommendation_submission'),
        sa.ForeignKeyConstraint(['company_id', 'author_id'], ['users.company_id', 'users.id'], name='fk_task_recommendation_author'),
        sa.CheckConstraint('length(btrim(note)) BETWEEN 1 AND 2000', name='ck_task_recommendation_note'))
    op.create_index('ix_task_recommendations_company_id', 'task_recommendations', ['company_id'])
    op.create_index('ix_task_recommendations_task_id', 'task_recommendations', ['task_id'])
    op.execute("""
CREATE FUNCTION cve_task_recommendation_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Task recommendation history is immutable' USING ERRCODE = '23514';
END $$;
CREATE TRIGGER task_recommendation_immutable BEFORE UPDATE OR DELETE ON task_recommendations
FOR EACH ROW EXECUTE FUNCTION cve_task_recommendation_immutable();
""")


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM task_recommendations')):
        raise RuntimeError('Cannot discard immutable task recommendation history')
    op.execute('DROP TRIGGER task_recommendation_immutable ON task_recommendations')
    op.execute('DROP FUNCTION cve_task_recommendation_immutable()')
    op.drop_table('task_recommendations')
    op.drop_constraint('uq_submission_identity', 'submissions', type_='unique')
