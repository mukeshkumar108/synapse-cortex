"""current meaning v1 (versioned live interpretation)

Revision ID: 0018_current_meaning
Revises: 0017_work_items
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_current_meaning"
down_revision = "0017_work_items"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "current_meanings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("honcho_workspace_id", sa.String(), nullable=False, index=True),
        sa.Column("product", sa.String(), nullable=False, index=True),
        sa.Column("honcho_session_id", sa.String(), nullable=False, index=True),
        sa.Column("owner_peer_id", sa.String(), nullable=False, index=True),
        sa.Column("scope_key", sa.String(), nullable=False, index=True),
        sa.Column("means_json", sa.String(), nullable=False),
        sa.Column("unresolved_json", sa.String(), nullable=False),
        sa.Column("source_message_ids_json", sa.String(), nullable=False),
        sa.Column("extractor_version", sa.String(), nullable=False, index=True),
        sa.Column("lens_version", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("revision_key", sa.String(), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("superseded_by_id", sa.String(), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scope_key", "revision_key", name="uq_current_meaning_scope_revision"),
    )
    op.create_index("ix_current_meaning_scope_active", "current_meanings", ["scope_key", "superseded_by_id"])
    op.create_index("ix_current_meaning_scope_created", "current_meanings", ["scope_key", "created_at"])
    # Single-active backstop (partial unique). Separate try blocks so a
    # dialect without partial-index support does not fail the migration.
    try:
        op.create_index(
            "uq_current_meaning_scope_active", "current_meanings", ["scope_key"],
            unique=True, postgresql_where=sa.text("superseded_by_id IS NULL"),
        )
    except Exception:
        pass


def downgrade():
    try:
        op.drop_index("uq_current_meaning_scope_active", table_name="current_meanings")
    except Exception:
        pass
    try:
        op.drop_index("ix_current_meaning_scope_created", table_name="current_meanings")
    except Exception:
        pass
    try:
        op.drop_index("ix_current_meaning_scope_active", table_name="current_meanings")
    except Exception:
        pass
    op.drop_table("current_meanings")
