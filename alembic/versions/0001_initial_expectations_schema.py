"""initial expectations schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-08-11 16:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'expectations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('honcho_message_id', sa.String(), nullable=False),
        sa.Column('honcho_document_id', sa.String(), nullable=True),
        sa.Column('candidate_key', sa.String(), nullable=False, server_default='primary'),
        sa.Column('source_start', sa.Integer(), nullable=True),
        sa.Column('source_end', sa.Integer(), nullable=True),
        sa.Column('subject_peer_id', sa.String(), nullable=False),
        sa.Column('expectation_type', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('summary', sa.String(), nullable=False),
        sa.Column('raw_temporal_phrase', sa.String(), nullable=True),
        sa.Column('anchor_timezone', sa.String(), nullable=False),
        sa.Column('expected_window_start', sa.DateTime(), nullable=True),
        sa.Column('expected_window_end', sa.DateTime(), nullable=True),
        sa.Column('hard_deadline_at', sa.DateTime(), nullable=True),
        sa.Column('outcome_state', sa.String(), nullable=False),
        sa.Column('extraction_confidence', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'honcho_workspace_id', 'honcho_message_id', 'candidate_key',
            name='uq_expectation_workspace_message_candidate'
        )
    )
    op.create_index(op.f('ix_expectations_honcho_workspace_id'), 'expectations', ['honcho_workspace_id'], unique=False)
    op.create_index(op.f('ix_expectations_honcho_session_id'), 'expectations', ['honcho_session_id'], unique=False)
    op.create_index(op.f('ix_expectations_subject_peer_id'), 'expectations', ['subject_peer_id'], unique=False)
    op.create_index(op.f('ix_expectations_outcome_state'), 'expectations', ['outcome_state'], unique=False)
    op.create_index(op.f('ix_expectations_candidate_key'), 'expectations', ['candidate_key'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_expectations_candidate_key'), table_name='expectations')
    op.drop_index(op.f('ix_expectations_outcome_state'), table_name='expectations')
    op.drop_index(op.f('ix_expectations_subject_peer_id'), table_name='expectations')
    op.drop_index(op.f('ix_expectations_honcho_session_id'), table_name='expectations')
    op.drop_index(op.f('ix_expectations_honcho_workspace_id'), table_name='expectations')
    op.drop_table('expectations')
