"""make source-object uniqueness apply only to the active projection

Revision ID: 0011_active_source_object_index
Revises: 0010_commitment_candidates
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_active_source_object_index"
down_revision = "0010_commitment_candidates"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index(
        "uq_expectation_workspace_source_object", table_name="expectations"
    )
    op.create_index(
        "uq_expectation_workspace_source_object",
        "expectations",
        [
            "honcho_workspace_id",
            "source_system",
            "source_object_id",
            "owner_peer_id",
        ],
        unique=True,
        postgresql_where=sa.text(
            "source_system IS NOT NULL AND superseded_by_id IS NULL"
        ),
        sqlite_where=sa.text(
            "source_system IS NOT NULL AND superseded_by_id IS NULL"
        ),
    )


def downgrade():
    op.drop_index(
        "uq_expectation_workspace_source_object", table_name="expectations"
    )
    op.create_index(
        "uq_expectation_workspace_source_object",
        "expectations",
        [
            "honcho_workspace_id",
            "source_system",
            "source_object_id",
            "owner_peer_id",
        ],
        unique=True,
        postgresql_where=sa.text("source_system IS NOT NULL"),
        sqlite_where=sa.text("source_system IS NOT NULL"),
    )
