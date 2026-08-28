"""commitment candidate intelligence: derived, fallible, bounded

Adds the commitment_candidates table backing the watcher's implicit-commitment
lane. Candidates are derived Cortex state (never canonical tasks); stable
candidate keys make redelivery idempotent, canonical keys make dismissal
durable, and pending candidates expire.

Revision ID: 0010_commitment_candidates
Revises: 0009_source_linked_objects
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_commitment_candidates"
down_revision = "0009_source_linked_objects"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "commitment_candidates",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("honcho_session_id", sa.String(), nullable=False),
        sa.Column("owner_peer_id", sa.String(), nullable=False),
        sa.Column("candidate_key", sa.String(), nullable=False),
        sa.Column("canonical_key", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_verbatim", sa.String(), nullable=False),
        sa.Column("evidence_class", sa.String(), nullable=False),
        sa.Column("authority", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_message_id", sa.String(), nullable=False),
        sa.Column("materialized_source_object_id", sa.String(), nullable=True),
        sa.Column("raw_temporal_phrase", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "honcho_workspace_id",
            "owner_peer_id",
            "candidate_key",
            name="uq_commitment_candidate_workspace_owner_key",
        ),
    )
    op.create_index(
        "ix_commitment_candidates_honcho_workspace_id",
        "commitment_candidates",
        ["honcho_workspace_id"],
    )
    op.create_index(
        "ix_commitment_candidates_honcho_session_id",
        "commitment_candidates",
        ["honcho_session_id"],
    )
    op.create_index(
        "ix_commitment_candidates_owner_peer_id", "commitment_candidates", ["owner_peer_id"]
    )
    op.create_index(
        "ix_commitment_candidates_canonical_key", "commitment_candidates", ["canonical_key"]
    )
    op.create_index(
        "ix_commitment_candidates_status", "commitment_candidates", ["status"]
    )
    op.create_index(
        "ix_commitment_candidates_source_message_id",
        "commitment_candidates",
        ["source_message_id"],
    )
    op.create_index(
        "ix_commitment_candidates_materialized_source_object_id",
        "commitment_candidates",
        ["materialized_source_object_id"],
    )


def downgrade():
    op.drop_table("commitment_candidates")
