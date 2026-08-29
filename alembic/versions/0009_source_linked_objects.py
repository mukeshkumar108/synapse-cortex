"""stable source-link contract for canonical external objects

Adds identity/version source references to expectations (app-owned tasks,
Google Calendar events) plus explicit reminder windows, and source links +
owner scoping to attention candidates (bounded post-event follow-ups).

Revision ID: 0009_source_linked_objects
Revises: 0008_cross_chat_ownership
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_source_linked_objects"
down_revision = "0008_cross_chat_ownership"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("expectations", sa.Column("source_system", sa.String(32), nullable=True))
    op.add_column("expectations", sa.Column("source_object_id", sa.String(256), nullable=True))
    op.add_column("expectations", sa.Column("source_version", sa.Integer(), nullable=True))
    op.add_column("expectations", sa.Column("reminder_windows_json", sa.Text(), nullable=True))
    op.create_index(
        "ix_expectations_source_system", "expectations", ["source_system"]
    )
    op.create_index(
        "ix_expectations_source_object_id", "expectations", ["source_object_id"]
    )
    op.create_index(
        "uq_expectation_workspace_source_object",
        "expectations",
        ["honcho_workspace_id", "source_system", "source_object_id", "owner_peer_id"],
        unique=True,
        postgresql_where=sa.text(
            "source_system IS NOT NULL AND superseded_by_id IS NULL"
        ),
        sqlite_where=sa.text(
            "source_system IS NOT NULL AND superseded_by_id IS NULL"
        ),
    )

    op.add_column(
        "attention_candidates",
        sa.Column("owner_peer_id", sa.String(), nullable=True),
    )
    op.add_column(
        "attention_candidates",
        sa.Column("source_system", sa.String(32), nullable=True),
    )
    op.add_column(
        "attention_candidates",
        sa.Column("source_object_id", sa.String(256), nullable=True),
    )
    op.create_index(
        "ix_attention_candidates_owner_peer_id",
        "attention_candidates",
        ["owner_peer_id"],
    )
    op.create_index(
        "ix_attention_candidates_source_system",
        "attention_candidates",
        ["source_system"],
    )
    op.create_index(
        "ix_attention_candidates_source_object_id",
        "attention_candidates",
        ["source_object_id"],
    )


def downgrade():
    op.drop_index(
        "ix_attention_candidates_source_object_id", table_name="attention_candidates"
    )
    op.drop_index(
        "ix_attention_candidates_source_system", table_name="attention_candidates"
    )
    op.drop_index(
        "ix_attention_candidates_owner_peer_id", table_name="attention_candidates"
    )
    op.drop_column("attention_candidates", "source_object_id")
    op.drop_column("attention_candidates", "source_system")
    op.drop_column("attention_candidates", "owner_peer_id")

    op.drop_index(
        "uq_expectation_workspace_source_object", table_name="expectations"
    )
    op.drop_index("ix_expectations_source_object_id", table_name="expectations")
    op.drop_index("ix_expectations_source_system", table_name="expectations")
    op.drop_column("expectations", "reminder_windows_json")
    op.drop_column("expectations", "source_version")
    op.drop_column("expectations", "source_object_id")
    op.drop_column("expectations", "source_system")
