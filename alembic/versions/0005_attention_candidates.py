"""grounded Sophie-side attention candidates

Revision ID: 0005_attention_candidates
Revises: 0004_extractor_reconciliation
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_attention_candidates"
down_revision = "0004_extractor_reconciliation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "attention_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("honcho_session_id", sa.String(), nullable=False),
        sa.Column("source_message_id", sa.String(), nullable=False),
        sa.Column("source_assistant_message_id", sa.String(), nullable=True),
        sa.Column("candidate_key", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("salience", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("not_before", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("surfaced_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_surfaced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("honcho_workspace_id", "source_message_id", "candidate_key", name="uq_attention_candidate_workspace_source_key"),
    )
    for column in ("honcho_workspace_id", "honcho_session_id", "source_message_id", "source_assistant_message_id", "kind", "status", "not_before", "expires_at"):
        op.create_index(f"ix_attention_candidates_{column}", "attention_candidates", [column])


def downgrade():
    op.drop_table("attention_candidates")
