"""extractor reconciliation metadata

Revision ID: 0004_extractor_reconciliation
Revises: 0003_v4_core
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_extractor_reconciliation"
down_revision = "0003_v4_core"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("expectations", sa.Column("extractor_version", sa.String(), nullable=False, server_default="rules-v1"))
    op.create_index("ix_expectations_extractor_version", "expectations", ["extractor_version"])


def downgrade():
    op.drop_index("ix_expectations_extractor_version", table_name="expectations")
    op.drop_column("expectations", "extractor_version")
