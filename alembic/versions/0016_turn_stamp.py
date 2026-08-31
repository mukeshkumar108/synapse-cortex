"""agenda snapshot + turn stamp migration

Revision ID: 0016_turn_stamp
Revises: 0015_proactive_log
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_turn_stamp"
down_revision = "0015_proactive_log"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "turn_stamps",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("owner_peer_id", sa.String(), nullable=True),
        sa.Column("honcho_message_id", sa.String(), nullable=False),
        sa.Column("turn_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("honcho_workspace_id", "honcho_message_id", name="uq_turn_stamp_message"),
    )
    op.create_index("ix_turn_stamps_owner_turn_at", "turn_stamps", ["honcho_workspace_id", "turn_at"])


def downgrade():
    op.drop_index("ix_turn_stamps_owner_turn_at", table_name="turn_stamps")
    op.drop_table("turn_stamps")
