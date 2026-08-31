"""proactive delivery ledger (initiative engine accounting)

Revision ID: 0015_proactive_log
Revises: 0014_agenda
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_proactive_log"
down_revision = "0014_agenda"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "proactive_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("owner_peer_id", sa.String(), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("item_key", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
    )
    op.create_index("ix_proactive_log_owner_at", "proactive_log", ["honcho_workspace_id", "owner_peer_id", "at"])


def downgrade():
    op.drop_index("ix_proactive_log_owner_at", table_name="proactive_log")
    op.drop_table("proactive_log")
