"""Session-consolidation run ledger (ConsolidationRun contract).

Durable audit ledger for session-consolidation runs (shadow + apply): one
row per invocation that reached a model call (or recorded failure), carrying
lane + temporal provenance, completion/segment accounting and accepted payload
so retries converge and applied rows stay attributable. Raw evidence remains
canonical; this table is revisit index only.
"""
from alembic import op
import sqlalchemy as sa
revision = '0031_consolidation_runs'
down_revision = '0030_current_scene'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'consolidation_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('temporal_session_id', sa.String(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('summary', sa.String(), nullable=False),
        sa.Column('completion', sa.String(), nullable=False),
        sa.Column('segment_map_json', sa.String(), nullable=False),
        sa.Column('accepted_json', sa.String(), nullable=False),
        sa.Column('prior_run_id', sa.Uuid(), nullable=True),
        sa.Column('accepted_count', sa.Integer(), nullable=False),
        sa.Column('rejected_count', sa.Integer(), nullable=False),
        sa.Column('applied_count', sa.Integer(), nullable=False),
        sa.Column('deferred_count', sa.Integer(), nullable=False),
        sa.Column('error', sa.String(), nullable=False),
        sa.Column('prompt_chars', sa.Integer(), nullable=False),
        sa.Column('latency_s', sa.Float(), nullable=False),
        sa.Column('owner_peer_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ('honcho_workspace_id', 'honcho_session_id', 'owner_peer_id'):
        op.create_index(f'ix_consolidation_runs_{col}', 'consolidation_runs', [col])

def downgrade():
    for col in ('owner_peer_id', 'honcho_session_id', 'honcho_workspace_id'):
        op.drop_index(f'ix_consolidation_runs_{col}', table_name='consolidation_runs')
    op.drop_table('consolidation_runs')
