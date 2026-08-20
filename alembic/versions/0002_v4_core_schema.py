"""V4 Core Schema Migration: open_loops, suppressions, clarifications, epistemic, domain annotations

Revision ID: 0003_v4_core
Revises: 0002_multi_expectation
Create Date: 2026-08-11 17:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0003_v4_core'
down_revision: Union[str, None] = '0002_multi_expectation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update expectations table with version and resolution_evidence columns
    op.add_column('expectations', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('expectations', sa.Column('superseded_by_id', sa.Uuid(), nullable=True))
    op.add_column('expectations', sa.Column('resolution_evidence', sa.String(), nullable=True))
    op.create_index(op.f('ix_expectations_superseded_by_id'), 'expectations', ['superseded_by_id'], unique=False)

    # 2. open_loops table
    op.create_table(
        'open_loops',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('honcho_message_id', sa.String(), nullable=False),
        sa.Column('candidate_key', sa.String(), nullable=False, server_default='primary'),
        sa.Column('expectation_id', sa.Uuid(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('summary', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('resolution_evidence', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('honcho_workspace_id', 'honcho_message_id', 'candidate_key', name='uq_open_loop_workspace_message_candidate')
    )
    op.create_index(op.f('ix_open_loops_honcho_workspace_id'), 'open_loops', ['honcho_workspace_id'], unique=False)
    op.create_index(op.f('ix_open_loops_honcho_session_id'), 'open_loops', ['honcho_session_id'], unique=False)
    op.create_index(op.f('ix_open_loops_status'), 'open_loops', ['status'], unique=False)
    op.create_index(op.f('ix_open_loops_expectation_id'), 'open_loops', ['expectation_id'], unique=False)

    # 3. suppressions table
    op.create_table(
        'suppressions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('honcho_message_id', sa.String(), nullable=False),
        sa.Column('candidate_key', sa.String(), nullable=False, server_default='primary'),
        sa.Column('target_type', sa.String(), nullable=False),
        sa.Column('target_id', sa.String(), nullable=True),
        sa.Column('topic_or_entity', sa.String(), nullable=True),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('suppressed_until', sa.DateTime(), nullable=True),
        sa.Column('reopen_condition', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('honcho_workspace_id', 'honcho_message_id', 'candidate_key', name='uq_suppression_workspace_message_candidate')
    )
    op.create_index(op.f('ix_suppressions_honcho_workspace_id'), 'suppressions', ['honcho_workspace_id'], unique=False)
    op.create_index(op.f('ix_suppressions_honcho_session_id'), 'suppressions', ['honcho_session_id'], unique=False)
    op.create_index(op.f('ix_suppressions_status'), 'suppressions', ['status'], unique=False)
    op.create_index(op.f('ix_suppressions_target_id'), 'suppressions', ['target_id'], unique=False)
    op.create_index(op.f('ix_suppressions_topic_or_entity'), 'suppressions', ['topic_or_entity'], unique=False)
    op.create_index(op.f('ix_suppressions_suppressed_until'), 'suppressions', ['suppressed_until'], unique=False)

    # 4. clarification_candidates table
    op.create_table(
        'clarification_candidates',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('honcho_message_id', sa.String(), nullable=False),
        sa.Column('candidate_key', sa.String(), nullable=False, server_default='primary'),
        sa.Column('clarification_type', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('candidates_json', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('honcho_workspace_id', 'honcho_message_id', 'candidate_key', 'clarification_type', name='uq_clarification_event_candidate_type')
    )
    op.create_index(op.f('ix_clarification_candidates_honcho_workspace_id'), 'clarification_candidates', ['honcho_workspace_id'], unique=False)
    op.create_index(op.f('ix_clarification_candidates_honcho_session_id'), 'clarification_candidates', ['honcho_session_id'], unique=False)
    op.create_index(op.f('ix_clarification_candidates_status'), 'clarification_candidates', ['status'], unique=False)

    # 5. epistemic_annotations table
    op.create_table(
        'epistemic_annotations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('honcho_message_id', sa.String(), nullable=False),
        sa.Column('candidate_key', sa.String(), nullable=False, server_default='primary'),
        sa.Column('target_expectation_id', sa.Uuid(), nullable=True),
        sa.Column('target_loop_id', sa.Uuid(), nullable=True),
        sa.Column('perspective_peer_id', sa.String(), nullable=False),
        sa.Column('target_peer_id', sa.String(), nullable=True),
        sa.Column('provenance_type', sa.String(), nullable=False),
        sa.Column('claim_summary', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('honcho_workspace_id', 'honcho_message_id', 'candidate_key', name='uq_epistemic_workspace_message_candidate')
    )
    op.create_index(op.f('ix_epistemic_annotations_honcho_workspace_id'), 'epistemic_annotations', ['honcho_workspace_id'], unique=False)
    op.create_index(op.f('ix_epistemic_annotations_honcho_session_id'), 'epistemic_annotations', ['honcho_session_id'], unique=False)
    op.create_index(op.f('ix_epistemic_annotations_perspective_peer_id'), 'epistemic_annotations', ['perspective_peer_id'], unique=False)
    op.create_index(op.f('ix_epistemic_annotations_target_peer_id'), 'epistemic_annotations', ['target_peer_id'], unique=False)

    # 6. domain_annotations table
    op.create_table(
        'domain_annotations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('honcho_message_id', sa.String(), nullable=False),
        sa.Column('candidate_key', sa.String(), nullable=False, server_default='primary'),
        sa.Column('domain', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('annotation_summary', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('honcho_workspace_id', 'honcho_message_id', 'candidate_key', name='uq_domain_workspace_message_candidate')
    )
    op.create_index(op.f('ix_domain_annotations_honcho_workspace_id'), 'domain_annotations', ['honcho_workspace_id'], unique=False)
    op.create_index(op.f('ix_domain_annotations_honcho_session_id'), 'domain_annotations', ['honcho_session_id'], unique=False)
    op.create_index(op.f('ix_domain_annotations_domain'), 'domain_annotations', ['domain'], unique=False)
    op.create_index(op.f('ix_domain_annotations_category'), 'domain_annotations', ['category'], unique=False)


def downgrade() -> None:
    op.drop_table('domain_annotations')
    op.drop_table('epistemic_annotations')
    op.drop_table('clarification_candidates')
    op.drop_table('suppressions')
    op.drop_table('open_loops')
    op.drop_index(op.f('ix_expectations_superseded_by_id'), table_name='expectations')
    op.drop_column('expectations', 'resolution_evidence')
    op.drop_column('expectations', 'superseded_by_id')
    op.drop_column('expectations', 'version')
