"""recurrence semantic type (habit vs ritual vs adherence vs goal vs observed pattern)

Revision ID: 0012_recurrence_semantic_type
Revises: 0011_active_source_object_index
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_recurrence_semantic_type"
down_revision = "0011_active_source_object_index"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "recurring_intentions",
        sa.Column("semantic_type", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_recurring_intentions_semantic_type",
        "recurring_intentions",
        ["semantic_type"],
    )


def downgrade():
    op.drop_index("ix_recurring_intentions_semantic_type", table_name="recurring_intentions")
    op.drop_column("recurring_intentions", "semantic_type")
