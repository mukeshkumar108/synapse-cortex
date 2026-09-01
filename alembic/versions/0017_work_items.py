"""work items migration

Revision ID: 0017_work_items
Revises: 0016_turn_stamp
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_work_items"
down_revision = "0016_turn_stamp"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False, index=True),
        sa.Column("owner_peer_id", sa.String(), nullable=False, index=True),
        sa.Column("honcho_session_id", sa.String(), nullable=True),
        sa.Column("parent_type", sa.String(), nullable=False, index=True),
        sa.Column("parent_id", sa.String(), nullable=False, index=True),
        sa.Column("parent_title", sa.String(), nullable=True),
        sa.Column("owner", sa.String(), nullable=False, index=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, index=True),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("authority", sa.String(), nullable=True),
        sa.Column("due_window_start", sa.DateTime(), nullable=True),
        sa.Column("due_window_end", sa.DateTime(), nullable=True),
        sa.Column("completion_condition", sa.String(), nullable=True),
        sa.Column("blocker", sa.String(), nullable=True),
        sa.Column("sophie_executable", sa.Boolean(), nullable=False),
        sa.Column("source_agent", sa.String(), nullable=False),
        sa.Column("evidence_text", sa.String(), nullable=True),
        sa.Column("provenance_json", sa.String(), nullable=False),
        sa.Column("surfaced_count", sa.Integer(), nullable=False),
        sa.Column("last_surfaced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("extra_json", sa.String(), nullable=False),
    )


def downgrade():
    op.drop_table("work_items")
