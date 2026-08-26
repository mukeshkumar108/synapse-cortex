"""owner-scoped durable state for safe cross-chat continuity

Revision ID: 0008_cross_chat_ownership
Revises: 0007_derived_signals
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_cross_chat_ownership"
down_revision = "0007_derived_signals"
branch_labels = None
depends_on = None


TABLES = ("expectations", "open_loops", "recurring_intentions", "objective_progress")


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column("owner_peer_id", sa.String(), nullable=True))
        op.create_index(f"ix_{table}_owner_peer_id", table, ["owner_peer_id"])


def downgrade():
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_owner_peer_id", table_name=table)
        op.drop_column(table, "owner_peer_id")
