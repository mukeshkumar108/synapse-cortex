"""agenda snapshot table (one live ranked attention artifact per owner)

Revision ID: 0014_agenda
Revises: 0013_occurrence_followup
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_agenda"
down_revision = "0013_occurrence_followup"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agenda_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("owner_peer_id", sa.String(), nullable=True),
        sa.Column("item_key", sa.String(), nullable=False),
        sa.Column("compiled_at", sa.DateTime(), nullable=False),
        sa.Column("horizon", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("what", sa.String(), nullable=False),
        sa.Column("semantic_type", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("urgency", sa.Float(), nullable=False),
        sa.Column("pressure", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("why", sa.String(), nullable=False),
        sa.Column("next_move", sa.String(), nullable=False),
        sa.Column("occurrence_id", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("honcho_workspace_id", "owner_peer_id", "item_key", "compiled_at", name="uq_agenda_item_compiled"),
    )
    op.create_table(
        "agenda_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("owner_peer_id", sa.String(), nullable=True),
        sa.Column("horizon", sa.String(), nullable=False),
        sa.Column("items_json", sa.String(), nullable=False),
        sa.Column("compiled_by", sa.String(), nullable=False),
        sa.Column("compiled_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("honcho_workspace_id", "owner_peer_id", "horizon", name="uq_agenda_snapshot_owner_horizon"),
    )


def downgrade():
    op.drop_table("agenda_snapshots")
    op.drop_table("agenda_items")
