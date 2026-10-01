"""Derived Cortex state: WorldModel snapshots, knowledge coverage, session episodes.

All three are disposable/reconstructable (episodes hold prose + references to
canonical writes only). Downgrade drops the tables.
"""
from alembic import op
import sqlalchemy as sa
revision = '0034_world_model_coverage'
down_revision = '0033_epistemic_direction'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'world_model_snapshots',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('owner_peer_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('compiled_at', sa.DateTime(), nullable=False),
        sa.Column('snapshot_json', sa.String(), nullable=False),
        sa.Column('fingerprints_json', sa.String(), nullable=False),
        sa.Column('superseded_by_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ('honcho_workspace_id', 'owner_peer_id', 'superseded_by_id'):
        op.create_index(f'ix_world_model_snapshots_{col}', 'world_model_snapshots', [col])

    op.create_table(
        'knowledge_coverage',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('owner_peer_id', sa.String(), nullable=True),
        sa.Column('subject_key', sa.String(), nullable=False),
        sa.Column('parent_key', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('basis', sa.String(), nullable=False),
        sa.Column('evidence_count', sa.Integer(), nullable=False),
        sa.Column('evidence_refs_json', sa.String(), nullable=False),
        sa.Column('last_evidence_at', sa.DateTime(), nullable=True),
        sa.Column('why_useful', sa.String(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('honcho_workspace_id', 'owner_peer_id', 'subject_key',
                            name='uq_knowledge_coverage_subject'),
        sa.CheckConstraint(
            "status IN ('known','partial','unknown','stale','conflicting')",
            name='ck_knowledge_coverage_status'),
    )
    for col in ('honcho_workspace_id', 'owner_peer_id', 'subject_key', 'parent_key', 'status'):
        op.create_index(f'ix_knowledge_coverage_{col}', 'knowledge_coverage', [col])

    op.create_table(
        'session_episodes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('temporal_session_id', sa.String(), nullable=False),
        sa.Column('consolidation_run_id', sa.Uuid(), nullable=True),
        sa.Column('owner_peer_id', sa.String(), nullable=True),
        sa.Column('summary', sa.String(), nullable=False),
        sa.Column('writes_json', sa.String(), nullable=False),
        sa.Column('detected_json', sa.String(), nullable=False),
        sa.Column('matters_touched_json', sa.String(), nullable=False),
        sa.Column('entities_touched_json', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ('honcho_workspace_id', 'honcho_session_id', 'consolidation_run_id', 'owner_peer_id'):
        op.create_index(f'ix_session_episodes_{col}', 'session_episodes', [col])


def downgrade():
    op.drop_table('session_episodes')
    op.drop_table('knowledge_coverage')
    op.drop_table('world_model_snapshots')
