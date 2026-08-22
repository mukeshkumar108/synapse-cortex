"""model-led operational watcher state

Revision ID: 0006_operational_state
Revises: 0005_attention_candidates
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_operational_state"
down_revision = "0005_attention_candidates"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("suppressions", sa.Column("surface_scope", sa.String(), nullable=False, server_default="all_surfaces"))
    op.create_index("ix_suppressions_surface_scope", "suppressions", ["surface_scope"])
    op.add_column("open_loops", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_open_loops_expires_at", "open_loops", ["expires_at"])
    op.create_table(
        "recurring_intentions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("honcho_session_id", sa.String(), nullable=False),
        sa.Column("honcho_message_id", sa.String(), nullable=False),
        sa.Column("candidate_key", sa.String(), nullable=False),
        sa.Column("canonical_key", sa.String(), nullable=False),
        sa.Column("active_slot", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("cadence", sa.String(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("days_of_week_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
        sa.Column("preferred_window", sa.String(), nullable=True),
        sa.Column("target_amount", sa.Float(), nullable=True),
        sa.Column("target_unit", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"),
        sa.Column("source_evidence", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("honcho_workspace_id", "honcho_session_id", "canonical_key", "active_slot", name="uq_recurring_active_key"),
        sa.UniqueConstraint("honcho_workspace_id", "honcho_message_id", "candidate_key", name="uq_recurring_source_candidate"),
    )
    op.create_table(
        "recurring_occurrences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("recurring_intention_id", sa.Uuid(), nullable=False),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("user_day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("progress_amount", sa.Float(), nullable=True),
        sa.Column("progress_unit", sa.String(), nullable=True),
        sa.Column("source_message_id", sa.String(), nullable=True),
        sa.Column("evidence", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("recurring_intention_id", "user_day", name="uq_recurring_occurrence_day"),
    )
    op.create_table(
        "objective_progress",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("honcho_session_id", sa.String(), nullable=False),
        sa.Column("honcho_message_id", sa.String(), nullable=False),
        sa.Column("candidate_key", sa.String(), nullable=False),
        sa.Column("expectation_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("user_day", sa.Date(), nullable=False),
        sa.Column("evidence", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("honcho_workspace_id", "honcho_message_id", "candidate_key", name="uq_progress_source_candidate"),
    )
    op.create_table(
        "extraction_traces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False),
        sa.Column("honcho_session_id", sa.String(), nullable=False),
        sa.Column("honcho_message_id", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("item_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("detail_json", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("honcho_workspace_id", "honcho_message_id", "stage", "item_key", name="uq_extraction_trace_stage_item"),
    )
    for table, columns in {
        "recurring_intentions": ["honcho_workspace_id", "honcho_session_id", "honcho_message_id", "canonical_key", "active_slot", "status", "superseded_by_id"],
        "recurring_occurrences": ["recurring_intention_id", "honcho_workspace_id", "user_day", "status", "source_message_id"],
        "objective_progress": ["honcho_workspace_id", "honcho_session_id", "honcho_message_id", "expectation_id", "user_day"],
        "extraction_traces": ["honcho_workspace_id", "honcho_session_id", "honcho_message_id", "stage", "status"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    op.drop_table("extraction_traces")
    op.drop_table("objective_progress")
    op.drop_table("recurring_occurrences")
    op.drop_table("recurring_intentions")
    op.drop_index("ix_open_loops_expires_at", table_name="open_loops")
    op.drop_column("open_loops", "expires_at")
    op.drop_index("ix_suppressions_surface_scope", table_name="suppressions")
    op.drop_column("suppressions", "surface_scope")
