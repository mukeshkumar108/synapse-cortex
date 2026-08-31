"""recurrence occurrence follow-up accounting (asked_at, ask_count)

Revision ID: 0013_occurrence_followup
Revises: 0012_recurrence_semantic_type
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_occurrence_followup"
down_revision = "0012_recurrence_semantic_type"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("recurring_occurrences", sa.Column("asked_at", sa.DateTime(), nullable=True))
    op.add_column("recurring_occurrences", sa.Column("ask_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("recurring_occurrences", "ask_count")
    op.drop_column("recurring_occurrences", "asked_at")
