"""derived backstage signals (bounded per-session, evidence in payload)

Revision ID: 0007_derived_signals
Revises: 0006_operational_state
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_derived_signals"
down_revision = "0006_operational_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "derived_signals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("honcho_session_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("payload_json", sa.String(), nullable=False),
        sa.Column("last_message_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "honcho_workspace_id", "honcho_session_id", "kind",
            name="uq_derived_signal_workspace_session_kind",
        ),
    )
    for column in ["honcho_workspace_id", "honcho_session_id", "kind"]:
        op.create_index(f"ix_derived_signals_{column}", "derived_signals", [column])


def downgrade():
    for column in ["honcho_workspace_id", "honcho_session_id", "kind"]:
        op.drop_index(f"ix_derived_signals_{column}", table_name="derived_signals")
    op.drop_table("derived_signals")