"""append-only neutral candidate lifecycle receipts

Revision ID: 0019_candidate_receipts
Revises: 0018_current_meaning
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_candidate_receipts"
down_revision = "0018_current_meaning"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "candidate_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("receipt_id", sa.String(), nullable=False),
        sa.Column("decision_id", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("candidate_version", sa.String(), nullable=False),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("owner_peer_id", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("assistant_message_id", sa.String(), nullable=True),
        sa.Column("effect", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "decision_id", "candidate_id", "stage",
            name="uq_candidate_receipt_stage",
        ),
        sa.UniqueConstraint("receipt_id", name="uq_candidate_receipt_id"),
    )
    for column in (
        "receipt_id", "decision_id", "turn_id", "candidate_id",
        "honcho_workspace_id", "owner_peer_id", "stage",
        "assistant_message_id",
    ):
        op.create_index(
            f"ix_candidate_receipts_{column}", "candidate_receipts", [column]
        )


def downgrade():
    op.drop_table("candidate_receipts")
